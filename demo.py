import json
import time
from urllib import request

BASE_URL = "http://127.0.0.1:8010"


def post(path: str, payload: dict):
    req = request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        body = json.loads(response.read().decode())
    print(path, json.dumps(body, indent=2))
    return body


if __name__ == "__main__":
    print("Injecting HARBOR demo scenario...")
    post("/api/resources", {"name": "Rescue Team Alpha", "type": "RESCUE", "status": "AVAILABLE", "location": "HQ", "capacity": 4})
    time.sleep(1)
    post("/api/incidents", {"source": "WEB", "node_id": "PHONE-1", "category": "MEDICAL", "description": "Tree blocking East Bay Street with one injured person", "people_affected": 1})
    time.sleep(1)
    post("/api/incidents", {"source": "WEB", "node_id": "SHELTER-A", "category": "FLOOD", "description": "Floodwater rising near Shelter A with 30 people present", "people_affected": 30})
    time.sleep(1)
    post("/api/incidents", {"source": "WEB", "node_id": "SHELTER-B", "category": "SHELTER", "description": "Shelter B generator has approximately two hours of fuel", "people_affected": 30})
    time.sleep(1)
    post("/api/tasks", {"title": "Only one rescue team available; reprioritize response", "priority": "HIGH", "assigned_resource": "Rescue Team Alpha"})
    print("Demo scenario complete. Refresh the dashboard.")
