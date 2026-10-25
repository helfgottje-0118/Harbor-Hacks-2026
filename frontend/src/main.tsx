import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import harborWordmark from './harbor-logo.svg';
import './harbor-chat.css';
import { HarborChat } from './HarborChat';
import { incidentTitle } from './incident-title';
import { OfflineMap, reportAge } from './map';

type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
type Incident = { water_depth_cm?:number|null; observed_at?:string|null; id:number; timestamp:string; source:string; node_id:string|null; location?:string|null; category:string; description:string; severity:Severity; people_affected:number; status:string; ai_reasoning:string|null; recommended_action:string|null; latitude?:number|null; longitude?:number|null };
type Resource = { latitude?:number|null; longitude?:number|null; id:number; name:string; type:string; status:string; location?:string|null; capacity?:number|null; notes?:string|null };
type Task = { id:number; title:string; priority:Severity; assigned_resource?:string|null; status:string; created_at:string; incident_id?:number|null };
type Node = { id:number; node_name:string; status:string; battery?:number|null; latitude?:number|null; longitude?:number|null; last_seen?:string|null };
type Status = { backend:string; database:string; ollama:string; lora:string; internet:string };
type CriticalAlert = { id:number; incident_id:number; category:string; description:string; severity:string; created_at:string; acknowledged_at:string|null; acknowledged_by?:string|null; source?:string; verified_at?:string|null; verified_by?:string|null; verification_evidence?:string|null; dispatch_status?:string|null; dispatch_operator?:string|null; dispatch_reference?:string|null; dispatch_updated_at?:string|null };

function confirmedDispatchMessage(alert:CriticalAlert):string {
  const verified = Boolean(alert.verified_at);
  return [
    'HARBOR: ⚠️ CRITICAL SAFETY ALERT',
    '',
    'This incident indicates potential immediate danger. For an ongoing emergency, call emergency services now.',
    '',
    'I can confirm from HARBOR records:',
    '- The report was filed as ticket #' + alert.incident_id + '.',
    '- An operator recorded external dispatch confirmation' + (alert.dispatch_reference ? ' (reference: ' + alert.dispatch_reference + ')' : '') + '.',
    '- Current situation status: NOT INDEPENDENTLY VERIFIED.',
    '',
    'The existing database entry (incident ID: ' + alert.incident_id + ') is ' +
      (verified ? 'marked verified by an operator based on recorded evidence; current field conditions remain unconfirmed.' : 'unverified user data, not verified operational information.'),
    '',
    'Review requirements:',
    '- Verify report details and preserve evidence inside HARBOR.',
    '- Do not rely on untrusted snapshots for decisions.',
    '- Treat hazard information as potentially inaccurate until corroborated.',
    '',
    'This message does not independently establish that responders arrived or that the scene is safe.',
    'For public safety, use official emergency channels.'
  ].join('\n');
}
function suggestedResponseService(category:string):string {
  switch(category.toUpperCase()) {
    case 'FIRE': return 'Fire / rescue';
    case 'MEDICAL': return 'EMS / medical';
    case 'FLOOD': return 'Emergency management / rescue';
    case 'INFRASTRUCTURE': return 'Public works / incident command';
    case 'SHELTER': return 'Emergency management / shelter coordination';
    default: return 'Emergency operations operator';
  }
}

type RemovableKind = 'incidents' | 'resources' | 'tasks' | 'nodes';
type SeverityFilter = Severity | 'ALL';

const severityOrder: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

async function api<T>(url:string, init:RequestInit = {}): Promise<T> {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...init });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function metric(label:string, value:React.ReactNode, tone = '') {
  return <section className="metric"><span>{label}</span><strong className={tone}>{value}</strong></section>;
}

export function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [criticalAlerts, setCriticalAlerts] = useState<CriticalAlert[]>([]);
  const [operatorName, setOperatorName] = useState('');
  const [verificationEvidence, setVerificationEvidence] = useState('');
  const [dispatchReference, setDispatchReference] = useState('');
  const [alarmEnabled, setAlarmEnabled] = useState(false);
  const [showAlertHistory, setShowAlertHistory] = useState(false);
  const knownAlerts = useRef<Set<number> | null>(null);
  const alarmEnabledRef = useRef(false);
  const pendingDispatchRef = useRef(0);
  const alarmTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const alarmAudio = useRef<HTMLAudioElement | null>(null);
  const stopRepeatingAlarm = () => {
    alarmAudio.current?.pause();
    if (alarmAudio.current) alarmAudio.current.currentTime = 0;
    if (alarmTimer.current !== null) {
      clearInterval(alarmTimer.current);
      alarmTimer.current = null;
    }
  };
  // Safari-compatible single-pitch repeating PCM WAV alarm. A real HTML audio element is used instead
  // of relying solely on WebAudio oscillators, which can be silent in some setups.
  const ensureAlarmAudio = () => {
    if (alarmAudio.current) return alarmAudio.current;
    // Never silently substitute the old synthesized beep.
    const audio = new Audio('/sounds/find-my-iphone.mp3');
    audio.preload = 'auto';
    audio.addEventListener('error', () => {
      alarmEnabledRef.current = false;
      setAlarmEnabled(false);
      setNotice('Find My alarm MP3 failed to load. Check /sounds/find-my-iphone.mp3 and rebuild the frontend.');
    });
    audio.loop = true;
    audio.volume = 1;
    alarmAudio.current = audio;
    return audio;
  };
  const playCriticalTone = () => {
    if (pendingDispatchRef.current <= 0) return;
    const audio = ensureAlarmAudio();
    if (!audio.paused) return;
    void audio.play().catch(() => {
      alarmEnabledRef.current = false;
      setAlarmEnabled(false);
      setNotice('Safari blocked alarm playback. Click Enable / Test alarm sound and check your Mac audio output.');
    });
  };
  // Resume audible warnings after tab visibility changes. Browser throttling
  // may pause timers in inactive tabs; this is not a background alarm service.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState !== 'visible' || !alarmEnabledRef.current || pendingDispatchRef.current === 0) return;
      playCriticalTone();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);
  // Safari requires audio.play() within the actual click/key gesture.
  // Do not await AudioContext.resume() first: that loses user activation.
  useEffect(() => {
    const unlock = () => {
      if (alarmEnabledRef.current) return;
      const audio = ensureAlarmAudio();
      const attempt = audio.play();
      void attempt.then(() => {
        alarmEnabledRef.current = true;
        setAlarmEnabled(true);
        if (pendingDispatchRef.current === 0) {
          audio.pause();
          audio.currentTime = 0;
        }
      }).catch(() => {
        alarmEnabledRef.current = false;
        setAlarmEnabled(false);
      });
    };
    document.addEventListener('pointerdown', unlock, {capture:true});
    document.addEventListener('keydown', unlock, {capture:true});
    return () => {
      document.removeEventListener('pointerdown', unlock, true);
      document.removeEventListener('keydown', unlock, true);
    };
  }, []);
  const [alertError, setAlertError] = useState('');
  const [status, setStatus] = useState<Status | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string|null>(null);
  const [refreshError, setRefreshError] = useState('');
  const [plan, setPlan] = useState('No action plan generated yet.');
  const [briefing, setBriefing] = useState('No situation briefing generated yet.');
  const [notice, setNotice] = useState('Dashboard ready.');
  const [constraint, setConstraint] = useState('Only Rescue Team Alpha is available');
  const [query, setQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('ALL');
  const [removing, setRemoving] = useState<string | null>(null);
  const [incidentDescription, setIncidentDescription] = useState('Tree blocking East Bay Street with one injured person');
  const [incidentLocation, setIncidentLocation] = useState('');
  const [incidentLatitude, setIncidentLatitude] = useState('');
  const [incidentLongitude, setIncidentLongitude] = useState('');

  const refresh = async () => {
   try {
    const [statusData, incidentData, resourceData, taskData, nodeData] = await Promise.all([
      api<Status>('/api/system/status'),
      api<Incident[]>('/api/incidents'),
      api<Resource[]>('/api/resources'),
      api<Task[]>('/api/tasks'),
      api<Node[]>('/api/nodes'),
    ]);
    setStatus(statusData);
    setIncidents(incidentData.filter(item => item.source !== 'LORA_SIM'));
    setResources(resourceData);
    setTasks(taskData);
    setNodes(nodeData);
    try {
      const incoming = await api<CriticalAlert[]>('/api/alerts/critical');
      const nextIds = new Set(incoming.map(a => a.id));
      const pendingCount = incoming.filter(a => a.source !== 'TEST' && !a.verified_at).length;
      pendingDispatchRef.current = pendingCount;
      if (alarmEnabledRef.current && pendingCount > 0 && alarmTimer.current === null) {
        playCriticalTone();
        alarmTimer.current = setInterval(playCriticalTone, 1700);
      } else if (pendingCount === 0) {
        stopRepeatingAlarm();
      }
      knownAlerts.current = nextIds;
      setCriticalAlerts(incoming);
      setAlertError('');
    }
    catch { setAlertError('Critical alert inbox unavailable.'); }
    setLastUpdate(new Date().toLocaleString());
    setRefreshError('');
   } catch (error) {
    setRefreshError(error instanceof Error ? error.message : String(error));
    throw error;
   }
  };

  useEffect(() => {
    refresh().catch(err => setNotice(err.message));
    const id = setInterval(() => refresh().catch(() => {}), 5000);
    // Keep field-node presence responsive independently of slower incident polling.
    const nodePoll = setInterval(() => {
      api<Node[]>('/api/nodes').then(setNodes).catch(() => {});
    }, 1000);
    const onIncidentCreated = () => { refresh().catch(() => {}); };
    window.addEventListener('harbor:incident-created', onIncidentCreated);
    return () => {
      clearInterval(id);
      clearInterval(nodePoll);
      window.removeEventListener('harbor:incident-created', onIncidentCreated);
    };
  }, []);

  const counts = useMemo(() => ({
    active: incidents.filter(i => !['CLOSED','RESOLVED'].includes(i.status)).length,
    critical: incidents.filter(i => i.severity === 'CRITICAL').length,
    available: resources.filter(r => r.status === 'AVAILABLE').length,
    nodes: nodes.filter(n => n.status === 'ONLINE').length,
  }), [incidents, resources, nodes]);

  // Display numbers describe current visible reports; immutable IDs remain for audit/actions.
  const reportNumbers = useMemo(() => new Map(
    [...incidents].sort((a, b) => a.id - b.id).map((item, index) => [item.id, index + 1])
  ), [incidents]);

  const filteredIncidents = useMemo(() => {
    const term = query.trim().toLowerCase();
    return incidents.filter(incident => {
      const severityMatches = severityFilter === 'ALL' || incident.severity === severityFilter;
      if (!severityMatches) return false;
      if (!term) return true;
      return [
        incident.id.toString(), incident.category, incident.description, incident.source,
        incident.node_id ?? '', incident.status, incident.recommended_action ?? '', incident.ai_reasoning ?? '',
      ].join(' ').toLowerCase().includes(term);
    });
  }, [incidents, query, severityFilter]);
  const timeline = useMemo(() => [
    ...incidents.map(item => ({key:`incident-${item.id}`,time:item.timestamp,type:'REPORT',tone:item.severity,title:incidentTitle(item.description,item.category),meta:`Report ${reportNumbers.get(item.id) ?? item.id} (ID ${item.id}) · ${item.category} · ${item.status}`})),
    ...tasks.map(item => ({key:`task-${item.id}`,time:item.created_at,type:'TASK',tone:item.priority,title:item.title,meta:`${item.status} · ${item.assigned_resource || 'unassigned'}`})),
  ].sort((a,b) => Date.parse(b.time)-Date.parse(a.time)).slice(0,50), [incidents,tasks,reportNumbers]);
  const selectMapLocation = useCallback((latitude:number, longitude:number) => {
    setIncidentLatitude(latitude.toFixed(6));
    setIncidentLongitude(longitude.toFixed(6));
    setNotice(`Map location selected: ${latitude.toFixed(5)}, ${longitude.toFixed(5)}.`);
  }, []);

  const submitIncident = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api<Incident>('/api/incidents', { method:'POST', body: JSON.stringify({
      category: form.get('category'),
      description: incidentDescription,
      people_affected: Number(form.get('people_affected') || 0),
      node_id: form.get('node_id'),
      source: 'WEB',
      water_depth_cm: form.get('water_depth_cm') === '' ? null : Number(form.get('water_depth_cm')),
      location: incidentLocation || null,
      latitude: incidentLatitude ? Number(incidentLatitude) : null,
      longitude: incidentLongitude ? Number(incidentLongitude) : null,
    })});
    setNotice('Incident saved, triaged, and posted to the priority board.');
    await refresh();
  };

  const submitResource = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    await api('/api/resources', { method:'POST', body: JSON.stringify({ name:f.get('name'), type:f.get('type'), status:f.get('status'), location:f.get('location'), capacity:Number(f.get('capacity') || 0), latitude:f.get('latitude') ? Number(f.get('latitude')) : null, longitude:f.get('longitude') ? Number(f.get('longitude')) : null }) });
    setNotice('Resource added.');
    await refresh();
  };

  const submitTask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    await api('/api/tasks', { method:'POST', body: JSON.stringify({ title:f.get('title'), priority:f.get('priority'), assigned_resource:f.get('assigned_resource'), status:'OPEN' }) });
    setNotice('Task added.');
    await refresh();
  };

  const generatePlan = async () => {
    const p = await api<object>('/api/ai/plan', { method:'POST', body: JSON.stringify({ constraint }) });
    setPlan(JSON.stringify(p, null, 2));
  };

  const generateBriefing = async () => {
    const b = await api<{briefing:string}>('/api/ai/briefing', { method:'POST', body: '{}' });
    setBriefing(b.briefing);
  };

  const lookupCoordinates = async () => {
    const lookupText = incidentLocation.trim() || incidentDescription.trim();
    if (!lookupText) {
      setNotice('Enter a street address or report description before looking up coordinates.');
      return;
    }
    const result = await api<{latitude:number; longitude:number; display_name:string; street_address:string; provider:string}>(`/api/geocode?location=${encodeURIComponent(lookupText)}`);
    setIncidentLatitude(result.latitude.toString());
    setIncidentLongitude(result.longitude.toString());
    setIncidentLocation(result.street_address || result.display_name);
    setNotice(`Resolved place/address with ${result.provider}: ${result.street_address || result.display_name} (${result.latitude.toFixed(5)}, ${result.longitude.toFixed(5)})`);
  };

  // Clean up any repeating sound when the operator leaves this dashboard.
  useEffect(() => () => {
    if (alarmTimer.current !== null) clearInterval(alarmTimer.current);
    alarmAudio.current?.pause();
    if (alarmAudio.current) URL.revokeObjectURL(alarmAudio.current.src);
  }, []);

  const verifyAlert = async (id:number) => {
    if (!operatorName.trim() || verificationEvidence.trim().length < 10) {
      setAlertError('Enter the verifying operator and evidence (at least 10 characters).');
      return;
    }
    try {
      await api(`/api/alerts/critical/${id}/verify`, {method:'POST', body:JSON.stringify({operator:operatorName.trim(),evidence:verificationEvidence.trim()})});
      setVerificationEvidence('');
      await refresh();
    } catch (err) { setAlertError(err instanceof Error ? err.message : 'Verification failed'); }
  };
  const recordDispatch = async (id:number, status:'REQUESTED_EXTERNALLY'|'CONFIRMED_EXTERNALLY') => {
    if (!operatorName.trim() || dispatchReference.trim().length < 3) {
      setAlertError('Enter operator name and the real external dispatch reference.');
      return;
    }
    try {
      await api(`/api/alerts/critical/${id}/dispatch-record`, {method:'POST', body:JSON.stringify({operator:operatorName.trim(),reference:dispatchReference.trim(),status})});
      setDispatchReference('');
      await refresh();
    } catch (err) { setAlertError(err instanceof Error ? err.message : 'Dispatch record failed'); }
  };
  const acknowledgeAlert = async (id:number) => {
    try { await api(`/api/alerts/critical/${id}/acknowledge?operator=${encodeURIComponent(operatorName.trim() || 'Unspecified operator')}`, {method:'POST'}); await refresh(); }
    catch { setAlertError('Could not acknowledge alert.'); }
  };

  const removeItem = async (kind:RemovableKind, id:number, label:string) => {
    const key = `${kind}:${id}`;
    if (removing !== key) {
      setRemoving(key);
      setNotice(`Click Remove again to confirm deleting ${label}.`);
      return;
    }
    await api(`/api/${kind}/${id}`, { method: 'DELETE' });
    setRemoving(null);
    setNotice(`${label} removed from HARBOR.`);
    await refresh();
  };

  const removeText = (kind:RemovableKind, id:number) => removing === `${kind}:${id}` ? 'Confirm' : 'Remove';

  return <main>
    <header className="hero">
      <div className="hero-brand">
        <img className="harbor-brand-logo" src={harborWordmark} alt="HARBOR" width="420" height="128" />
        <p className="eyebrow">OFFLINE EMERGENCY COMMAND</p>
        <p className="tagline">Human + Autonomous Resilience Beyond Online Reach</p>
      </div>
      <div className="statusPanel">
        <b>Emergency Ops Console</b>
        <span>Backend {status?.backend ?? '...'}</span>
        <span>DB {status?.database ?? '...'}</span>
        <span>Ollama {status?.ollama ?? 'UNKNOWN'}</span>

      </div>
    </header>

    <section className="metrics">
      {metric('Active Incidents', counts.active)}
      {metric('Critical', counts.critical, 'critical')}
      {metric('Available Resources', counts.available, 'ok')}
      {metric('Field Nodes', counts.nodes, 'blue')}
    </section>
    <div className="notice">{notice}</div>
    <section className="panel critical-alerts" aria-labelledby="critical-alerts-heading">
      <div className="boardHeader"><div><h2 id="critical-alerts-heading">Critical Alerts · Operator Inbox</h2><p>Unverified critical incidents trigger a repeating audible operator alert until human verification is recorded. HARBOR suggests an appropriate response service, but does not automatically notify or dispatch that agency.</p></div><strong>{criticalAlerts.filter(alert => alert.source !== 'TEST' && !alert.verified_at).length} awaiting human verification</strong></div>
      <div className="critical-alert-controls">
        <strong role="status">{alarmEnabled ? 'Alarm audio engine ready (check speaker volume)' : 'Alarm audio needs activation in this browser'}</strong>
        <button type="button" onClick={() => {
          // Call play() directly during the user gesture, without awaiting
          // any promise first. This is necessary for Safari autoplay policy.
          const audio = ensureAlarmAudio();
          void audio.play().then(() => {
            alarmEnabledRef.current = true;
            setAlarmEnabled(true);
            if (pendingDispatchRef.current === 0) {
              window.setTimeout(() => {
                if (pendingDispatchRef.current === 0) {
                  audio.pause();
                  audio.currentTime = 0;
                }
              }, 1600);
            }
            setNotice(pendingDispatchRef.current
              ? 'Alarm playback started; repeats until human verification.'
              : 'Alarm test started. Check your speakers.');
          }).catch((error: unknown) => {
            alarmEnabledRef.current = false;
            setAlarmEnabled(false);
            setNotice('Safari rejected audio playback: ' + String(error));
          });
        }}>Enable / Test alarm sound</button>
        <label>Operator name (self-reported)<input value={operatorName} onChange={e => setOperatorName(e.target.value)} maxLength={120} placeholder="Name for acknowledgment log" /></label>
        <button type="button" className="secondary" onClick={() => setShowAlertHistory(v => !v)}>{showAlertHistory ? 'Hide history' : 'Show alert history'}</button>
      </div>
      <p className="alert-help">The single-tone beep repeats approximately every second until every real critical incident has human verification recorded. Acknowledging an alert does not stop it. Training-only reports do not drive this alarm. Verification is not the same as dispatch confirmation. Safari may require this initial interaction. Closing the tab also stops audio. This tab must remain open. A report receipt, suggested response service, or acknowledgment does not mean responders were contacted or dispatched.</p>
      {alertError && <p role="alert">{alertError}</p>}
      {criticalAlerts.length === 0 && <p>No critical alerts recorded. Open dashboards check for alerts every five seconds.</p>}
      <div className="critical-alert-list">{criticalAlerts.filter(alert => showAlertHistory || (alert.source !== 'TEST' && (!alert.verified_at || alert.dispatch_status !== 'CONFIRMED_EXTERNALLY'))).map(alert =>
        <article className="critical-alert-card" key={alert.id}>
          <strong>{alert.source === 'TEST' ? 'TEST ONLY · Simulated Critical' : 'Critical'} · Ticket ID {alert.incident_id} · {alert.category}</strong>
          <p>{incidentTitle(alert.description,alert.category)}</p>
          <small>Received {new Date(alert.created_at).toLocaleString()} · {alert.acknowledged_at ? 'Acknowledged in HARBOR' : 'Awaiting operator acknowledgment'}</small>
          {alert.acknowledged_at && <small>Acknowledgment log: {alert.acknowledged_by || 'Operator unspecified'} · {new Date(alert.acknowledged_at).toLocaleString()} (self-reported identity)</small>}
          <small>Verification: {alert.verified_at ? `VERIFIED by ${alert.verified_by} on ${new Date(alert.verified_at).toLocaleString()}` : 'UNVERIFIED'}</small>
          {alert.verification_evidence && <small>Recorded verification evidence: {alert.verification_evidence}</small>}
          <small>Internal notification: RECEIVED IN HARBOR · Suggested service: {suggestedResponseService(alert.category)} · Awaiting operator routing</small>
          <small>External dispatch: {alert.dispatch_status || 'NOT_REQUESTED'} {alert.dispatch_reference ? `· Reference: ${alert.dispatch_reference}` : ''}</small>
          {alert.dispatch_status === 'CONFIRMED_EXTERNALLY' && <div className="critical-workflow">
            <strong>Post-dispatch follow-up (not yet sent)</strong>
            <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{confirmedDispatchMessage(alert)}</pre>
            <button type="button" onClick={() => navigator.clipboard.writeText(confirmedDispatchMessage(alert)).catch(() => setAlertError('Could not copy follow-up message.'))}>Copy dispatch follow-up</button>
            <small>HARBOR has not sent this by Photon. Send only after checking the agency confirmation and intended recipient.</small>
          </div>}
          {alert.source !== 'TEST' && !alert.verified_at && <div className="critical-workflow"><label>Verification evidence<textarea value={verificationEvidence} onChange={e=>setVerificationEvidence(e.target.value)} placeholder="Who confirmed this and how?"/></label><button type="button" onClick={()=>verifyAlert(alert.id)}>Record human verification</button></div>}
          {alert.source !== 'TEST' && <div className="critical-workflow">
            <strong>External dispatch workflow</strong>
            {!alert.verified_at && <small>Complete human verification with real evidence first. These controls do not send a request to any agency.</small>}
            <label>External dispatch authority / case reference<input value={dispatchReference} onChange={e=>setDispatchReference(e.target.value)} placeholder="Agency and actual incident/reference number" disabled={!alert.verified_at} /></label>
            <button type="button" disabled={!alert.verified_at || alert.dispatch_status === 'REQUESTED_EXTERNALLY' || alert.dispatch_status === 'CONFIRMED_EXTERNALLY'} onClick={()=>recordDispatch(alert.id,'REQUESTED_EXTERNALLY')}>Record external dispatch request</button>
            <button type="button" disabled={!alert.verified_at || alert.dispatch_status === 'CONFIRMED_EXTERNALLY'} onClick={()=>recordDispatch(alert.id,'CONFIRMED_EXTERNALLY')}>Record externally confirmed dispatch</button>
          </div>}
          {!alert.acknowledged_at && <button type="button" onClick={() => acknowledgeAlert(alert.id)}>Acknowledge alert</button>}
        </article>
      )}</div>
    </section>


    <div className="update-status" aria-live="polite"><p>Last successful update: {lastUpdate ?? 'none yet'}. Polling local server every 5 seconds; not a live water feed.</p>{refreshError && <p role="alert">Refresh failed: {refreshError}. Displayed reports may be out of date.</p>}</div>
    <OfflineMap incidents={incidents.map(item => ({...item, display_number: reportNumbers.get(item.id) ?? item.id}))} resources={resources} onLocationSelect={selectMapLocation} />
    <section className="panel timeline-panel" aria-labelledby="timeline-heading"><div className="boardHeader"><div><h2 id="timeline-heading">Command Timeline</h2><p>Newest operational reports and assignments</p></div><span className="offline-badge">Local history</span></div><div className="timeline">{timeline.length === 0 && <div className="empty">No command activity yet.</div>}{timeline.map(item => <article className={`timeline-item ${item.tone}`} key={item.key}><time dateTime={item.time}>{new Date(item.time).toLocaleString()}</time><div><b>{item.type}</b><p>{item.title}</p><small>{item.meta}</small></div></article>)}</div></section>
    <section className="layout">
      <div className="panel report"><h2>Report Incident</h2><form onSubmit={submitIncident}>
        <div className="two"><input name="category" defaultValue="MEDICAL" placeholder="Emergency type"/><input name="people_affected" type="number" defaultValue="1"/></div>
        <textarea name="description" value={incidentDescription} onChange={e => setIncidentDescription(e.target.value)} />
        <div className="two"><input name="node_id" defaultValue="PHONE-1"/><input value={incidentLocation} onChange={e => setIncidentLocation(e.target.value)} placeholder="Street/place optional; inferred from description if blank"/></div>
        <button type="button" className="secondary full" onClick={lookupCoordinates}>Auto-fill coordinates from address</button>
        <div className="two"><input value={incidentLatitude} onChange={e => setIncidentLatitude(e.target.value)} placeholder="Latitude auto-filled"/><input value={incidentLongitude} onChange={e => setIncidentLongitude(e.target.value)} placeholder="Longitude auto-filled"/></div><label>Reported water depth (cm, optional)<input name="water_depth_cm" type="number" min="0" step="any" placeholder="Unknown if blank" /></label><button>Submit + Auto Triage</button>
      </form></div>

      <div className="panel board">
        <div className="boardHeader">
          <div><h2>Incident Priority Board</h2><p>{filteredIncidents.length} shown / {incidents.length} total</p></div>
          <button className="secondary" onClick={() => refresh().then(() => setNotice('Dashboard refreshed.')).catch(() => {})}>Refresh</button>
        </div>
        <div className="controls">
          <input aria-label="Search incidents" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by ID, category, node, description, action..." />
          <select aria-label="Filter severity" value={severityFilter} onChange={e => setSeverityFilter(e.target.value as SeverityFilter)}>
            <option value="ALL">All severities</option>
            {severityOrder.map(level => <option key={level} value={level}>{level}</option>)}
          </select>
        </div>
        {severityOrder.map(level => {
          const laneIncidents = filteredIncidents.filter(i => i.severity === level);
          return <div key={level} className="lane">
            <h3>{level} <span>{laneIncidents.length}</span></h3>
            {laneIncidents.length === 0 && <div className="empty">No {level.toLowerCase()} incidents match the current filter.</div>}
            {laneIncidents.map(i => <article className={`incident ${level}`} key={i.id}>
              <div className="cardTop"><b>Report {reportNumbers.get(i.id) ?? i.id} · {incidentTitle(i.description,i.category)} <small>(ID {i.id})</small></b><button className="remove" onClick={() => removeItem('incidents', i.id, `Incident #${i.id}`)}>{removeText('incidents', i.id)}</button></div>
              <p>{i.description}</p>
              {i.location && <p className="incident-location"><strong>Location:</strong> {i.location}</p>}
              <small>{i.people_affected} affected · {i.source === 'LORA_REAL' ? 'LORA' : i.source} · {i.status} · {new Date(i.timestamp).toLocaleString()}</small>
              <small>{reportAge(i)} · Reported water depth: {i.water_depth_cm == null ? 'unknown' : `${i.water_depth_cm} cm`}{i.observed_at && ` · Observed: ${i.observed_at}`}</small>
              <div><strong>AI Recommendation:</strong> {i.recommended_action}</div>
              {typeof i.latitude === 'number' && typeof i.longitude === 'number' && <a className="mapLink" href="#map-heading">View offline map · coordinates ({i.latitude.toFixed(5)}, {i.longitude.toFixed(5)})</a>}
            </article>)}
          </div>;
        })}
      </div>

      <div className="panel"><h2>Resources</h2><form onSubmit={submitResource}><input name="name" defaultValue="Rescue Team Alpha"/><div className="two"><input name="type" defaultValue="RESCUE"/><select name="status" defaultValue="AVAILABLE"><option>AVAILABLE</option><option>ASSIGNED</option><option>OFFLINE</option></select></div><input name="location" defaultValue="HQ"/><input name="capacity" type="number" defaultValue="4"/><div className="two"><label>Resource latitude<input name="latitude" type="number" min="-90" max="90" step="any" /></label><label>Resource longitude<input name="longitude" type="number" min="-180" max="180" step="any" /></label></div><button>Add Resource</button></form>{resources.map(r => <div className="mini" key={r.id}><div className="cardTop"><b>{r.name}</b><button className="remove" onClick={() => removeItem('resources', r.id, r.name)}>{removeText('resources', r.id)}</button></div><span>{r.type} · {r.status}</span></div>)}</div>
      <div className="panel"><h2>Tasks</h2><form onSubmit={submitTask}><input name="title" defaultValue="Check East Bay alternate route"/><div className="two"><select name="priority" defaultValue="HIGH"><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select><input name="assigned_resource" defaultValue="Rescue Team Alpha"/></div><button>Add Task</button></form>{tasks.map(t => <div className={`mini ${t.priority}`} key={t.id}><div className="cardTop"><b>{t.priority}</b><button className="remove" onClick={() => removeItem('tasks', t.id, t.title)}>{removeText('tasks', t.id)}</button></div><span>{t.title}</span></div>)}</div>
      <div className="panel"><h2>Field Nodes</h2>{nodes.length === 0 && <div className="empty">No nodes registered yet. Start the Mac Meshtastic gateway with a valid HARBOR_MESH_GATEWAY_TOKEN to register the connected radio.</div>}{nodes.map(n => <div className="mini" key={n.id}><div className="cardTop"><b>{n.node_name}</b><button className="remove" onClick={() => removeItem('nodes', n.id, n.node_name)}>{removeText('nodes', n.id)}</button></div><span><strong>{n.status === 'ONLINE' ? '● ONLINE' : n.status === 'OFFLINE' ? '○ OFFLINE' : n.status}</strong> · {n.status === 'ONLINE' ? 'Gateway heartbeat active' : 'Previously registered; no recent heartbeat'}</span><small>Last seen: {n.last_seen ? new Date(n.last_seen.endsWith('Z') || /[+-]\d\d:\d\d$/.test(n.last_seen) ? n.last_seen : n.last_seen + 'Z').toLocaleString() : 'Never'} · Last known battery: {n.battery == null ? 'Unknown' : n.battery + '%'}</small></div>)}</div>
      <div className="panel wide"><h2>AI Commander</h2><input value={constraint} onChange={e => setConstraint(e.target.value)} /><button onClick={generatePlan}>Generate/Reprioritize Plan</button><pre>{plan}</pre></div>
      <div className="panel wide"><h2>Situation Briefing</h2><button onClick={generateBriefing}>Generate 30-second Briefing</button><pre>{briefing}</pre></div>
    </section>
    <HarborChat />
  </main>;
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<App />);
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/service-worker.js').catch(() => {}));
}
