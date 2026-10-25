"""Preview or refresh a saved Harbor incident using current safety rules.

Usage:
    python scripts/retriage_incident.py --id 8
    python scripts/retriage_incident.py --id 8 --apply

Does not contact emergency responders. Does not change immutable record IDs.
"""
import argparse

from backend.app import ai, models
from backend.app.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Review a saved incident with current triage rules")
    parser.add_argument("--id", type=int, required=True, help="Immutable database incident ID")
    parser.add_argument("--apply", action="store_true", help="Commit changes after preview")
    args = parser.parse_args()

    with SessionLocal() as db:
        incident = db.get(models.Incident, args.id)
        if incident is None:
            parser.error("Incident ID not found")
        revised = ai.heuristic_triage(incident.description, incident.category, incident.people_affected)
        print(f"Incident ID: {incident.id}")
        print(f"Reported text: {incident.description}")
        print(f"Previous: {incident.category} / {incident.severity}")
        print(f"New: {revised['category']} / {revised['severity']}")
        print(f"Recommended action: {revised['recommended_action']}")
        if not args.apply:
            print("Preview only. Add --apply to update this saved incident.")
            return
        incident.category = str(revised["category"])
        incident.severity = str(revised["severity"])
        incident.recommended_action = str(revised["recommended_action"])
        incident.ai_reasoning = str(revised["reason"]) + "; retriaged with updated local safety rules"
        db.commit()
        print("Updated saved incident. No emergency services were contacted.")


if __name__ == "__main__":
    main()
