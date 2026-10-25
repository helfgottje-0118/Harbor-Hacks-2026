"""Real Meshtastic USB receiver bridge for macOS.

Requires pip install meshtastic pypubsub. Do not use alongside meshtastic --listen.
Only text starting HARBOR REPORT: is ingested.
"""
import argparse
import json
import os
import sys
import time
import threading
from collections import deque
from urllib import error, request


def extract_report(packet: dict, local_node_num: int | None) -> dict | None:
    decoded = packet.get("decoded") or {}
    if str(decoded.get("portnum", "")).upper() not in ("TEXT_MESSAGE_APP", "1"):
        return None
    sender_num = packet.get("from")
    if local_node_num is not None and sender_num == local_node_num:
        return None
    message = decoded.get("text")
    if not isinstance(message, str) or not message.strip().upper().startswith("HARBOR REPORT:"):
        return None
    packet_id = packet.get("id")
    if packet_id is None or sender_num is None:
        return None
    return {
        "packet_id": str(packet_id),
        "sender": str(packet.get("fromId") or sender_num),
        "receiver": str(local_node_num if local_node_num is not None else "gateway"),
        "message": message.strip(),
    }


def forward(url: str, token: str, payload: dict) -> dict:
    req = request.Request(
        url.rstrip("/") + "/api/mesh/real/receive",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    with request.urlopen(req, timeout=15) as response:
        return json.load(response)


def fetch_saved_radio_reports(harbor_url: str) -> list[dict]:
    """Read saved radio incidents; these may be direct HTTP tests, not radio packets."""
    req = request.Request(harbor_url.rstrip("/") + "/api/incidents", method="GET")
    with request.urlopen(req, timeout=8) as response:
        incidents = json.load(response)
    return [item for item in incidents if item.get("source") == "LORA_REAL"]


def new_saved_reports(incidents: list[dict], seen: set[int]) -> list[dict]:
    """Show only IDs first observed after monitoring began."""
    fresh = [item for item in incidents if isinstance(item.get("id"), int) and item["id"] not in seen]
    seen.update(item["id"] for item in fresh)
    return sorted(fresh, key=lambda item: item["id"])


def outgoing_text(text: str, limit: int = 180) -> str:
    """Keep replies within a conservative radio text payload size."""
    clean = " ".join(str(text).split())
    if len(clean.encode("utf-8")) <= limit:
        return clean
    out = ""
    for char in clean:
        if len((out + char + "...").encode("utf-8")) > limit:
            break
        out += char
    return out.rstrip() + "..."


def incoming_command(packet: dict, local_node_num: int | None) -> tuple[str, str] | None:
    decoded = packet.get("decoded") or {}
    if str(decoded.get("portnum", "")).upper() not in ("TEXT_MESSAGE_APP", "1"):
        return None
    if packet.get("from") is None or packet.get("from") == local_node_num:
        return None
    value = decoded.get("text")
    if not isinstance(value, str):
        return None
    text = value.strip()
    for prefix, mode in (("HARBOR AI:", "ai"), ("HARBOR REPORT:", "report")):
        if text.upper().startswith(prefix):
            return mode, text[len(prefix):].strip()
    return None


def ask_harbor_ai(harbor_url: str, question: str) -> str:
    req = request.Request(
        harbor_url.rstrip("/") + "/api/ai/chat",
        method="POST",
        data=json.dumps({"message": question, "history": []}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=125) as response:
        result = json.load(response)
    if result.get("report_draft"):
        return "Report drafting requires confirmation in the HARBOR dashboard."
    return str(result.get("reply") or "HARBOR AI did not return an answer.")


def incident_recommendation(harbor_url: str, incident_id: int) -> str:
    req = request.Request(harbor_url.rstrip("/") + "/api/incidents/" + str(incident_id))
    with request.urlopen(req, timeout=15) as response:
        incident = json.load(response)
    return str(incident.get("recommended_action") or "Report saved; awaiting human review.")


def heartbeat(harbor_url: str, token: str, node_id: str) -> dict:
    req = request.Request(
        harbor_url.rstrip("/") + "/api/mesh/real/heartbeat",
        method="POST",
        data=json.dumps({"node_id": node_id}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    with request.urlopen(req, timeout=8) as response:
        return json.load(response)



def disconnect(harbor_url: str, token: str, node_id: str) -> dict:
    req = request.Request(
        harbor_url.rstrip("/") + "/api/mesh/real/disconnect",
        method="POST",
        data=json.dumps({"node_id": node_id}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    with request.urlopen(req, timeout=5) as response:
        return json.load(response)



def main() -> int:
    parser = argparse.ArgumentParser(description="Listen to physical Meshtastic USB text packets")
    parser.add_argument("--port", default="/dev/cu.usbserial-0001")
    parser.add_argument("--harbor-url", default=os.getenv("HARBOR_URL", "http://192.168.4.54:8010"))
    parser.add_argument("--demo", action="store_true", help="Interactive one-radio AI demonstration; broadcast replies, not received packets")
    args = parser.parse_args()
    token = os.getenv("HARBOR_MESH_GATEWAY_TOKEN", "")
    if not token:
        print("ERROR: HARBOR_MESH_GATEWAY_TOKEN is missing on this Mac. The radio cannot appear ONLINE until the Mac gateway authenticates to HARBOR. Set the same token used by the Ubuntu harbor.service, then restart this command.", file=sys.stderr)
        return 2

    try:
        from meshtastic.serial_interface import SerialInterface
        from pubsub import pub
    except ImportError:
        print("Install meshtastic and pypubsub: pip install meshtastic pypubsub", file=sys.stderr)
        return 2

    interface = SerialInterface(devPath=args.port)
    me = getattr(getattr(interface, "myInfo", None), "my_node_num", None)
    node_name = "!" + format(me, "08x") if isinstance(me, int) else "UNKNOWN-GATEWAY"
    try:
        print("[HARBOR NODE] " + str(heartbeat(args.harbor_url, token, node_name)), flush=True)
    except (error.URLError, TimeoutError, ValueError) as exc:
        print(f"[HARBOR NODE ERROR] Registration failed: {exc}. Check that the Mac token matches the Ubuntu systemd environment and --harbor-url points at that same server.", file=sys.stderr, flush=True)
        interface.close()
        return 2
    # macOS removes /dev/cu.usbserial-* when the USB device is unplugged.
    # A fast watcher reports the disconnect rather than waiting for heartbeat expiry.
    stop_usb_watch = threading.Event()
    def watch_usb():
        while not stop_usb_watch.wait(0.5):
            if not os.path.exists(args.port):
                print("[HARBOR NODE] USB radio unplugged; marking node OFFLINE.", flush=True)
                try:
                    print("[HARBOR NODE] " + str(disconnect(args.harbor_url, token, node_name)), flush=True)
                except (error.URLError, TimeoutError, ValueError, OSError) as exc:
                    print(f"[HARBOR NODE] Disconnect notification failed: {exc}", file=sys.stderr, flush=True)
                # The serial connection is no longer usable. Restart the gateway after reconnecting.
                os._exit(3)
    usb_watch_thread = threading.Thread(target=watch_usb, daemon=True)
    usb_watch_thread.start()
    if args.demo:
        stop_heartbeat = threading.Event()
        def demo_heartbeat_loop():
            while not stop_heartbeat.wait(2):
                if not os.path.exists(args.port):
                    break
                try:
                    heartbeat(args.harbor_url, token, node_name)
                except (error.URLError, TimeoutError, ValueError) as exc:
                    print(f"[HARBOR NODE] Heartbeat failed: {exc}", file=sys.stderr, flush=True)
        heartbeat_thread = threading.Thread(target=demo_heartbeat_loop, daemon=True)
        heartbeat_thread.start()
    if args.demo:
        print("ONE-RADIO DEMO: questions come from this Mac keyboard, NOT from LoRa.", flush=True)
        print("HARBOR AI responses will be printed here and BROADCAST by the Heltec.", flush=True)
        print("A second radio is required to confirm over-the-air reception. Type exit to quit.", flush=True)
        try:
            while True:
                question = input("\nHARBOR AI QUESTION > ").strip()
                if question.lower() in ("exit", "quit"):
                    break
                if not question:
                    continue
                try:
                    answer = ask_harbor_ai(args.harbor_url, question)
                    print(f"\n[HARBOR AI RESPONSE] {answer}", flush=True)
                    reply = outgoing_text("HARBOR AI: " + answer)
                    interface.sendText(reply)
                    print(f"[RADIO TRANSMIT REQUESTED] {reply}", flush=True)
                    print("[DEMO] Broadcast requested; reception by another radio is NOT verified.", flush=True)
                except (error.URLError, TimeoutError, ValueError, OSError) as exc:
                    print(f"[DEMO ERROR] {exc}", file=sys.stderr, flush=True)
        except (KeyboardInterrupt, EOFError):
            print("\nStopping demo.", flush=True)
        finally:
            stop_usb_watch.set()
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=2)
            try:
                disconnect(args.harbor_url, token, node_name)
            except (error.URLError, TimeoutError, ValueError, OSError) as exc:
                print(f"[HARBOR NODE] Disconnect notification failed: {exc}", file=sys.stderr, flush=True)
            interface.close()
        return 0
    print(f"Connected to {args.port}; local node {me}. Waiting for real received HARBOR reports.")
    print("Format: HARBOR REPORT: Tree blocking roadway at 54 George Street")
    print("Or: HARBOR AI: What should I do during flooding? Replies go BACK OVER LoRa.", flush=True)
    processed = set()
    recent = deque(maxlen=256)
    last_reply = [0.0]
    try:
        seen = {item["id"] for item in fetch_saved_radio_reports(args.harbor_url)}
        print(f"Watching HARBOR for NEW saved LoRa reports (existing: {len(seen)}).", flush=True)
    except (error.URLError, TimeoutError, ValueError) as exc:
        print(f"HARBOR watch unavailable: {exc}. Retrying.", file=sys.stderr, flush=True)
        seen = None

    def on_receive(packet: dict, interface=None):
        command = incoming_command(packet, me)
        if command is None:
            return
        mode, message = command
        sender = packet.get("fromId") or packet.get("from")
        key = (str(sender), str(packet.get("id")))
        if key in processed:
            return
        processed.add(key)
        if len(recent) == recent.maxlen:
            processed.discard(recent.popleft())
        recent.append(key)
        if not message:
            return
        now = time.monotonic()
        if now - last_reply[0] < 20:
            print("[RADIO] Request skipped: reply cooldown (20 seconds).", flush=True)
            return
        last_reply[0] = now
        try:
            if mode == "ai":
                response_text = ask_harbor_ai(args.harbor_url, message)
                prefix = "HARBOR AI: "
            else:
                payload = extract_report(packet, me)
                if payload is None:
                    return
                result = forward(args.harbor_url, token, payload)
                if result.get("status") not in ("created", "duplicate"):
                    return
                response_text = incident_recommendation(args.harbor_url, result["incident_id"])
                prefix = "HARBOR ADVICE: "
            reply = outgoing_text(prefix + response_text)
            if not reply:
                return
            print(f"[RADIO RX] {sender}: {message}", flush=True)
            interface.sendText(reply, destinationId=str(sender), wantAck=False)
            print(f"[RADIO TX -> {sender}] {reply} (delivery unconfirmed)", flush=True)
        except (error.URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
            print(f"[RADIO] Could not generate/send reply: {exc}", file=sys.stderr, flush=True)

    pub.subscribe(on_receive, "meshtastic.receive")
    last_heartbeat = time.monotonic()
    try:
        while True:
            time.sleep(3)
            if time.monotonic() - last_heartbeat >= 2:
                if not os.path.exists(args.port):
                    continue
                try:
                    heartbeat(args.harbor_url, token, node_name)
                except (error.URLError, TimeoutError, ValueError) as exc:
                    print(f"[HARBOR NODE] Heartbeat failed: {exc}", file=sys.stderr, flush=True)
                last_heartbeat = time.monotonic()
            try:
                saved = fetch_saved_radio_reports(args.harbor_url)
                if seen is None:
                    seen = {item["id"] for item in saved}
                    print(f"HARBOR watch connected; tracking {len(seen)} existing radio reports.", flush=True)
                    continue
                for item in new_saved_reports(saved, seen):
                    print(
                        f"[HARBOR SAVED] Incident #{item['id']} | {item.get('severity')} | "
                        f"{item.get('node_id')} | {item.get('description')} "
                        f"(source={item.get('source')}; may be API test, not proven RF reception)",
                        flush=True,
                    )
                    if item.get("recommended_action"):
                        print(f"  [HARBOR RECOMMENDATION] {item['recommended_action']}", flush=True)
                    if item.get("ai_reasoning"):
                        print(f"  [TRIAGE] {item['ai_reasoning']}", flush=True)
            except (error.URLError, TimeoutError, ValueError) as exc:
                print(f"HARBOR report watch: {exc}", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        print("Stopping receiver.")
    finally:
        stop_usb_watch.set()
        pub.unsubscribe(on_receive, "meshtastic.receive")
        try:
            disconnect(args.harbor_url, token, node_name)
        except (error.URLError, TimeoutError, ValueError, OSError) as exc:
            print(f"[HARBOR NODE] Disconnect notification failed: {exc}", file=sys.stderr, flush=True)
        interface.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
