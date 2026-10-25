"""Submit a fresh local HTTP test report to Harbor, without pretending RF receipt."""
import argparse
import json
import os
import uuid
from urllib import request


def main():
    p = argparse.ArgumentParser(description="Create one fresh Harbor radio-ingestion API test")
    p.add_argument("description", nargs="?", default="Tree blocking roadway at 54 George Street")
    p.add_argument("--harbor-url", default="http://192.168.4.54:8010")
    args = p.parse_args()
    token = os.environ.get("HARBOR_MESH_GATEWAY_TOKEN", "")
    if not token:
        raise SystemExit("Set HARBOR_MESH_GATEWAY_TOKEN first.")
    payload = {
        "packet_id": "local-api-test-" + uuid.uuid4().hex,
        "sender": "!LOCAL-API-TEST",
        "receiver": "!433c2ff4",
        "message": "HARBOR REPORT: " + args.description,
    }
    req = request.Request(
        args.harbor_url.rstrip("/") + "/api/mesh/real/receive",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    with request.urlopen(req, timeout=15) as response:
        result = json.load(response)
    print("LOCAL HTTP TEST — not a received LoRa transmission")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
