import { FormEvent, useState } from 'react';

type Entry = { role: 'user' | 'assistant'; content: string };
type Draft = { description: string; category: string; location: string; people_affected: number; incident_datetime?: string; datetime_assumed?: boolean; summary?: string; actions_taken?: string; potential_hazards?: string; next_steps?: string };

export function HarborChat() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState<Draft | null>(null);
  const [reportStatus, setReportStatus] = useState('');

  const suggestReport = async () => {
    if (!messages.some(entry => entry.role === 'user')) {
      setError('Describe the situation in chat first, then draft a report.');
      return;
    }
    setBusy(true);
    setError('');
    setReportStatus('');
    try {
      const response = await fetch('/api/ai/report-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: messages.slice(-24) }),
      });
      if (!response.ok) throw new Error('Unable to draft report. Please try again.');
      const result: Draft & { location_resolved: boolean } = await response.json();
      setReport(result);
      setReportStatus(result.location_resolved
        ? 'Address found in HARBOR location data. Review the exact location before saving.'
        : 'Please verify or enter a location before saving.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to prepare report.');
    } finally {
      setBusy(false);
    }
  };

  const saveReport = async () => {
    if (!report || busy) return;
    setBusy(true);
    setError('');
    setReportStatus('');
    try {
      const response = await fetch('/api/incidents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: [
            report.description,
            report.summary ? 'Summary: ' + report.summary : '',
            report.incident_datetime ? 'Incident time: ' + report.incident_datetime + (report.datetime_assumed ? ' (submission-time default; incident time unverified)' : '') : '',
            report.actions_taken ? 'Actions taken (reported): ' + report.actions_taken : '',
            report.potential_hazards ? 'Potential hazards (unverified): ' + report.potential_hazards : '',
            report.next_steps ? 'Suggested next steps (not verified actions): ' + report.next_steps : '',
          ].filter(Boolean).join('\n'),
          category: report.category,
          location: report.location || null,
          people_affected: report.people_affected,
          source: 'WEB',
          status: 'REPORTED',
        }),
      });
      if (!response.ok) {
        let detail = '';
        try {
          const payload = await response.json();
          detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail ?? '');
        } catch { /* An upstream proxy may return non-JSON. */ }
        throw new Error(`Could not save report (HTTP ${response.status})${detail ? ': ' + detail.slice(0, 350) : ''}. Nothing was confirmed saved.`);
      }
      const incident: {id:number} = await response.json();
      const incidentListResponse = await fetch('/api/incidents');
      let displayNumber: number | null = null;
      if (incidentListResponse.ok) {
        const records: Array<{ id: number; source: string }> = await incidentListResponse.json();
        const visible = records.filter(item => item.source !== 'LORA_SIM').sort((a, b) => a.id - b.id);
        const ordinal = visible.findIndex(item => item.id === incident.id);
        if (ordinal >= 0) displayNumber = ordinal + 1;
      }
      setReport(null);
      const label = displayNumber === null ? `Incident ID ${incident.id}` : `Report ${displayNumber} (incident ID ${incident.id})`;
      const receipt = `${label} saved to HARBOR. Responder notification status: not verified. HARBOR has no dispatch acknowledgment. If anyone is in immediate danger, contact local emergency services directly.`;
      setReportStatus(receipt);
      setMessages(prev => [...prev, {role:'assistant', content:receipt}]);
      window.dispatchEvent(new Event('harbor:incident-created'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save report.');
    } finally {
      setBusy(false);
    }
  };

  const submitReport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await saveReport();
  };

  const send = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message || busy) return;
    // Only an explicit HARBOR CRITICAL command submits without a second confirmation.
    // Plain conversational mentions of emergencies still require review.
    if (/^\/?harbor critical(?:\s|$)/i.test(message)) {
      setDraft('');
      const content = message.replace(/^\/?harbor critical\s*/i, '').trim();
      if (!content) {
        setError('Describe the incident, for example: /harbor critical fire at Harborwalk, Charleston SC. Heavy smoke reported.');
        return;
      }
      const isTest = /\b(?:test only|simulat(?:ed|ion)|training exercise|drill)\b/i.test(content);
      const category = /\b(fire|smoke|flames|burning)\b/i.test(content) ? 'FIRE'
        : /\b(flood|flooding|water rising)\b/i.test(content) ? 'FLOOD'
        : /\b(medical|injured|unconscious|not breathing)\b/i.test(content) ? 'MEDICAL'
        : /\b(power outage|bridge collapse|infrastructure|road collapse)\b/i.test(content) ? 'INFRASTRUCTURE'
        : /\b(shelter|evacuation center)\b/i.test(content) ? 'SHELTER' : 'GENERAL';
      // Use only an explicitly provided location. Never infer an address.
      const locationMatch = content.match(/\b(?:at|near|located at)\s+([^.!?;]+?)(?=\s*[,;.]|$)/i);
      const location = locationMatch?.[1]?.trim() || null;
      const description = isTest && !/\bTEST ONLY\b/i.test(content)
        ? 'TEST ONLY — SIMULATED INCIDENT. ' + content : content;
      setBusy(true);
      setError('');
      try {
        const response = await fetch('/api/incidents', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            source:isTest ? 'TEST' : 'WEB', severity:'CRITICAL', status:'REPORTED',
            category:category.toUpperCase(), location, description,
            people_affected:0,
          }),
        });
        if (!response.ok) throw new Error('Could not submit critical report (HTTP ' + response.status + ')');
        const saved:{id:number} = await response.json();
        const receipt = `${isTest ? 'TEST ONLY — simulated ' : ''}HARBOR CRITICAL ticket ID ${saved.id} submitted as UNVERIFIED from ${isTest ? 'TEST' : 'WEB'}. Operator inbox notified within HARBOR; no emergency responders dispatched. For immediate danger call emergency services.`;
        setMessages(prev=>[...prev,{role:'user',content:message},{role:'assistant',content:receipt}]);
        window.dispatchEvent(new Event('harbor:incident-created'));
      } catch(err) {
        setError(err instanceof Error ? err.message : 'Critical report submission failed.');
      } finally { setBusy(false); }
      return;
    }
    if (/^(confirm|yes confirm|confirmed)[.!?]*$/i.test(message)) {
      setDraft('');
      setMessages(prev => [...prev, { role: 'user', content: message }]);
      if (!report || !report.description.trim()) {
        setError('No completed report is awaiting confirmation. Describe the incident or open Draft incident report first.');
        return;
      }
      setError('For safety, use the Confirm & save report button to submit. Chat confirmation does not save incident reports.');
      return;
    }
    // Apply a location correction to the open draft before calling a language model.
    // The Battery is a large public landmark, not a verified street address.
    if (report && /\b(?:actually|instead|change|update|correction|no[, ]|at the battery)\b/i.test(message) && /\b(?:the battery|battery park|white point garden)\b/i.test(message)) {
      setReport({...report, location: 'The Battery (White Point Garden area), Charleston, SC', description: report.description.replace(/\b66\s+George\s+(?:Street|St)\b(?:,?\s*Charleston(?:,?\s*SC)?)?/gi, 'The Battery, Charleston, SC'), summary: report.summary?.replace(/\b66\s+George\s+(?:Street|St)\b(?:,?\s*Charleston(?:,?\s*SC)?)?/gi, 'The Battery, Charleston, SC')});
      setMessages(prev => [...prev, {role: 'user', content: message}, {role: 'assistant', content: 'Updated the draft location to The Battery (White Point Garden area), Charleston, SC. This is a landmark, not a verified street address. Your original incident type, affected-person count, and details were preserved. Review the location and confirm the draft before saving.'}]);
      setReportStatus('Location corrected to a landmark; enter a more precise location if available. Report has not been saved.');
      setDraft('');
      return;
    }
    const history = messages.slice(-8);
    setDraft('');
    setError('');
    setMessages(prev => [...prev, { role: 'user', content: message }]);
    setBusy(true);
    try {
      const response = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history }),
      });
      if (!response.ok) throw new Error('FORGE is unavailable. No emergency report was sent.');
      const data: { reply: string; report_draft?: Draft & {location_resolved:boolean} } = await response.json();
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }]);
      if (data.report_draft) {
        setReport(data.report_draft);
        setReportStatus(data.report_draft.location_resolved
          ? 'Address found in HARBOR data. Review and confirm before saving.'
          : 'Review the description and enter or confirm the location before saving.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'FORGE unavailable.');
    } finally {
      setBusy(false);
    }
  };

  return <aside className="harbor-chat-widget">
    {!open
      ? <button type="button" className="harbor-chat-toggle" onClick={() => setOpen(true)} aria-label="Open HARBOR + FORGE chat"><img src="/harbor-icon.svg" alt="" width="22" height="22" />Ask FORGE</button>
      : <section className="harbor-chat-panel" aria-label="HARBOR AI assistance chat">
          <div className="harbor-chat-heading"><strong className="harbor-chat-brand"><img src="/harbor-icon.svg" alt="" width="30" height="30" /> HARBOR + FORGE Assistant</strong><button type="button" onClick={() => setOpen(false)} aria-label="Close HARBOR AI chat">×</button></div>
          <p className="harbor-chat-disclaimer">In immediate danger, call 911 if possible. Reports are saved to HARBOR. Responder notification is not verified; call emergency services directly for immediate danger.</p>
          <div className="harbor-chat-messages" role="log" aria-live="polite">
            {messages.length === 0 && <p>Ask about flood safety, or describe an incident to draft a report.</p>}
            {messages.map((entry, i) => <div key={i} className={`harbor-chat-message ${entry.role}`}><b>{entry.role === 'user' ? 'You' : 'FORGE'}</b><p>{entry.content}</p></div>)}
            {busy && <p>Processing…</p>}
            {error && <p role="alert">{error}</p>}
            {reportStatus && <p role="status">{reportStatus}</p>}
          </div>
          {report && <form className="harbor-chat-report" onSubmit={submitReport}>
            <strong>Review report before submitting</strong>
            <label>Description<textarea required maxLength={1500} value={report.description} onChange={e => setReport({...report,description:e.target.value})} /></label>
            <label>Category<select value={report.category} onChange={e => setReport({...report,category:e.target.value})}>
              {['UNCLASSIFIED','FLOOD','MEDICAL','FIRE','INFRASTRUCTURE','SHELTER','GENERAL'].map(category => <option key={category}>{category}</option>)}
            </select></label>
            <label>Location (optional)<input value={report.location} onChange={e => setReport({...report,location:e.target.value})} maxLength={250} placeholder="Street or landmark" /></label>
            <label>People affected<input type="number" min={0} max={100000} value={report.people_affected} onChange={e => setReport({...report, people_affected:Number(e.target.value) || 0})} /></label>
            <label>Incident date/time (local; defaults to drafting time)<input value={report.incident_datetime ?? ''} onChange={e => setReport({...report,incident_datetime:e.target.value,datetime_assumed:false})} /></label>
            <label>Summary<textarea maxLength={1500} value={report.summary ?? ''} onChange={e => setReport({...report,summary:e.target.value})} /></label>
            <label>Actions taken (leave blank if unknown)<textarea maxLength={1500} value={report.actions_taken ?? ''} onChange={e => setReport({...report,actions_taken:e.target.value})} /></label>
            <label>Potential hazards (unverified)<textarea maxLength={1500} value={report.potential_hazards ?? ''} onChange={e => setReport({...report,potential_hazards:e.target.value})} /></label>
            <label>Suggested next steps (review before saving)<textarea maxLength={1500} value={report.next_steps ?? ''} onChange={e => setReport({...report,next_steps:e.target.value})} /></label>
            <div className="harbor-report-actions"><button type="button" onClick={() => setReport(null)}>Cancel</button><button type="submit" disabled={busy || !report.description.trim()}>Confirm & save report</button></div>
          </form>}
          <button type="button" className="harbor-report-draft-button" disabled={busy} onClick={suggestReport}>Draft incident report from chat</button>
          <form onSubmit={send} className="harbor-chat-form"><input aria-label="Ask FORGE" maxLength={1000} value={draft} onChange={e => setDraft(e.target.value)} placeholder="How can HARBOR help?" /><button type="submit" disabled={!draft.trim() || busy}>Send</button></form>
        </section>}
  </aside>;
}
