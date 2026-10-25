import json
import os
import re
from collections import Counter
from typing import Iterable
from urllib import request

from backend.app import models

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def heuristic_triage(description: str, category: str = "UNCLASSIFIED", people_affected: int = 0) -> dict[str, object]:
    text = f"{category} {description}".lower()
    reported = description.lower()
    fire_report = bool(re.search(r"\b(fire|flames|smoke|burning)\b", reported))
    flood_report = bool(re.search(r"\b(flood|flooding|floodwater)\b", reported))
    severity = "LOW"
    reason_bits: list[str] = []

    suspected_death = any(phrase in description.lower() for phrase in (
        "dead body", "deceased", "unresponsive", "not breathing",
        "unconscious", "person not moving", "body in the street",
    ))
    if suspected_death:
        severity = "CRITICAL"
        reason_bits.append("reported possible life-threatening medical emergency; condition unverified")
    if any(word in text for word in ["injured", "injury", "medical", "trapped", "missing", "fire", "urgent"]):
        if severity == "LOW":
            severity = "HIGH"
        reason_bits.append("reported medical, rescue, fire, or urgent language")
    if any(word in text for word in ["blocked", "blocking", "tree", "bridge", "flood", "generator", "fuel", "shelter"]):
        if severity == "LOW":
            severity = "MEDIUM"
        reason_bits.append("reported infrastructure/resource impact")
    if people_affected >= 25 or (people_affected >= 1 and severity == "HIGH" and any(word in text for word in ["blocked", "trapped", "fire"])):
        severity = "CRITICAL"
        reason_bits.append("people affected plus access/life-safety risk")

    if suspected_death:
        recommended = (
            "Possible unresponsive or deceased person reported: treat the condition as unverified. "
            "Call emergency services immediately and give the exact location. "
            "Keep bystanders and vehicles clear; do not move the person unless there is immediate danger. "
            "If safe, check responsiveness and breathing and follow dispatcher instructions for CPR or an AED. "
            "Leave any death determination, scene investigation, and notifications to qualified responders. "
            "Harbor does not automatically contact dispatch."
        )
        detected_category = "MEDICAL"
    elif fire_report:
        recommended = ("Reported fire or smoke: contact emergency services for immediate danger, "
                       "keep people away from the area, and follow dispatcher instructions. "
                       "Verify incident details before assigning responders; HARBOR does not dispatch.")
        detected_category = "FIRE"
    elif flood_report:
        recommended = ("Reported flooding: validate water conditions and location, "
                       "warn people away from hazardous water, and arrange human-led response review.")
        detected_category = "FLOOD"
    elif "generator" in text or "fuel" in text:
        recommended = "Check generator fuel, assign logistics support, and prepare shelter contingency plan."
        detected_category = "SHELTER"
    elif any(word in text for word in ["injured", "medical"]):
        recommended = "Dispatch medical assessment team after human commander approval and identify alternate access routes."
        detected_category = "MEDICAL"
    elif "flood" in text:
        recommended = "Monitor flood level, warn affected shelter/area, and stage evacuation resources for human approval."
        detected_category = "FLOOD"
    elif any(word in text for word in ["tree", "blocked", "blocking", "bridge"]):
        recommended = ("Keep people and vehicles away from the obstruction; do not attempt to move the tree or approach any downed wires. "
                       "Verify the exact location, road access, and whether anyone is injured or trapped. "
                       "Flag the roadway hazard for human incident review and coordinate a qualified road or utility crew if appropriate; "
                       "share alternate-route information only after it is verified.")
        detected_category = "INFRASTRUCTURE"
    else:
        recommended = "Validate report details, monitor conditions, and assign a human commander for review."
        detected_category = category or "GENERAL"

    return {
        "severity": severity,
        "category": detected_category.upper(),
        "people_affected": people_affected,
        "summary": description[:160],
        "recommended_action": recommended,
        "reason": "; ".join(reason_bits) if reason_bits else "No critical keywords detected; defaulted to low priority until verified.",
        "source": "local_heuristic",
    }


def try_ollama_triage(description: str, category: str, people_affected: int) -> dict[str, object] | None:
    prompt = {
        "task": "Triage emergency report. Return only JSON with severity, category, people_affected, summary, recommended_action, reason.",
        "allowed_severity": SEVERITIES,
        "report": {"description": description, "category": category, "people_affected": people_affected},
    }
    payload = json.dumps({"model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"), "prompt": json.dumps(prompt), "stream": False}).encode()
    try:
        req = request.Request(f"{os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')}/api/generate", data=payload, headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=2) as response:
            raw = json.loads(response.read().decode()).get("response", "{}")
        parsed = json.loads(raw)
        if parsed.get("severity") in SEVERITIES:
            parsed["source"] = "ollama"
            return parsed
    except Exception:
        return None
    return None


def triage(description: str, category: str = "UNCLASSIFIED", people_affected: int = 0) -> dict[str, object]:
    baseline = heuristic_triage(description, category, people_affected)
    model_result = try_ollama_triage(description, category, people_affected)
    if model_result is None:
        return baseline

    # Do not let an unconstrained language model downgrade a safety-relevant
    # report or issue a terse physical intervention such as "clear tree".
    rank = {name: idx for idx, name in enumerate(SEVERITIES)}
    proposed = str(model_result.get("severity", "LOW"))
    if rank.get(proposed, 99) > rank[baseline["severity"]]:
        proposed = str(baseline["severity"])
    baseline["severity"] = proposed
    baseline["source"] = "ollama_reviewed"
    # Safety recommendations remain vetted, deterministic guidance.
    baseline["reason"] = str(baseline["reason"]) + "; Ollama severity reviewed"
    return baseline


def ordered_incidents(incidents: Iterable[models.Incident]) -> list[models.Incident]:
    rank = {name: index for index, name in enumerate(SEVERITIES)}
    return sorted(incidents, key=lambda item: (rank.get(item.severity, 99), -item.people_affected, item.id))


def make_plan(incidents: list[models.Incident], resources: list[models.Resource], tasks: list[models.Task], constraint: str | None = None) -> dict[str, object]:
    available = [r for r in resources if r.status.upper() == "AVAILABLE"]
    actions = []
    for index, incident in enumerate(ordered_incidents(incidents), start=1):
        assigned = available[0].name if available else "UNASSIGNED - needs commander decision"
        actions.append(
            {
                "order": index,
                "incident_id": incident.id,
                "severity": incident.severity,
                "reported_information": incident.description,
                "ai_inference": incident.ai_reasoning or "Prioritized from reported severity and people affected.",
                "ai_recommendation": incident.recommended_action or "Assign commander review.",
                "suggested_resource": assigned,
                "human_approval_required": True,
            }
        )
    if not actions:
        actions.append({"order": 1, "ai_recommendation": "No active incidents. Keep monitoring field reports.", "human_approval_required": True})
    return {
        "requires_human_approval": True,
        "constraint": constraint,
        "available_resources": [r.name for r in available],
        "open_tasks": len([t for t in tasks if t.status.upper() != "DONE"]),
        "ordered_actions": actions,
    }


def make_briefing(incidents: list[models.Incident], resources: list[models.Resource]) -> dict[str, object]:
    active = [i for i in incidents if i.status.upper() not in {"CLOSED", "RESOLVED"}]
    counts = Counter(i.severity for i in active)
    available = [r for r in resources if r.status.upper() == "AVAILABLE"]
    top = ordered_incidents(active)[0] if active else None
    if top:
        briefing = (
            f"{len(active)} active incidents are reported. Highest priority is incident {top.id}, "
            f"classified {top.severity}: {top.description}. Recommended action: {top.recommended_action}. "
            f"{len(available)} resources are currently available. All actions require human commander approval."
        )
    else:
        briefing = "No active incidents are currently reported. Continue monitoring field nodes and local reports."
    return {"briefing": briefing, "active_incidents": len(active), "severity_counts": dict(counts), "available_resources": len(available)}
