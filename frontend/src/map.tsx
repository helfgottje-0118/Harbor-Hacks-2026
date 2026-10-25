import React, { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { FeatureCollection } from 'geojson';
import { incidentTitle } from './incident-title';

export type MapIncident = { display_number?:number; id:number; category:string; description:string; timestamp:string; source:string; severity?:string; status?:string; node_id?:string|null; location?:string|null; people_affected?:number; ai_reasoning?:string|null; recommended_action?:string|null; latitude?:number|null; longitude?:number|null; observed_at?:string|null; water_depth_cm?:number|null };
export type MapResource = { id:number; name:string; type:string; status:string; capacity?:number|null; latitude?:number|null; longitude?:number|null };
type AgeFilter = '15m'|'1h'|'6h'|'all';

type Source = {source_timestamp?:string; source:string; url:string; downloaded_at:string; feature_count:number; file:string};
type Manifest = {sources: {basemap?:Source; flood_zones?:Source}};

export function hasCoordinates(item: {latitude?:number|null; longitude?:number|null}): item is {latitude:number; longitude:number} {
 return typeof item.latitude === 'number' && Number.isFinite(item.latitude) && Math.abs(item.latitude) <= 90 && typeof item.longitude === 'number' && Number.isFinite(item.longitude) && Math.abs(item.longitude) <= 180;
}
export function reportAge(report: MapIncident, now = Date.now()) {
 const age = now - Date.parse(report.observed_at || report.timestamp);
 if (!Number.isFinite(age) || age < 0) return 'Age unknown';
 return `${age >= 3600000 ? 'STALE · ' : ''}${Math.floor(age / 60000)} min old`;
}
export function filterIncidentsByAge<T extends MapIncident>(incidents:T[], filter:AgeFilter, now=Date.now()) {
 const limit = { '15m':15*60000, '1h':60*60000, '6h':6*3600000, all:Infinity }[filter];
 return incidents.filter(item => {
  const time = Date.parse(item.observed_at || item.timestamp);
  return limit === Infinity || (Number.isFinite(time) && now - time <= limit);
 });
}
export function clusterIncidents<T extends MapIncident>(incidents:T[]) {
 const groups = new Map<string,T[]>();
 for (const incident of incidents) {
  if (!hasCoordinates(incident)) continue;
  const key = `${incident.latitude.toFixed(3)}:${incident.longitude.toFixed(3)}`;
  groups.set(key,[...(groups.get(key) ?? []),incident]);
 }
 return [...groups.values()];
}
export function incidentPopup(report: MapIncident) {
 const popup = document.createElement('div');
 const lines = [`Report ${report.display_number ?? report.id} · Ticket ID ${report.id} · ${incidentTitle(report.description, report.category)}`, `Address: ${reportAddress(report)}`, report.description, reportAge(report), `Severity: ${report.severity ?? 'UNKNOWN'}`, `Status: ${report.status ?? 'UNKNOWN'}`, `People affected: ${report.people_affected ?? 'unknown'}`, `Reporter/node: ${report.node_id ?? 'not supplied'}`, `Received: ${report.timestamp}`, `Observed: ${report.observed_at ?? 'not supplied'}`, `Source: ${reportSource(report.source)}`, `Reported water depth: ${report.water_depth_cm == null ? 'unknown' : `${report.water_depth_cm} cm`}`, `Recommended action: ${report.recommended_action ?? 'not supplied'}`, `AI reasoning: ${report.ai_reasoning ?? 'not supplied'}`, `Coordinates: ${hasCoordinates(report) ? `${report.latitude.toFixed(6)}, ${report.longitude.toFixed(6)}` : 'missing or invalid'}`];
 for (const text of lines) { const line = document.createElement('p'); line.textContent = text; popup.append(line); }
 return popup;
}
export function clusterPopup(reports:MapIncident[]) {
 const popup=document.createElement('div');popup.className='cluster-popup';
 const heading=document.createElement('h3');heading.textContent=`${reports.length} reports at this location`;popup.append(heading);
 for(const report of reports){const article=document.createElement('article');article.append(...Array.from(incidentPopup(report).children));popup.append(article);}
 return popup;
}
export function floodRiskStyle(properties: Record<string,unknown>): L.PathOptions|null {
 const zone = String(properties.FLD_ZONE ?? '').toUpperCase();
 if (properties.SFHA_TF === 'T' || /^[AV]/.test(zone)) return {color:'#f59e0b',fillColor:'#f59e0b',weight:1,fillOpacity:0.28};
 if (String(properties.ZONE_SUBTY ?? '').includes('0.2 PCT')) return {color:'#fde68a',fillColor:'#fde68a',weight:1,fillOpacity:0.18};
 return null;
}
export function offlineRoute(streets:FeatureCollection,start:[number,number],end:[number,number],floods:Array<{latitude?:number|null;longitude?:number|null}>):[number,number][] {
 type Edge={to:string;cost:number};
 const nodes=new Map<string,[number,number]>(), graph=new Map<string,Edge[]>();
 const key=(lng:number,lat:number)=>`${lng.toFixed(6)},${lat.toFixed(6)}`;
 const distance=(a:[number,number],b:[number,number])=>Math.hypot(a[0]-b[0],a[1]-b[1]);
 const addLine=(coordinates:number[][])=>{for(let index=1;index<coordinates.length;index++){const a=coordinates[index-1] as [number,number],b=coordinates[index] as [number,number];const aKey=key(...a),bKey=key(...b);nodes.set(aKey,a);nodes.set(bKey,b);const midpoint:[number,number]=[(a[0]+b[0])/2,(a[1]+b[1])/2];const blocked=floods.some(item=>typeof item.latitude==='number'&&typeof item.longitude==='number'&&distance(midpoint,[item.longitude,item.latitude])<.0007);if(blocked)continue;const cost=distance(a,b);graph.set(aKey,[...(graph.get(aKey)??[]),{to:bKey,cost}]);graph.set(bKey,[...(graph.get(bKey)??[]),{to:aKey,cost}]);}};
 for(const feature of streets.features){const geometry=feature.geometry as {type?:string;coordinates?:unknown};if(geometry?.type==='LineString')addLine(geometry.coordinates as number[][]);else if(geometry?.type==='MultiLineString')for(const line of geometry.coordinates as number[][][])addLine(line);}
 if(!nodes.size)return[start,end];
 const nearest=([lat,lng]:[number,number])=>[...nodes].reduce((best,current)=>distance(current[1],[lng,lat])<distance(best[1],[lng,lat])?current:best)[0];
 const source=nearest(start),target=nearest(end),dist=new Map<string,number>([[source,0]]),previous=new Map<string,string>(),queue=new Set(nodes.keys());
 while(queue.size){let current:string|undefined;for(const candidate of queue)if(current===undefined||(dist.get(candidate)??Infinity)<(dist.get(current)??Infinity))current=candidate;if(current===undefined||(dist.get(current)??Infinity)===Infinity)break;queue.delete(current);if(current===target)break;for(const edge of graph.get(current)??[]){const next=(dist.get(current)??Infinity)+edge.cost;if(next<(dist.get(edge.to)??Infinity)){dist.set(edge.to,next);previous.set(edge.to,current);}}}
 if(!dist.has(target))return[start,end];
 const path:string[]=[];for(let current:string|undefined=target;current;current=previous.get(current)){path.push(current);if(current===source)break;}path.reverse();return[start,...path.map(item=>{const [lng,lat]=nodes.get(item)!;return[lat,lng] as [number,number];}),end];
}

const COVERAGE: L.LatLngBoundsLiteral = [[32.70,-80.02],[32.86,-79.84]];
function focusCoverage(map:L.Map, bounds:L.LatLngBoundsExpression=COVERAGE) {
 const region = bounds instanceof L.LatLngBounds ? bounds : L.latLngBounds(bounds);
 const zoom = map.getBoundsZoom(region,true);
 map.setMaxBounds(region);
 map.options.maxBoundsViscosity = 1;
 map.setMinZoom(zoom);
 map.setView(region.getCenter(),zoom,{animate:false,reset:true} as L.ZoomPanOptions);
}
/** Frame the part of the downloaded map containing streets, not empty boundary margins. */
export function streetContentBounds(collection:FeatureCollection): L.LatLngBounds | null {
 const points:[number,number][]=[];
 const visit=(value:unknown):void=>{
   if(!Array.isArray(value))return;
   if(value.length>=2 && typeof value[0]==='number' && typeof value[1]==='number'){
     const lng=value[0], lat=value[1];
     if(Number.isFinite(lat)&&Number.isFinite(lng)&&Math.abs(lat)<=90&&Math.abs(lng)<=180)points.push([lat,lng]);
   } else for(const child of value)visit(child);
 };
 for(const feature of collection.features) {
   const shape=feature.geometry as {coordinates?:unknown}|null;
   if(shape?.coordinates)visit(shape.coordinates);
 }
 if(points.length<2)return null;
 const lat=points.map(p=>p[0]).sort((a,b)=>a-b),lng=points.map(p=>p[1]).sort((a,b)=>a-b);
 const at=(items:number[],q:number)=>items[Math.floor((items.length-1)*q)];
 return L.latLngBounds([at(lat,.08),at(lng,.08)],[at(lat,.92),at(lng,.92)]);
}
export function reportSource(source:string):string {
 const name=source.toUpperCase();
 if(name==='LORA_REAL'||name==='LORA_SIM'||name==='LORA') return name==='LORA_SIM'?'LORA (simulation)':'LORA';
 if(name==='PHOTON') return 'PHOTON';
 if(name==='WEB') return 'WEB';
 return source || 'UNKNOWN';
}
function reportAddress(report:MapIncident):string {
 return report.location?.trim() || 'Not provided — verify with reporter; coordinates are not a confirmed street address';
}
function severityClass(value?:string) { return `severity-${String(value ?? 'unknown').toLowerCase()}`; }

export function OfflineMap({incidents,resources,onLocationSelect}:{incidents:MapIncident[];resources:MapResource[];onLocationSelect?:(lat:number,lng:number)=>void}) {
 const container=useRef<HTMLDivElement>(null), mapRef=useRef<L.Map|null>(null);
 const localCoverage=useRef<L.LatLngBounds|null>(null);
 const contentCoverage=useRef<L.LatLngBounds|null>(null);
 const markers=useRef(new Map<string,L.Marker>()), routeRef=useRef<L.Polyline|null>(null);
 const layers = {basemap:true,flood_zones:true,incidents:true,resources:true};
 const [data,setData]=useState<Record<string,FeatureCollection>>({});
 const [manifest,setManifest]=useState<Manifest|null>(null), [errors,setErrors]=useState<Record<string,string>>({});
 const [attempt,setAttempt]=useState(0), [now,setNow]=useState(Date.now()), [ageFilter,setAgeFilter]=useState<AgeFilter>('all');
 const [selectedId,setSelectedId]=useState<number|null>(null), [routeMessage,setRouteMessage]=useState('');
 const [mapSize,setMapSize]=useState<'compact'|'standard'|'expanded'>('compact');
 const visibleIncidents=useMemo(()=>filterIncidentsByAge(incidents,ageFilter,now),[incidents,ageFilter,now]);
 const mappedIncidents=visibleIncidents.filter(hasCoordinates), mappedResources=resources.filter(hasCoordinates);
 const selected=visibleIncidents.find(item=>item.id===selectedId) ?? visibleIncidents[0];
 const availableResource=mappedResources.find(item=>item.status==='AVAILABLE') ?? mappedResources[0];
 const resetCoverage=()=>{if(!mapRef.current)return; const map=mapRef.current; map.invalidateSize({pan:false}); focusCoverage(map,contentCoverage.current??localCoverage.current??COVERAGE);};
 const viewIncident=(incident:MapIncident)=>{if(!hasCoordinates(incident)||!mapRef.current)return;setSelectedId(incident.id);mapRef.current.setView([incident.latitude,incident.longitude],Math.max(mapRef.current.getZoom(),14),{animate:false});markers.current.get(`incident:${incident.id}`)?.openPopup();};
 const previewRoute=()=>{if(!selected||!hasCoordinates(selected)||!availableResource||!hasCoordinates(availableResource)||!mapRef.current)return;const points=offlineRoute(data.basemap??{type:'FeatureCollection',features:[]},[availableResource.latitude,availableResource.longitude],[selected.latitude,selected.longitude],visibleIncidents.filter(item=>/flood/i.test(item.category)));routeRef.current?.remove();routeRef.current=L.polyline(points,{color:'#8da8ff',weight:5,dashArray:'10 8',opacity:.9}).addTo(mapRef.current);mapRef.current.fitBounds(routeRef.current.getBounds(),{padding:[60,60],maxZoom:15,animate:false});setRouteMessage(`Advisory offline street route from ${availableResource.name} to report ${selected.display_number ?? selected.id}; segments near reported flooding are excluded. Verify road and flood conditions before travel.`);};
 useEffect(()=>{
  const timer=window.setTimeout(()=>{
   const map=mapRef.current;
   if(map) {
    map.invalidateSize({pan:false});
    const bounds=contentCoverage.current??localCoverage.current??L.latLngBounds(COVERAGE);
    map.setMinZoom(map.getBoundsZoom(bounds,true));
    map.panInsideBounds(bounds,{animate:false});
   }
  },80);
  return()=>window.clearTimeout(timer);
 },[mapSize]);
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),60000);return()=>clearInterval(timer);},[]);
 useEffect(()=>{
  const element=container.current!;
  const map=L.map(element,{attributionControl:false,preferCanvas:true,trackResize:false,maxBounds:COVERAGE,maxBoundsViscosity:1,zoomSnap:.25,zoomDelta:.5}).fitBounds(COVERAGE);
  map.createPane('basemap').style.zIndex='200'; map.createPane('risk').style.zIndex='300'; mapRef.current=map;
  let width=element.clientWidth,height=element.clientHeight,hasUsableLayout=width>=200&&height>=200;if(hasUsableLayout)focusCoverage(map);
  const resize=()=>{if(!element.clientWidth||!element.clientHeight||(width===element.clientWidth&&height===element.clientHeight))return;const center=map.getCenter(),zoom=map.getZoom();width=element.clientWidth;height=element.clientHeight;map.invalidateSize({pan:false});if(!hasUsableLayout&&width>=200&&height>=200){hasUsableLayout=true;focusCoverage(map);return;}const activeBounds=contentCoverage.current??localCoverage.current??L.latLngBounds(COVERAGE);const minimumZoom=map.getBoundsZoom(activeBounds,true);map.setMinZoom(minimumZoom);map.setMaxBounds(activeBounds);map.setView(center,Math.max(zoom,minimumZoom),{animate:false,reset:true} as L.ZoomPanOptions);map.panInsideBounds(activeBounds,{animate:false});};
  const click=(event:L.LeafletMouseEvent)=>onLocationSelect?.(event.latlng.lat,event.latlng.lng);map.on('click',click);
  const observer=typeof ResizeObserver!=='undefined'?new ResizeObserver(resize):null;observer?.observe(element);if(!observer)window.addEventListener('resize',resize);
  return()=>{observer?.disconnect();window.removeEventListener('resize',resize);map.off('click',click);map.remove();markers.current.clear();mapRef.current=null;};
 },[onLocationSelect]);
 useEffect(()=>{let cancelled=false;for(const [key,url] of Object.entries({basemap:'/api/maps/basemap.geojson',flood_zones:'/api/maps/flood-zones.geojson',manifest:'/api/maps/manifest'})){fetch(url).then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}).then(value=>{if(cancelled)return;if(key==='manifest'){if(!value.sources)throw new Error('Invalid manifest');setManifest(value);}else{if(value.type!=='FeatureCollection'||!Array.isArray(value.features))throw new Error('Invalid GeoJSON');setData(current=>({...current,[key]:value}));}setErrors(current=>{const next={...current};delete next[key];return next;});}).catch(error=>{if(!cancelled)setErrors(current=>({...current,[key]:error.message}));});}return()=>{cancelled=true;};},[attempt]);
 useEffect(()=>{
  // Frame the real downloaded street geometry rather than a fixed rectangular
  // approximation. The latter can leave a large empty strip on tall layouts.
  if (!data.basemap?.features?.length || !mapRef.current) return;
  const streets=L.geoJSON(data.basemap);
  const bounds=streets.getBounds();
  if (!bounds.isValid()) return;
  localCoverage.current=bounds;
  const map=mapRef.current;
  map.invalidateSize({pan:false});
  const populated = streetContentBounds(data.basemap);
  contentCoverage.current=populated?.isValid()?populated:null;
  // The full download bounds include empty margins. Restrict dragging and
  // minimum zoom to the area with actual street geometry, not the download.
  focusCoverage(map,contentCoverage.current??bounds);
 },[data.basemap]);
 useEffect(()=>{const map=mapRef.current!;const group=L.layerGroup().addTo(map);for(const key of ['basemap','flood_zones'] as const)if(layers[key]&&data[key])L.geoJSON(data[key],{pane:key==='basemap'?'basemap':'risk',filter:feature=>key==='basemap'||floodRiskStyle(feature.properties??{})!==null,style:feature=>key==='basemap'?{color:'#94a3b8',weight:1.4,fillOpacity:0}:floodRiskStyle(feature?.properties??{})??{},onEachFeature:(feature,layer)=>{const label=document.createElement('span');label.textContent=key==='basemap'?String(feature.properties?.name??feature.properties?.highway??'Unnamed street'):`FEMA zone ${feature.properties?.FLD_ZONE??'unknown'} · ${feature.properties?.ZONE_SUBTY??'Mapped flood hazard, not current water'}`;layer.bindTooltip(label);}}).addTo(group);return()=>{group.remove();};},[data,layers.basemap,layers.flood_zones]);
 useEffect(()=>{
  const active=new Set<string>();
  const update=(key:string,point:L.LatLngExpression,title:string,icon:L.DivIcon,popup:HTMLElement,click?:()=>void)=>{active.add(key);let marker=markers.current.get(key);if(!marker){marker=L.marker(point,{title,icon}).bindPopup(popup,{maxWidth:340,maxHeight:300,autoPan:true,autoPanPadding:[20,20]}).addTo(mapRef.current!);if(click)marker.on('click',click);markers.current.set(key,marker);}else{marker.setLatLng(point);marker.options.title=title;marker.setIcon(icon);marker.setPopupContent(popup);}};
  if(layers.incidents)for(const group of clusterIncidents(mappedIncidents)){const first=group[0];if(group.length>1){update(`cluster:${first.latitude!.toFixed(3)}:${first.longitude!.toFixed(3)}`,[first.latitude!,first.longitude!],`${group.length} nearby reports`,L.divIcon({className:'map-marker cluster-marker',html:`<span aria-hidden="true" class="incident-flag">🚩</span><span class="incident-pin-label">${group.length}</span>`,iconSize:[42,32]}),clusterPopup(group),()=>setSelectedId(first.id));}else{const stale=reportAge(first,now).startsWith('STALE');const flood=/flood/i.test(first.category);update(`incident:${first.id}`,[first.latitude!,first.longitude!],`Report ${first.display_number ?? first.id}`,L.divIcon({className:`map-marker ${flood?'flood-marker':'report-marker'} ${severityClass(first.severity)} ${stale?'stale-marker':''}`,html:`<span aria-hidden="true" class="incident-flag">🚩</span><span class="incident-pin-label">${first.display_number ?? first.id}</span>`,iconSize:[42,34]}),incidentPopup(first),()=>setSelectedId(first.id));}}
  if(layers.resources)for(const resource of mappedResources){const popup=document.createElement('div');popup.textContent=`${resource.name} · ${resource.type} · ${resource.status} · capacity ${resource.capacity??'unknown'}`;update(`resource:${resource.id}`,[resource.latitude!,resource.longitude!],resource.name,L.divIcon({className:`map-marker resource-marker resource-${resource.status.toLowerCase()}`,html:'R',iconSize:[26,26]}),popup);}
  for(const [key,marker] of markers.current)if(!active.has(key)){marker.remove();markers.current.delete(key);}
 },[layers.incidents,layers.resources,mappedIncidents,mappedResources,now]);
 return <section className="panel map-panel" aria-labelledby="map-heading">
  <div className="map-header"><div><p className="section-kicker">Tactical overview</p><h2 id="map-heading">Charleston · Offline Operations Map</h2><p className="map-subtitle">Local street, hazard, incident, and resource data in one offline view. Click the map to populate report coordinates.</p></div><div className="map-stats" aria-label="Map status"><span>{mappedIncidents.length} mapped {mappedIncidents.length===1?'report':'reports'}</span><span>{mappedResources.length} mapped {mappedResources.length===1?'resource':'resources'}</span><span className="offline-badge">Offline data</span></div></div>
  <div className="risk-disclaimer"><span aria-hidden="true">!</span><p><strong>Risk zones are not current water.</strong> Amber areas show mapped flood hazard—not observed flooding or safe routes. Reported depths are unverified.</p></div>
  <div className="map-toolbar"><label className="map-size-picker">Map size<select aria-label="Map size" value={mapSize} onChange={e=>setMapSize(e.target.value as typeof mapSize)}><option value="compact">Compact</option><option value="standard">Standard</option><option value="expanded">Expanded</option></select></label><label className="age-filter">Report age<select aria-label="Report age" value={ageFilter} onChange={e=>setAgeFilter(e.target.value as AgeFilter)}><option value="15m">15 minutes</option><option value="1h">1 hour</option><option value="6h">6 hours</option><option value="all">All reports</option></select></label><div className="map-actions"><button className="secondary" onClick={resetCoverage}>Reset coverage</button><button className="secondary" onClick={()=>setAttempt(value=>value+1)}>Reload data</button></div></div>
  {Object.entries(errors).map(([key,error])=><p role="alert" key={key}>{key} unavailable: {error}. No replacement data is generated.</p>)}
  {!data.basemap&&!errors.basemap&&<p>Loading local basemap…</p>}{Object.entries(data).filter(([,value])=>value.features.length===0).map(([key])=><p key={key}>{key}: no features available in local file.</p>)}
  <div className={`map-workspace map-workspace--${mapSize}`}><div ref={container} className="offline-map" aria-label="Interactive Charleston map"/><aside className="map-sidebar"><h3>Incident navigator</h3><p>{visibleIncidents.length} in selected time window · repeated reports remain separate</p><div className="incident-nav-list">{visibleIncidents.length===0&&<span className="empty">No reports in this time window.</span>}{visibleIncidents.map(item=><button aria-label={`View report ${item.display_number ?? item.id}`} className={`incident-nav ${severityClass(item.severity)} ${selectedId===item.id?'selected':''}`} key={item.id} disabled={!hasCoordinates(item)} title={!hasCoordinates(item)?'Location missing or not reliably geocoded; no pin can be placed until coordinates are supplied.':`Show ticket ${item.id} on map`} onClick={()=>viewIncident(item)}><b><span aria-hidden="true">🚩 </span>Report {item.display_number ?? item.id} · Ticket ID {item.id} · {incidentTitle(item.description,item.category)}</b><span>{item.severity??'UNKNOWN'} · {item.status??'UNKNOWN'} · {reportAge(item,now)}</span><small>Address: {reportAddress(item)}</small>{!hasCoordinates(item)&&<small>📍 PIN PENDING — no reliable coordinates. Supply and verify the location before mapping.</small>}<small>{item.description}</small><small>People affected: {item.people_affected??'unknown'} · Reporter/node: {item.node_id??'not supplied'}</small><small>Source: {reportSource(item.source)} · Received: {item.timestamp}</small><small>Observed: {item.observed_at??'not supplied'} · Water depth: {item.water_depth_cm==null?'unknown':`${item.water_depth_cm} cm`}</small><small>Recommended action: {item.recommended_action??'not supplied'}</small><small>AI reasoning: {item.ai_reasoning??'not supplied'}</small><small>Coordinates: {hasCoordinates(item)?`${item.latitude.toFixed(6)}, ${item.longitude.toFixed(6)}`:'missing or invalid'}</small></button>)}</div>{selected&&availableResource&&<button className="route-button" aria-label={`Preview route from ${availableResource.name}`} onClick={previewRoute}>Preview dispatch route</button>}{routeMessage&&<p className="route-warning">{routeMessage}</p>}</aside></div>
  <div className="map-legend" aria-label="Map legend"><span><i className="legend-swatch hazard"/>Amber · high flood hazard</span><span><i className="legend-swatch hazard-light"/>Light amber · 0.2% annual chance</span><span><i className="legend-marker flood">F</i>Reported flooding</span><span><i className="legend-marker report">!</i>Other report</span><span><i className="legend-marker resource">R</i>Resource</span></div>
  <div className="map-notes"><p>{incidents.filter(i=>!hasCoordinates(i)).length} reports / {resources.filter(r=>!hasCoordinates(r)).length} resources with missing or invalid coordinates are not mapped.</p><p>{incidents.filter(i=>reportAge(i,now).startsWith('STALE')).length} stale reports are at least 60 minutes old. Report age does not establish current conditions.</p></div>
  <details className="map-details"><summary>Data coverage and sources</summary><p className="map-attribution">Street-line basemap © OSM contributors · ODbL. Flood hazard data: FEMA NFHL. Central Charleston coverage only; blank areas are not evidence of safety. No remote tiles or live water measurements.</p>{manifest&&['basemap','flood_zones'].map(key=>{const source=manifest.sources[key as keyof Manifest['sources']];return source?<p key={key}>{source.source} · {source.url} · Downloaded: {source.downloaded_at} · Source timestamp: {source.source_timestamp??'not supplied'} · {source.feature_count} features · {source.file}</p>:null;})}</details>
 </section>;
}
