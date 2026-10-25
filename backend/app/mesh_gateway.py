"""Authenticated inbound gateway for *received* Meshtastic text packets.

Only messages prefixed HARBOR REPORT: become incidents. No external dispatch.
"""
import hmac
import os
import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import ai, models
from backend.app.database import get_db
from backend.app.geocoding import geocode_text

router = APIRouter(prefix="/api/mesh/real", tags=["physical mesh gateway"])
PREFIX = "HARBOR REPORT:"


class RadioPacket(BaseModel):
    packet_id: str = Field(min_length=1, max_length=100)
    sender: str = Field(min_length=2, max_length=120)
    receiver: str = Field(min_length=2, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    received_at: datetime | None = None


class GatewayNodeHeartbeat(BaseModel):
    node_id: str = Field(min_length=2, max_length=120)
    battery: int | None = Field(default=None, ge=0, le=100)


@router.post("/heartbeat")
def node_heartbeat(
    payload: GatewayNodeHeartbeat,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected = os.getenv("HARBOR_MESH_GATEWAY_TOKEN", "")
    if not expected or not authorization or not hmac.compare_digest(authorization, "Bearer " + expected):
        raise HTTPException(status_code=401, detail="Gateway authorization required")
    label = "MESHTASTIC " + payload.node_id
    node = db.scalar(select(models.Node).where(models.Node.node_name == label))
    if node is None:
        node = models.Node(node_name=label)
        db.add(node)
    node.status = "ONLINE"
    node.last_seen = datetime.now(timezone.utc)
    if payload.battery is not None:
        node.battery = payload.battery
    db.commit()
    return {"status": "ONLINE", "node_name": label}


class GatewayNodeDisconnect(BaseModel):
    node_id: str = Field(min_length=2, max_length=120)


@router.post("/disconnect")
def node_disconnect(
    payload: GatewayNodeDisconnect,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected = os.getenv("HARBOR_MESH_GATEWAY_TOKEN", "")
    if not expected or not authorization or not hmac.compare_digest(authorization, "Bearer " + expected):
        raise HTTPException(status_code=401, detail="Gateway authorization required")
    label = "MESHTASTIC " + payload.node_id
    node = db.scalar(select(models.Node).where(models.Node.node_name == label))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not registered")
    node.status = "OFFLINE"
    db.commit()
    return {"status": "OFFLINE", "node_name": label}


@router.post("/receive")
def receive_packet(
    payload: RadioPacket,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected = os.getenv("HARBOR_MESH_GATEWAY_TOKEN", "")
    if not expected or not authorization or not hmac.compare_digest(
        authorization, "Bearer " + expected
    ):
        raise HTTPException(status_code=401, detail="Gateway authorization required")

    # Non-Harbor chat is ignored. Never convert public mesh chatter to incidents.
    if not payload.message.strip().upper().startswith(PREFIX):
        return {"status": "ignored", "reason": "not a Harbor incident message"}
    description = payload.message.strip()[len(PREFIX):].strip()
    if not description:
        raise HTTPException(status_code=422, detail="Incident description missing")
    if payload.sender == payload.receiver:
        return {"status": "ignored", "reason": "self-originated packet"}

    existing = db.scalar(select(models.RealMeshPacket).where(
        models.RealMeshPacket.sender == payload.sender,
        models.RealMeshPacket.packet_id == payload.packet_id,
    ))
    if existing:
        return {"status": "duplicate", "incident_id": existing.incident_id}

    affected_match = re.search(
        r"\b(\d{1,6})\s+(?:people|persons|residents|occupants|individuals)\b",
        description, re.I,
    )
    people_affected = int(affected_match.group(1)) if affected_match else 0
    is_test = bool(re.search(r"\b(?:TEST ONLY|SIMULATION|DRILL)\b", description, re.I))
    triage = ai.triage(description, people_affected=people_affected)
    location = geocode_text(None, description)
    incident = models.Incident(
        source="LORA_REAL",
        location=(location or {}).get("street_address"),
        node_id=payload.sender,
        category=str(triage["category"]),
        description=description,
        severity=str(triage["severity"]),
        people_affected=people_affected,
        status="REPORTED",
        latitude=(location or {}).get("latitude"),
        longitude=(location or {}).get("longitude"),
        ai_reasoning="Received through authenticated Meshtastic gateway; report unverified. " + str(triage["reason"]) + " (triage source: " + str(triage.get("source", "local_heuristic")) + ")",
        recommended_action=str(triage["recommended_action"]),
    )
    db.add(incident)
    # Receiving a report registers the sending radio even if its heartbeat was missed.
    node_name = "MESHTASTIC " + payload.sender
    node = db.scalar(select(models.Node).where(models.Node.node_name == node_name))
    if node is None:
        node = models.Node(node_name=node_name)
        db.add(node)
    node.status = "ONLINE"
    node.last_seen = datetime.now(timezone.utc)
    db.flush()
    db.add(models.RealMeshPacket(sender=payload.sender, packet_id=payload.packet_id, incident_id=incident.id))
    if incident.severity == "CRITICAL":
        # Dashboard review alert only; TEST ONLY stays blocked from real verification/dispatch.
        db.add(models.CriticalAlert(incident_id=incident.id))
    db.commit()
    return {"status": "created", "incident_id": incident.id, "severity": incident.severity, "source": "LORA_REAL", "test": is_test, "requires_operator_review": incident.severity == "CRITICAL", "alert_scope": "HARBOR_DASHBOARD_ONLY"}
