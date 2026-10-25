from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import ai, ai_chat, maps, mesh_gateway, models, schemas
from backend.app.database import database_is_online, get_db, init_db
from backend.app.geocoding import geocode_location, geocode_text


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Repair coordinates for previously imported reports only when an exact,
    # locally known street address can be resolved (never guess coordinates).
    from backend.app.database import SessionLocal
    from backend.app.geocoding import OFFLINE_LOCATIONS, normalize_location
    with SessionLocal() as db:
        missing = db.scalars(select(models.Incident).where(
            (models.Incident.latitude.is_(None)) | (models.Incident.longitude.is_(None))
        )).all()
        for incident in missing:
            address = normalize_location(incident.location or "")
            known = OFFLINE_LOCATIONS.get(address)
            if not known:
                continue
            incident.latitude = float(known["latitude"])
            incident.longitude = float(known["longitude"])
            incident.location = str(known["street_address"])
        # Correct earlier PHOTON reports misclassified as infrastructure,
        # only when their actual reported wording explicitly names a fire/flood.
        import re
        for incident in db.scalars(select(models.Incident).where(
            models.Incident.source == "PHOTON",
            models.Incident.category == "INFRASTRUCTURE",
        )).all():
            words = incident.description or ""
            event = ("FIRE" if re.search(r"\b(fire|flames|smoke|burning)\b", words, re.I)
                     else "FLOOD" if re.search(r"\b(flood|flooding|floodwater)\b", words, re.I)
                     else None)
            if event:
                reviewed = ai.heuristic_triage(words, event, incident.people_affected)
                incident.category = event
                incident.recommended_action = str(reviewed["recommended_action"])
        db.commit()
    yield


app = FastAPI(
    title="HARBOR Backend",
    description="Offline emergency command backend for HARBOR.",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(maps.router)
app.include_router(ai_chat.router)
app.include_router(mesh_gateway.router)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"

if FRONTEND_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="assets")


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HARBOR | Offline Emergency Command</title>
  <style>
    :root { color-scheme: dark; --bg:#05070b; --panel:#101827; --panel2:#0b1220; --line:#263244; --text:#eef4ff; --muted:#91a3bb; --red:#ef4444; --amber:#f59e0b; --green:#22c55e; --blue:#38bdf8; --purple:#a78bfa; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:radial-gradient(circle at top left,#172554 0,#05070b 42%,#02040a 100%); color:var(--text); }
    main { max-width:1400px; margin:0 auto; padding:24px; }
    header { display:flex; justify-content:space-between; gap:18px; align-items:flex-start; margin-bottom:20px; }
    h1 { margin:0; font-size:54px; letter-spacing:-0.08em; line-height:.9; }
    h2 { margin:0 0 12px; font-size:18px; letter-spacing:.08em; text-transform:uppercase; }
    h3 { margin:0 0 8px; }
    input, textarea, select, button { width:100%; border-radius:12px; border:1px solid #334155; background:#070d18; color:var(--text); padding:10px; font:inherit; }
    textarea { min-height:96px; resize:vertical; }
    button { cursor:pointer; background:#1d4ed8; border-color:#3b82f6; font-weight:800; }
    button.secondary { background:#132036; }
    .tagline { color:var(--muted); margin-top:10px; font-size:18px; }
    .badge { border:1px solid #31506f; background:#0b1220cc; padding:10px 14px; border-radius:999px; white-space:nowrap; font-weight:700; }
    .grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; }
    .card { border:1px solid var(--line); background:linear-gradient(180deg,var(--panel),var(--panel2)); border-radius:18px; padding:16px; box-shadow:0 18px 38px #0008; }
    .span3 { grid-column:span 3; } .span4 { grid-column:span 4; } .span5 { grid-column:span 5; } .span6 { grid-column:span 6; } .span7 { grid-column:span 7; } .span8 { grid-column:span 8; } .span12 { grid-column:span 12; }
    .label { color:var(--muted); text-transform:uppercase; letter-spacing:.12em; font-size:12px; }
    .value { font-size:30px; font-weight:900; margin:8px 0; }
    .detail { color:#c8d3e1; line-height:1.55; }
    .ok { color:var(--green); } .warn { color:var(--amber); } .critical { color:var(--red); } .blue { color:var(--blue); } .purple { color:var(--purple); }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .item { border:1px solid #263244; border-left-width:5px; border-radius:14px; padding:12px; margin-bottom:10px; background:#07101e; }
    .CRITICAL { border-left-color:var(--red); } .HIGH { border-left-color:var(--amber); } .MEDIUM { border-left-color:var(--blue); } .LOW { border-left-color:var(--green); }
    .pill { display:inline-block; border:1px solid #334155; border-radius:999px; padding:3px 8px; margin:2px; font-size:12px; color:#dbeafe; }
    pre { white-space:pre-wrap; background:#050914; border:1px solid #1f2937; padding:12px; border-radius:12px; max-height:360px; overflow:auto; }
    @media (max-width:900px){ main{padding:14px} header{display:block} h1{font-size:42px}.span3,.span4,.span5,.span6,.span7,.span8,.span12{grid-column:span 12}.row{grid-template-columns:1fr}.badge{display:inline-block;margin-top:14px} }
  </style>
</head>
<body>
<main>
  <header>
    <div><h1>HARBOR</h1><div class="tagline">When the network goes down, HARBOR stays up.</div></div>
    <div class="badge"><span class="ok">●</span> OFFLINE EMERGENCY COMMAND</div>
  </header>

  <section class="grid">
    <div class="card span3"><div class="label">System Status</div><div class="value" id="activeCount">0</div><div class="detail">Active Incidents</div></div>
    <div class="card span3"><div class="label">Critical</div><div class="value critical" id="criticalCount">0</div></div>
    <div class="card span3"><div class="label">Available Resources</div><div class="value ok" id="resourceCount">0</div></div>
    <div class="card span3"><div class="label">Field Nodes</div><div class="value blue" id="nodeCount">0</div></div>

    <div class="card span5">
      <h2>Report Incident</h2>
      <form id="incidentForm">
        <div class="row"><input name="category" placeholder="Emergency type e.g. MEDICAL" value="MEDICAL"><input name="people_affected" type="number" min="0" value="1" placeholder="People affected"></div><br>
        <textarea name="description" placeholder="Description">Tree blocking East Bay Street with one injured person</textarea><br><br>
        <div class="row"><input name="node_id" placeholder="Reporter/node" value="PHONE-1"><input name="location" placeholder="Location" value="East Bay Street"></div><br>
        <div class="row"><input name="latitude" placeholder="Latitude optional"><input name="longitude" placeholder="Longitude optional"></div><br>
        <button>Submit Report + AI Triage</button>
      </form>
    </div>

    <div class="card span7">
      <h2>Incident Priority Board</h2>
      <div id="incidentBoard" class="detail">Loading incidents...</div>
    </div>

    <div class="card span4">
      <h2>Resources</h2>
      <form id="resourceForm"><input name="name" placeholder="Resource name" value="Rescue Team Alpha"><br><br><div class="row"><input name="type" value="RESCUE"><select name="status"><option>AVAILABLE</option><option>ASSIGNED</option><option>OFFLINE</option></select></div><br><button>Add Resource</button></form>
      <div id="resources"></div>
    </div>

    <div class="card span4">
      <h2>Tasks</h2>
      <form id="taskForm"><input name="title" placeholder="Task title" value="Check East Bay alternate route"><br><br><div class="row"><select name="priority"><option>HIGH</option><option>CRITICAL</option><option>MEDIUM</option><option>LOW</option></select><input name="assigned_resource" placeholder="Assigned resource" value="Rescue Team Alpha"></div><br><button>Add Task</button></form>
      <div id="tasks"></div>
    </div>

    <div class="card span4">
      <h2>Field Nodes / LoRa Sim</h2>
      <button class="secondary" onclick="simulateMesh()">Inject Simulated LoRa Medical Packet</button><br><br>
      <div id="nodes"></div>
    </div>

    <div class="card span6">
      <h2>AI Commander Plan</h2>
      <input id="constraint" placeholder="Optional constraint" value="Only Rescue Team Alpha is available"><br><br>
      <button onclick="makePlan()">Generate/Reprioritize Action Plan</button>
      <pre id="plan">No plan generated yet.</pre>
    </div>

    <div class="card span6">
      <h2>Situation Briefing</h2>
      <button onclick="makeBriefing()">Generate 30-second Briefing</button>
      <pre id="briefing">No briefing generated yet.</pre>
    </div>
  </section>
</main>
<script>
const api = async (url, options={}) => {
  const res = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};
const formJson = form => Object.fromEntries([...new FormData(form).entries()].map(([k,v]) => [k, v === '' ? null : (['people_affected','latitude','longitude','capacity'].includes(k) && v !== null ? Number(v) : v)]));
function incidentHtml(i){ return `<div class="item ${i.severity}"><b>${i.severity}</b> <span class="pill">${i.category}</span> <span class="pill">${i.source}</span><br>${i.description}<br><small>${i.people_affected} affected · ${i.status} · ${new Date(i.timestamp).toLocaleString()}</small><br><b>Recommendation:</b> ${i.recommended_action || 'Pending'}</div>`; }
async function refresh(){
  const [incidents, resources, tasks, nodes] = await Promise.all([api('/api/incidents'), api('/api/resources'), api('/api/tasks'), api('/api/nodes')]);
  activeCount.textContent = incidents.filter(i => !['CLOSED','RESOLVED'].includes(i.status)).length;
  criticalCount.textContent = incidents.filter(i => i.severity === 'CRITICAL').length;
  resourceCount.textContent = resources.filter(r => r.status === 'AVAILABLE').length;
  nodeCount.textContent = nodes.length;
  incidentBoard.innerHTML = incidents.length ? incidents.map(incidentHtml).join('') : 'No incidents yet.';
  document.getElementById('resources').innerHTML = resources.map(r => `<div class="item LOW"><b>${r.name}</b><br>${r.type} · ${r.status}</div>`).join('') || '<p class="detail">No resources.</p>';
  document.getElementById('tasks').innerHTML = tasks.map(t => `<div class="item ${t.priority}"><b>${t.priority}</b> ${t.title}<br>${t.status} · ${t.assigned_resource || 'unassigned'}</div>`).join('') || '<p class="detail">No tasks.</p>';
  document.getElementById('nodes').innerHTML = nodes.map(n => `<div class="item MEDIUM"><b>${n.node_name}</b><br>${n.status} · battery ${n.battery ?? 'unknown'}%</div>`).join('') || '<p class="detail">No nodes yet.</p>';
}
document.getElementById('incidentForm').onsubmit = async e => { e.preventDefault(); await api('/api/incidents',{method:'POST', body:JSON.stringify(formJson(e.target))}); await refresh(); };
document.getElementById('resourceForm').onsubmit = async e => { e.preventDefault(); await api('/api/resources',{method:'POST', body:JSON.stringify(formJson(e.target))}); await refresh(); };
document.getElementById('taskForm').onsubmit = async e => { e.preventDefault(); await api('/api/tasks',{method:'POST', body:JSON.stringify(formJson(e.target))}); await refresh(); };
async function simulateMesh(){ await api('/api/mesh/message',{method:'POST', body:JSON.stringify({node:'NODE07', type:'MEDICAL', priority:'URGENT', lat:32.78, lon:-79.93, message:'One injured person reported over simulated LoRa'})}); await refresh(); }
async function makePlan(){ const p = await api('/api/ai/plan',{method:'POST', body:JSON.stringify({constraint:document.getElementById('constraint').value})}); plan.textContent = JSON.stringify(p, null, 2); }
async function makeBriefing(){ const b = await api('/api/ai/briefing',{method:'POST', body:'{}'}); briefing.textContent = b.briefing; }
refresh(); setInterval(refresh, 5000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def root() -> Response:
    # Never let browsers cache an outdated dashboard entry point.
    # Versioned Vite assets can still be cached independently.
    html = FRONTEND_INDEX.read_text() if FRONTEND_INDEX.exists() else DASHBOARD_HTML
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/sounds/find-my-iphone.mp3", include_in_schema=False)
def find_my_iphone_alarm():
    """Serve the operator-supplied sound copied into Vite's dist directory."""
    sound = FRONTEND_DIST / "sounds" / "find-my-iphone.mp3"
    if not sound.is_file():
        raise HTTPException(status_code=404, detail="Alarm sound not installed; build frontend after adding MP3")
    return FileResponse(sound, media_type="audio/mpeg")


@app.get("/manifest.webmanifest", include_in_schema=False)
def pwa_manifest():
    return FileResponse(FRONTEND_DIST / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    return FileResponse(FRONTEND_DIST / "service-worker.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/harbor-icon.svg", include_in_schema=False)
def harbor_icon():
    return FileResponse(FRONTEND_DIST / "harbor-icon.svg", media_type="image/svg+xml")


@app.get("/harbor-logo.svg", include_in_schema=False)
def harbor_logo():
    """Serve the wordmark generated by the frontend build."""
    return FileResponse(FRONTEND_DIST / "harbor-logo.svg", media_type="image/svg+xml")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "harbor-backend"}


@app.get("/api/system/status")
def system_status() -> dict[str, str]:
    return {
        "backend": "ONLINE",
        "database": "ONLINE" if database_is_online() else "OFFLINE",
        "ollama": "UNKNOWN",
        "lora": "SIMULATION_READY",
        "internet": "UNKNOWN",
    }


@app.get("/api/geocode", response_model=schemas.GeocodeResult)
def geocode(location: str):
    result = geocode_location(location) or geocode_text(None, location)
    if not result:
        raise HTTPException(status_code=404, detail="Location could not be geocoded")
    return result


@app.post("/api/incidents", response_model=schemas.IncidentRead)
def create_incident(payload: schemas.IncidentCreate, db: Session = Depends(get_db)):
    triage = ai.triage(payload.description, payload.category, payload.people_affected)
    geocoded = None
    if payload.latitude is None or payload.longitude is None:
        geocoded = geocode_text(payload.location, payload.description)
    latitude = payload.latitude if payload.latitude is not None else (geocoded or {}).get("latitude")
    longitude = payload.longitude if payload.longitude is not None else (geocoded or {}).get("longitude")
    ai_reasoning = str(triage.get("reason") or "")
    if geocoded:
        location_label = geocoded.get("location") or payload.location or "reported text"
        ai_reasoning = f"{ai_reasoning} Geocoded location '{location_label}' to {geocoded['latitude']}, {geocoded['longitude']}."
    incident = models.Incident(
        source=payload.source,
        water_depth_cm=payload.water_depth_cm,
        observed_at=payload.observed_at,
        node_id=payload.node_id,
        location=str((geocoded or {}).get("street_address") or payload.location or "")[:240] or None,
        latitude=latitude,
        longitude=longitude,
        category=str(triage.get("category") or payload.category).upper(),
        description=payload.description,
        severity=str(payload.severity or triage.get("severity") or "LOW").upper(),
        people_affected=int(triage.get("people_affected") or payload.people_affected or 0),
        status=payload.status,
        ai_reasoning=ai_reasoning,
        recommended_action=str(triage.get("recommended_action") or "Human commander review required."),
    )
    db.add(incident)
    db.flush()
    if incident.severity == 'CRITICAL' and incident.source != 'LORA_SIM':
        db.add(models.CriticalAlert(incident_id=incident.id))
    db.commit()
    db.refresh(incident)
    return incident


@app.get("/api/alerts/critical")
def critical_alerts(db: Session = Depends(get_db)):
    """Internal dashboard inbox, not external responder dispatch."""
    alerts = db.scalars(select(models.CriticalAlert).order_by(models.CriticalAlert.id.desc())).all()
    results = []
    for alert in alerts:
        incident = db.get(models.Incident, alert.incident_id)
        if incident is None:
            continue
        results.append({
            "id": alert.id, "incident_id": incident.id,
            "category": incident.category, "description": incident.description,
            "source": incident.source,
            "severity": incident.severity, "created_at": alert.created_at,
            "acknowledged_at": alert.acknowledged_at,
            "acknowledged_by": alert.acknowledged_by,
            "verified_at": alert.verified_at,
            "verified_by": alert.verified_by,
            "verification_evidence": alert.verification_evidence,
            "dispatch_status": alert.dispatch_status,
            "dispatch_operator": alert.dispatch_operator,
            "dispatch_reference": alert.dispatch_reference,
            "dispatch_updated_at": alert.dispatch_updated_at,
            "notification_scope": "HARBOR_DASHBOARD_ONLY",
        })
    return results


@app.post("/api/alerts/critical/{alert_id}/acknowledge")
def acknowledge_critical_alert(alert_id: int, operator: str = "Unspecified operator", db: Session = Depends(get_db)):
    alert = db.get(models.CriticalAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Critical alert not found")
    if alert.acknowledged_at is None:
        alert.acknowledged_at = models.utc_now()
        alert.acknowledged_by = operator.strip()[:120] or "Unspecified operator"
        db.commit()
    return {"id": alert.id, "incident_id": alert.incident_id, "acknowledged_at": alert.acknowledged_at, "acknowledged_by": alert.acknowledged_by}


from pydantic import BaseModel as _WorkflowModel, Field as _WorkflowField

class CriticalVerify(_WorkflowModel):
    operator: str = _WorkflowField(min_length=2, max_length=120)
    evidence: str = _WorkflowField(min_length=10, max_length=2000)

class DispatchRecord(_WorkflowModel):
    operator: str = _WorkflowField(min_length=2, max_length=120)
    reference: str = _WorkflowField(min_length=3, max_length=240)
    # Only document a dispatch authority's externally confirmed status.
    status: str


@app.post("/api/alerts/critical/{alert_id}/verify")
def verify_critical_alert(alert_id: int, payload: CriticalVerify, db: Session = Depends(get_db)):
    alert = db.get(models.CriticalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Critical alert not found")
    incident = db.get(models.Incident, alert.incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.severity != "CRITICAL":
        raise HTTPException(status_code=409, detail="Only CRITICAL incidents can use verification and dispatch workflow")
    if incident.source == "TEST" or "TEST ONLY" in incident.description.upper():
        raise HTTPException(status_code=400, detail="Simulation cannot be verified as a real emergency")
    if alert.verified_at is None:
        alert.verified_at = models.utc_now()
        alert.verified_by = payload.operator.strip()
        alert.verification_evidence = payload.evidence.strip()
        db.commit()
    return {"id": alert.id, "verified_at": alert.verified_at, "verified_by": alert.verified_by}


@app.post("/api/alerts/critical/{alert_id}/dispatch-record")
def record_external_dispatch(alert_id: int, payload: DispatchRecord, db: Session = Depends(get_db)):
    alert = db.get(models.CriticalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Critical alert not found")
    incident = db.get(models.Incident, alert.incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.severity != "CRITICAL":
        raise HTTPException(status_code=409, detail="Only CRITICAL incidents can use verification and dispatch workflow")
    if incident.source == "TEST" or "TEST ONLY" in incident.description.upper():
        raise HTTPException(status_code=400, detail="Cannot record real dispatch for a simulation")
    if alert.verified_at is None:
        raise HTTPException(status_code=409, detail="Operator verification must be recorded first")
    if payload.status not in {"REQUESTED_EXTERNALLY", "CONFIRMED_EXTERNALLY"}:
        raise HTTPException(status_code=422, detail="Invalid external dispatch record status")
    alert.dispatch_status = payload.status
    alert.dispatch_operator = payload.operator.strip()
    alert.dispatch_reference = payload.reference.strip()
    alert.dispatch_updated_at = models.utc_now()
    db.commit()
    return {"id": alert.id, "dispatch_status": alert.dispatch_status, "dispatch_reference": alert.dispatch_reference}


@app.get("/api/incidents", response_model=list[schemas.IncidentRead])
def list_incidents(db: Session = Depends(get_db)):
    return db.scalars(select(models.Incident).order_by(models.Incident.id.desc())).all()


@app.get("/api/incidents/{incident_id}", response_model=schemas.IncidentRead)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    incident = db.get(models.Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


def remove_record(db: Session, model: type, record_id: int, label: str) -> dict[str, int | bool]:
    record = db.get(model, record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    db.delete(record)
    db.commit()
    return {"removed": True, "id": record_id}


@app.delete("/api/incidents/{incident_id}")
def delete_incident(incident_id: int, db: Session = Depends(get_db)):
    # Keep the operator inbox consistent when a report is removed.
    for alert in db.scalars(select(models.CriticalAlert).where(models.CriticalAlert.incident_id == incident_id)).all():
        db.delete(alert)
    for packet in db.scalars(select(models.RealMeshPacket).where(models.RealMeshPacket.incident_id == incident_id)).all():
        db.delete(packet)
    db.flush()
    return remove_record(db, models.Incident, incident_id, "Incident")


@app.post("/api/resources", response_model=schemas.ResourceRead)
def create_resource(payload: schemas.ResourceCreate, db: Session = Depends(get_db)):
    resource = models.Resource(**payload.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


@app.get("/api/resources", response_model=list[schemas.ResourceRead])
def list_resources(db: Session = Depends(get_db)):
    return db.scalars(select(models.Resource).order_by(models.Resource.id.desc())).all()


@app.delete("/api/resources/{resource_id}")
def delete_resource(resource_id: int, db: Session = Depends(get_db)):
    return remove_record(db, models.Resource, resource_id, "Resource")


@app.post("/api/tasks", response_model=schemas.TaskRead)
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    task = models.Task(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.get("/api/tasks", response_model=list[schemas.TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    return db.scalars(select(models.Task).order_by(models.Task.id.desc())).all()


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    return remove_record(db, models.Task, task_id, "Task")


@app.post("/api/nodes", response_model=schemas.NodeRead)
def create_node(payload: schemas.NodeCreate, db: Session = Depends(get_db)):
    node = models.Node(**payload.model_dump(), last_seen=datetime.now(timezone.utc))
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@app.get("/api/nodes", response_model=list[schemas.NodeRead])
def list_nodes(db: Session = Depends(get_db)):
    nodes = db.scalars(select(models.Node).order_by(models.Node.id.desc())).all()
    cutoff = datetime.now(timezone.utc).timestamp() - 8
    for node in nodes:
        if node.node_name.startswith("MESHTASTIC ") and (
            node.last_seen is None or node.last_seen.replace(tzinfo=node.last_seen.tzinfo or timezone.utc).timestamp() < cutoff
        ):
            node.status = "OFFLINE"
    return nodes


@app.delete("/api/nodes/{node_id}")
def delete_node(node_id: int, db: Session = Depends(get_db)):
    return remove_record(db, models.Node, node_id, "Node")


@app.post("/api/ai/triage")
def triage_incident(payload: schemas.IncidentCreate):
    return ai.triage(payload.description, payload.category, payload.people_affected)


@app.post("/api/ai/plan")
def action_plan(payload: schemas.PlanRequest, db: Session = Depends(get_db)):
    incidents = db.scalars(select(models.Incident)).all()
    resources = db.scalars(select(models.Resource)).all()
    tasks = db.scalars(select(models.Task)).all()
    return ai.make_plan(incidents, resources, tasks, payload.constraint)


@app.post("/api/ai/briefing")
def briefing(payload: schemas.BriefingRequest, db: Session = Depends(get_db)):
    incidents = db.scalars(select(models.Incident)).all()
    resources = db.scalars(select(models.Resource)).all()
    return ai.make_briefing(incidents, resources)


@app.post("/api/mesh/message", response_model=schemas.IncidentRead)
def mesh_message(payload: schemas.MeshMessage, db: Session = Depends(get_db)):
    triage = ai.triage(payload.message, payload.type, 1 if "injur" in payload.message.lower() else 0)
    incident = models.Incident(
        source="LORA_SIM",
        water_depth_cm=payload.water_depth_cm,
        observed_at=payload.observed_at,
        node_id=payload.node,
        latitude=payload.lat,
        longitude=payload.lon,
        category=str(triage.get("category") or payload.type).upper(),
        description=payload.message,
        severity=str(triage.get("severity") or "LOW").upper(),
        people_affected=int(triage.get("people_affected") or 0),
        status="REPORTED",
        ai_reasoning=f"LoRa priority {payload.priority}. {triage.get('reason')}",
        recommended_action=str(triage.get("recommended_action") or "Human commander review required."),
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident
