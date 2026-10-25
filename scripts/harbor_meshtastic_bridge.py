"""Meshtastic gateway for HARBOR incident reports and FORGE-backed /ai chat.

Only one process should hold the USB serial port. Keep the HARBOR gateway token
in the host environment, not in the repository or Meshtastic messages.
"""
import json
import os
import queue
import re
import threading
import time
from urllib import error, request

from pubsub import pub
import meshtastic.serial_interface

HARBOR_URL = os.environ.get("HARBOR_API_URL", "http://192.168.4.54:8010").rstrip("/")
TOKEN = os.environ.get("HARBOR_MESH_GATEWAY_TOKEN", "")
PORT = os.environ.get("MESHTASTIC_PORT", "/dev/cu.usbmodem101")
MESHTASTIC_REPLY_BYTES = max(80, min(180, int(os.environ.get("MESHTASTIC_REPLY_BYTES", "160"))))
MESHTASTIC_CHUNK_DELAY = max(2.0, float(os.environ.get("MESHTASTIC_CHUNK_DELAY", "3")))
MESHTASTIC_MAX_CHUNKS = max(1, min(8, int(os.environ.get("MESHTASTIC_MAX_CHUNKS", "5"))))
jobs = queue.Queue(maxsize=100)
radio = None
local_node = None
seen = set()
seen_order = []
seen_lock = threading.Lock()
pending = {}  # sender -> (description, draft time)
last_result = {}  # sender -> last backend result
PENDING_TTL = 600



def post(path, payload, timeout=15):
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = request.Request(
        HARBOR_URL + path, data=json.dumps(payload).encode("utf-8"),
        method="POST", headers=headers,
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def parse_message(text):
    if not isinstance(text, str):
        return None
    text = text.strip()
    # Meshtastic phone keyboards sometimes insert a space after the slash.
    # Normalize command spelling only; preserve the incident description.
    text = re.sub(r"^/\s+(?=[A-Za-z])", "/", text)
    low = text.lower()
    if low == "/status":
        return ("status", "")
    if low == "/ping":
        return ("ping", "")
    if low in ("/confirm", "/submit", "/cancel"):
        return (low[1:], "")
    if low.startswith("/confirm "):
        return ("confirm", text[len("/confirm "):].strip())
    # /ai /harbor is an explicit HARBOR report command, not a chatbot request.
    # Standalone /harbor and /report are supported below too.
    match = re.match(r"^/ai\s+/harbor(?:\s+(.+))?$", text, re.I | re.S)
    if match:
        description = (match.group(1) or "").strip()
        return ("report", "HARBOR REPORT: " + description if description else "")
    # Explicit report submission, never inferred from ordinary /ai questions.
    # Keep the HARBOR REPORT: prefix required by the authenticated API.
    match = re.match(r"^/(?:report|harbor)(?:\s+(.+))?$", text, re.I | re.S)
    if match:
        description = (match.group(1) or "").strip()
        return ("report", "HARBOR REPORT: " + description if description else "")
    match = re.match(r"^/ai\s+(?:(?:submit|file|post)\s+(?:an?\s+)?(?:incident\s+)?report|report)\s*:?\s+(.+)$", text, re.I | re.S)
    if match:
        return ("report", "HARBOR REPORT: " + match.group(1).strip())
    if low == "/ai full":
        return ("ai_full", "")
    if low.startswith("/ai full "):
        return ("ai_full", text[len("/ai full "):].strip())
    if low == "/ai":
        return ("ai", "")
    if low.startswith("/ai "):
        return ("ai", text[4:].strip())
    if low.startswith("harbor ai:"):
        return ("ai", text[len("harbor ai:"):].strip())
    if low.startswith("harbor report:"):
        return ("report", text)
    if low.startswith("harbor warning:"):
        return ("report", "HARBOR REPORT: " + text[len("harbor warning:"):].strip())
    if low.startswith("/warn "):
        return ("report", "HARBOR REPORT: " + text[len("/warn "):].strip())
    if low == "/warn":
        return ("report", "")
    return None


def radio_text(value, limit=MESHTASTIC_REPLY_BYTES):
    """Single UTF-8-safe message, truncated with an ellipsis if necessary."""
    value = " ".join(str(value).split())
    if len(value.encode("utf-8")) <= limit:
        return value
    result = ""
    for ch in value:
        if len((result + ch + "...").encode("utf-8")) > limit:
            break
        result += ch
    return result.rstrip() + "..."


def split_radio_text(value, limit=MESHTASTIC_REPLY_BYTES, max_chunks=MESHTASTIC_MAX_CHUNKS):
    """Split a longer reply at word boundaries into UTF-8-safe numbered parts.

    Limit total packets to avoid flooding the mesh. Packet numbering includes
    reserved header space; a final ellipsis marks a truncated response.
    """
    value = " ".join(str(value).split())
    if not value:
        return ["FORGE: No answer returned."]
    # Reserve enough bytes for 'FORGE 8/8: ', with room for UTF-8 characters.
    payload_limit = limit - 16
    words = value.split(" ")
    parts = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate.encode("utf-8")) <= payload_limit:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        # Long unbroken words or URLs also need byte-safe splitting.
        for ch in word:
            if len((current + ch).encode("utf-8")) > payload_limit:
                if current:
                    parts.append(current)
                current = ch
            else:
                current += ch
    if current:
        parts.append(current)
    truncated = len(parts) > max_chunks
    parts = parts[:max_chunks]
    if truncated:
        parts[-1] = radio_text(parts[-1], payload_limit - 3).removesuffix("...").rstrip() + "..."
    if len(parts) == 1:
        return [radio_text("FORGE: " + parts[0], limit)]
    return [f"FORGE {i}/{len(parts)}: {part}" for i, part in enumerate(parts, 1)]


def transmit(sender, reply, multipart=False):
    if radio is None:
        return
    pieces = split_radio_text(reply) if multipart else [radio_text(reply)]
    for i, response in enumerate(pieces):
        if i:
            time.sleep(MESHTASTIC_CHUNK_DELAY)
        radio.sendText(response, destinationId=sender, wantAck=False)
        print("[MESH TX]", sender, response, flush=True)

def on_receive(packet, interface=None):
    decoded = packet.get("decoded") or {}
    if str(decoded.get("portnum", "")).upper() not in ("TEXT_MESSAGE_APP", "1"):
        return
    raw_text = decoded.get("text")
    if raw_text is None and isinstance(decoded.get("payload"), (bytes, bytearray)):
        raw_text = decoded["payload"].decode("utf-8", errors="replace")
    if not isinstance(raw_text, str):
        return
    command = parse_message(raw_text)
    print("[MESH TEXT]", str(packet.get("fromId") or packet.get("from")),
          "command=" + (command[0] if command else "unmatched"),
          "text=" + repr(raw_text[:140]), flush=True)
    if command is None:
        return
    sender_num = packet.get("from")
    if local_node is not None and sender_num == local_node:
        return
    sender = ("!" + format(sender_num, "08x")) if isinstance(sender_num, int) else str(packet.get("fromId") or "")
    receiver = str(packet.get("toId") or packet.get("to") or "")
    packet_id = packet.get("id")
    if not sender:
        print("[MESH SKIP] missing sender", flush=True)
        return
    if packet_id is None:
        packet_id = "rx-" + str(time.monotonic_ns())
        print("[MESH WARN] packet has no ID", flush=True)
    key = (sender, str(packet_id))
    with seen_lock:
        if key in seen:
            return
        seen.add(key)
        seen_order.append(key)
        if len(seen_order) > 512:
            seen.discard(seen_order.pop(0))
    try:
        jobs.put_nowait((sender, receiver, str(packet_id), *command))
        print("[MESH RX]", sender, command[0], repr(command[1][:100]), flush=True)
    except queue.Full:
        print("[MESH] Queue full; dropping request", flush=True)


def report_description(raw):
    if raw.upper().startswith("HARBOR REPORT:"):
        return raw[len("HARBOR REPORT:"):].strip()
    return raw.strip()


def register_node(sender):
    """Best-effort registration; submissions must not depend on heartbeat."""
    if not TOKEN:
        return
    try:
        post("/api/mesh/real/heartbeat", {"node_id": sender}, timeout=10)
    except Exception as exc:
        print("[MESH HEARTBEAT ERROR]", type(exc).__name__, str(exc)[:160], flush=True)


def submit_report(sender, receiver, packet_id, description):
    if not TOKEN:
        raise ValueError("HARBOR_MESH_GATEWAY_TOKEN is missing from Mac .env.mesh")
    result = post("/api/mesh/real/receive", {
        "sender": sender, "receiver": receiver or "HARBOR-GATEWAY",
        "packet_id": packet_id,
        "message": "HARBOR REPORT: " + description,
    }, timeout=35)
    status = str(result.get("status") or "unknown").lower()
    incident = result.get("incident_id")
    if status not in ("created", "duplicate") or incident is None:
        return "HARBOR: NOT SAVED (" + status + "). Check Mac logs."
    severity = str(result.get("severity") or "REPORTED")
    if severity == "CRITICAL":
        suffix = "TEST - dashboard review only." if result.get("test") else "Awaiting operator review; no dispatch."
        return f"HARBOR #{incident} {status.upper()} CRITICAL. {suffix}"
    return f"HARBOR #{incident} {status.upper()} {severity}. Unverified; no dispatch."


def worker():
    while True:
        sender, receiver, packet_id, mode, message = jobs.get()
        try:
            if mode == "status":
                draft = pending.get(sender)
                if draft and time.monotonic() - draft[1] <= PENDING_TTL:
                    transmit(sender, "HARBOR: Draft pending. Reply /confirm or /cancel.")
                else:
                    transmit(sender, last_result.get(sender, "HARBOR: No pending draft or saved result."))
            elif mode == "ping":
                transmit(sender, "HARBOR gateway online. Send /report <incident>.")
            elif mode in ("ai", "ai_full"):
                if not message:
                    reply = "FORGE: Use /ai <question> or /ai /harbor <incident>."
                else:
                    prompt = message if mode == "ai_full" else (
                        "LoRa radio reply: one concise sentence at most 110 characters; "
                        "no markdown. User: " + message
                    )
                    result = post("/api/ai/chat", {"message": prompt, "history": []}, timeout=125)
                    reply = ("FORGE: Use /ai /harbor <incident> to create a LoRa report."
                             if result.get("report_draft") else
                             str(result.get("reply") or "No answer returned."))
                transmit(sender, reply if reply.startswith("FORGE:") else "FORGE: " + reply,
                         multipart=(mode == "ai_full"))
            elif mode == "report":
                description = report_description(message)
                if not description:
                    transmit(sender, "HARBOR: Use /report <incident and location>.")
                    continue
                if len(description) > 800:
                    transmit(sender, "HARBOR: Report too long. Reduce to 800 characters.")
                    continue
                pending[sender] = (description, time.monotonic())
                transmit(sender, radio_text(
                    "HARBOR DRAFT: " + description, MESHTASTIC_REPLY_BYTES - 52
                ) + " | /confirm to submit or /cancel.")
                print("[MESH DRAFT]", sender, repr(description), flush=True)
                register_node(sender)
            elif mode in ("confirm", "submit"):
                draft = pending.get(sender)
                if not draft or time.monotonic() - draft[1] > PENDING_TTL:
                    pending.pop(sender, None)
                    transmit(sender, "HARBOR: No pending report. Send /report <incident>.")
                    continue
                description = draft[0]
                transmit(sender, "HARBOR: Confirmation received; saving report...")
                print("[MESH CONFIRM]", sender, repr(description), flush=True)
                # One packet ID per confirmed radio request; idempotent on retries.
                reply = submit_report(sender, receiver, packet_id, description)
                if " NOT SAVED " not in reply:
                    pending.pop(sender, None)
                    last_result[sender] = reply
                transmit(sender, reply)
                print("[MESH SUBMIT]", sender, reply, flush=True)
                register_node(sender)
            elif mode == "cancel":
                pending.pop(sender, None)
                transmit(sender, "HARBOR: Draft canceled. No report submitted.")
        except error.HTTPError as exc:
            body = exc.read(350).decode("utf-8", errors="replace")
            print("[MESH HTTP ERROR]", exc.code, body, flush=True)
            transmit(sender, f"HARBOR: Not saved, HTTP {exc.code}. Check Mac logs.")
        except Exception as exc:
            print("[MESH ERROR]", type(exc).__name__, str(exc), flush=True)
            transmit(sender, "HARBOR: Gateway error; not confirmed saved. Check Mac logs.")
        finally:
            jobs.task_done()

def main():
    global radio, local_node
    threading.Thread(target=worker, daemon=True).start()
    pub.subscribe(on_receive, "meshtastic.receive")
    print("Connecting to", PORT, "HARBOR API", HARBOR_URL, flush=True)
    try:
        radio = meshtastic.serial_interface.SerialInterface(devPath=PORT)
        local_node = getattr(getattr(radio, "myInfo", None), "my_node_num", None)
        print("HARBOR MESH BRIDGE VERSION: CONFIRM-ACK-2026-10-25", flush=True)
        print("Local node ID:", local_node, flush=True)
        print("Gateway token configured:", bool(TOKEN), flush=True)
        print("Ready: /ping, /ai <question>, /ai full <question>, /report <incident>, /confirm, /cancel", flush=True)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        pub.unsubscribe(on_receive, "meshtastic.receive")
        if radio is not None:
            radio.close()


if __name__ == "__main__":
    main()
