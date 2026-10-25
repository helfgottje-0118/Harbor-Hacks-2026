"""Simulate LoRa messages to local Ollama or the HARBOR incident API.

No radio hardware is used. Run from the repository root:
    python scripts/harbor_lora_simulator.py --mode ai
    python scripts/harbor_lora_simulator.py --mode incident
"""
import argparse
import json
import os
import sys
import uuid
from urllib import error, request


SYSTEM_PROMPT = (
    "You are Harbor, an emergency preparedness and assistance AI. "
    "Give brief, practical and cautious safety information. "
    "Recommend contacting emergency services when someone is in immediate danger. "
    "Never imply responders were contacted or deployed. "
    "Never invent current conditions or verified rescue availability. "
    "Keep replies short enough for a low-bandwidth radio."
)


def post_json(url: str, payload: dict, timeout: float = 120) -> dict:
    """Make an HTTP JSON request; safe error text is handled by the CLI."""
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def simulate_ai(message: str, ollama_url: str, model: str) -> str:
    response = post_json(
        f"{ollama_url.rstrip('/')}/api/generate",
        {
            "model": model,
            "prompt": f"{SYSTEM_PROMPT}\nUser: {message}\nHarbor:",
            "stream": False,
            "options": {"num_predict": 100},
        },
    )
    answer = response.get("response")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Ollama returned no text. Check the configured model.")
    return answer.strip()


def simulate_incident(message: str, harbor_url: str, node: str) -> dict:
    return post_json(
        f"{harbor_url.rstrip('/')}/api/mesh/message",
        {
            "node": node,
            "type": "UNCLASSIFIED",
            "priority": "NORMAL",
            "message": message,
        },
        timeout=30,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="HARBOR LoRa simulator (no physical radio required)"
    )
    parser.add_argument("--mode", choices=("ai", "incident"), default="ai")
    parser.add_argument(
        "--ollama-url", default=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    )
    parser.add_argument(
        "--model", default=os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    )
    parser.add_argument(
        "--harbor-url", default=os.getenv("HARBOR_URL", "http://127.0.0.1:8010")
    )
    parser.add_argument("--node", default="SIM-NODE-01")
    parser.add_argument("--once", help="Send one simulated message and exit")
    args = parser.parse_args(argv)

    print(f"[HARBOR] LoRa simulation: {args.mode}. NO RADIO TRANSMISSION.")
    while True:
        if args.once is not None:
            message = args.once.strip()
        else:
            try:
                message = input("\nLoRa message > ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
        if message.lower() in {"exit", "quit"} and args.once is None:
            return 0
        if not message:
            if args.once is not None:
                print("Message cannot be empty.", file=sys.stderr)
                return 2
            continue

        packet_id = uuid.uuid4().hex[:8]
        print(f"[LoRa SIM] {args.node} packet={packet_id} received: {message}")
        try:
            if args.mode == "ai":
                reply = simulate_ai(message, args.ollama_url, args.model)
                print(f"[Harbor AI] {reply}")
                print("[LoRa SIM] Reply simulated; nothing transmitted over radio.")
            else:
                incident = simulate_incident(message, args.harbor_url, args.node)
                print(
                    f"[HARBOR] Incident #{incident['id']} submitted "
                    f"(severity={incident['severity']}, source={incident['source']})."
                )
                print("[LoRa SIM] Incident visible through the Harbor API/map.")
        except (error.URLError, error.HTTPError, ValueError, KeyError, TimeoutError) as exc:
            print(f"[HARBOR] Request failed: {exc}", file=sys.stderr)
            if args.once is not None:
                return 1

        if args.once is not None:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
