/** Short, factual incident heading derived from reported text (no guessed address). */
export function incidentTitle(description: string, category: string): string {
  const text = description.trim().replace(/\s+/g, ' ');
  // Event type wins over unrelated fallback narratives and stale categories.
  if (/\b(fire|flames|smoke|burning)\b/i.test(description)) return 'Fire reported';
  if (/\b(flood|flooding|floodwater)\b/i.test(description)) return 'Flood reported';
  if (category.toUpperCase() === 'FIRE') return 'Fire reported';
  if (category.toUpperCase() === 'FLOOD') return 'Flood reported';
  const address = text.match(/\b\d{1,6}\s+[A-Za-z][A-Za-z0-9.' -]{0,65}?\s+(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|court|ct|way|place|pl)\b/i);
  const location = address ? address[0].replace(/\b\w/g, letter => letter.toUpperCase()) : '';
  const lower = text.toLowerCase();
  const cause =
    /dead body|deceased|unresponsive person/i.test(text) ? 'Person reported unresponsive or deceased' :
    /tree|treet|fallen branch/i.test(text) && /block|stuck|road|street/i.test(text) ? 'Tree blocking roadway' :
    /tree|treet|fallen branch/i.test(text) ? 'Fallen tree reported' :
    /flood|floodwater|rising water/i.test(text) ? 'Flooding reported' :
    /fire|smoke|flames/i.test(text) ? 'Fire or smoke reported' :
    /injur|medical|ambulance/i.test(text) ? 'Medical incident reported' :
    /power line|downed wire/i.test(text) ? 'Electrical hazard reported' :
    /blocked|blocking|obstruction/i.test(text) ? 'Road obstruction reported' :
    '';
  if (location && cause) return `${location} — ${cause}`;
  if (location) {
    const remainder = text.replace(address![0], '').replace(/\b(?:there is|there's|at|on|near|a|an|the)\b/gi,' ').replace(/\s+/g,' ').trim();
    return remainder ? `${location} — ${remainder.slice(0,70)}` : `${location} — ${category.toLowerCase()} report`;
  }
  return cause || text.slice(0,90) || `${category} report`;
}
