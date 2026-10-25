import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import L from 'leaflet';
test('map uses canvas and filters risk beneath markers with safe street labels', async () => {
 const draw = vi.spyOn(L,'geoJSON');
 const create = vi.spyOn(L,'map');
 vi.stubGlobal('fetch',vi.fn(async (url:string) => ({ok:true,json:async () => url.endsWith('manifest') ? manifest : collection})));
 render(<OfflineMap incidents={[]} resources={[]} />);
 await screen.findByText(/OpenStreetMap/);
 expect(create.mock.calls[0][1]).toMatchObject({preferCanvas:true, zoomSnap:0.25, zoomDelta:0.5});
 const risk = draw.mock.calls.find(([,options]) => options?.pane === 'risk')?.[1];
 expect(risk?.filter?.({type:'Feature',geometry:{type:'Polygon',coordinates:[]},properties:{FLD_ZONE:'X'}})).toBe(false);
 const base = draw.mock.calls.find(([,options]) => options?.pane === 'basemap')?.[1];
 const bindTooltip = vi.fn();
 base?.onEachFeature?.({type:'Feature',geometry:{type:'LineString',coordinates:[]},properties:{name:'<img src=x>'}}, {bindTooltip} as unknown as L.Layer);
 expect(bindTooltip.mock.calls[0][0].textContent).toBe('<img src=x>');
 expect(bindTooltip.mock.calls[0][0].querySelector('img')).toBeNull();
 expect(document.querySelector<HTMLElement>('.leaflet-risk-pane')?.style.zIndex).toBe('300');
 vi.restoreAllMocks();
});
import { clusterIncidents, clusterPopup, filterIncidentsByAge, incidentPopup, offlineRoute, OfflineMap, floodRiskStyle, streetContentBounds } from './map';
test('FEMA risk classification excludes minimal-hazard X and distinguishes 0.2 percent risk', () => {
 expect(floodRiskStyle({FLD_ZONE:'X',SFHA_TF:'F',ZONE_SUBTY:'AREA OF MINIMAL FLOOD HAZARD'})).toBeNull();
 expect(floodRiskStyle({FLD_ZONE:'AE',SFHA_TF:'T'})?.fillColor).toBe('#f59e0b');
 expect(floodRiskStyle({FLD_ZONE:'VE'})?.fillColor).toBe('#f59e0b');
 expect(floodRiskStyle({FLD_ZONE:'X',ZONE_SUBTY:'0.2 PCT ANNUAL CHANCE FLOOD HAZARD'})?.fillColor).toBe('#fde68a');
 expect(floodRiskStyle({})).toBeNull();
});
const collection = {type:'FeatureCollection', features:[]};
const manifest = {sources:{basemap:{source:'OpenStreetMap',url:'https://www.openstreetmap.org',source_timestamp:'2026-07-28',downloaded_at:'2026-10-11',feature_count:0,file:'basemap.geojson'},flood_zones:{source:'FEMA',url:'https://www.fema.gov',downloaded_at:'2026-10-10',feature_count:0,file:'flood-zones.geojson'}}};
test('offline map loads local layers, exposes provenance and toggles with stale and unmapped counts', async () => {
 const fetcher = vi.fn(async (url:string) => ({ok:true,json:async () => url.endsWith('manifest') ? manifest : collection}));
 vi.stubGlobal('fetch',fetcher);
 render(<OfflineMap incidents={[report,{...report,id:2,latitude:null}]} resources={[{id:1,name:'Team',type:'RESCUE',status:'AVAILABLE',latitude:32.77,longitude:-79.94}]} />);
 await screen.findByText(/OpenStreetMap/);
 expect(screen.getByText(/OSM contributors.*ODbL.*FEMA/)).toBeInTheDocument();
 expect(screen.getByText(/Light amber.*0.2%/)).toBeInTheDocument();
 expect(fetcher.mock.calls.map(c=>c[0]).sort()).toEqual(['/api/maps/basemap.geojson','/api/maps/flood-zones.geojson','/api/maps/manifest']);
 expect(screen.getByText(/Risk zones are not current water/)).toBeInTheDocument();
 expect(screen.getByText(/1 reports.*0 resources.*missing or invalid coordinates/)).toBeInTheDocument();
 expect(screen.getByText(/2 stale reports/)).toBeInTheDocument();
 expect(document.querySelectorAll('.leaflet-marker-icon')).toHaveLength(2);
 expect(screen.queryByLabelText('Incident reports')).not.toBeInTheDocument();
 expect(document.querySelectorAll('.leaflet-marker-icon')).toHaveLength(2);
 expect(screen.getByText(/Source timestamp: 2026-07-28/)).toBeInTheDocument();
 expect(screen.getByText(/2026-10-10/)).toBeInTheDocument();
 expect(document.querySelectorAll('img.leaflet-tile')).toHaveLength(0);
});
test('missing local files show unavailable errors instead of fabricated layers', async () => {
 vi.stubGlobal('fetch', vi.fn(async () => ({ok:false,status:503,json:async () => ({})})));
 render(<OfflineMap incidents={[]} resources={[]} />);
 await screen.findByText(/basemap unavailable: HTTP 503/);
 expect(screen.getByText(/flood_zones unavailable: HTTP 503/)).toBeInTheDocument();
 expect(screen.getByText(/manifest unavailable: HTTP 503/)).toBeInTheDocument();
 expect(document.querySelectorAll('.leaflet-marker-icon')).toHaveLength(0);
});
test('open report survives equal and changed polling with fresh content and location', async () => {
 vi.stubGlobal('fetch',vi.fn(async (url:string) => ({ok:true,json:async () => url.endsWith('manifest') ? manifest : collection})));
 const create = vi.spyOn(L, 'marker');
 const view = render(<OfflineMap incidents={[report]} resources={[]} />);
 await screen.findByText(/OpenStreetMap/);
 const marker = create.mock.results[0].value as L.Marker;
 marker.openPopup();
 view.rerender(<OfflineMap incidents={[{...report}]} resources={[]} />);
 expect(marker.isPopupOpen()).toBe(true);
 const changed = {...report, description:'Updated depth', water_depth_cm:42, latitude:32.79};
 view.rerender(<OfflineMap incidents={[changed]} resources={[]} />);
 expect(marker.isPopupOpen()).toBe(true);
 expect(document.querySelector('.leaflet-popup-content')).toHaveTextContent('Updated depth');
 expect(document.querySelector('.leaflet-popup-content')).toHaveTextContent('42 cm');
 expect(document.querySelector('.leaflet-popup-content')).not.toHaveTextContent(report.description);
 expect(marker.getLatLng().lat).toBe(32.79);
 view.rerender(<OfflineMap incidents={[]} resources={[]} />);
 expect(document.querySelector('.leaflet-popup')).toBeNull();
 expect(document.querySelectorAll('.leaflet-marker-icon')).toHaveLength(0);
});
test('resize preserves geographic center while fitting coverage at narrow widths', async () => {
 let width = 1280;
 vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width);
 vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(490);
 let resize = () => {};
 const disconnect = vi.fn();
 vi.stubGlobal('ResizeObserver', class { constructor(callback:() => void) { resize = callback; } observe() {} disconnect = disconnect; });
 vi.stubGlobal('fetch',vi.fn(async (url:string) => ({ok:true,json:async () => url.endsWith('manifest') ? manifest : collection})));
 const create = vi.spyOn(L,'map');
 const view = render(<OfflineMap incidents={[]} resources={[]} />);
 await screen.findByText(/OpenStreetMap/);
 const map = create.mock.results[0].value as L.Map;
 expect(map.getZoom()).toBe(map.getBoundsZoom([[32.70,-80.02],[32.86,-79.84]], true));
 expect(map.getMinZoom()).toBe(map.getZoom());
 map.setView([32.79,-79.94], 15, {animate:false});
 const center = map.getCenter();
 width = 390;
 resize();
 expect(map.getCenter().distanceTo(center)).toBeLessThan(1);
 expect(map.getMinZoom()).toBe(map.getBoundsZoom([[32.70,-80.02],[32.86,-79.84]], true));
 width = 1280;
 resize();
 expect(map.getCenter().distanceTo(center)).toBeLessThan(1);
 view.unmount();
 expect(disconnect).toHaveBeenCalled();
});
test('map toolbar omits layer tabs but retains age filter and coverage reset', async () => {
 vi.stubGlobal('fetch',vi.fn(async (url:string) => ({ok:true,json:async () => url.endsWith('manifest') ? manifest : collection})));
 render(<OfflineMap incidents={[report]} resources={[]} />);
 await screen.findByText(/OpenStreetMap/);
 expect(screen.queryByRole('group', {name:'Map layers'})).not.toBeInTheDocument();
 expect(screen.getByRole('button', {name:'Reset coverage'})).toBeInTheDocument();
 expect(screen.getByText('1 mapped report')).toBeInTheDocument();
 expect(screen.getByText('0 mapped resources')).toBeInTheDocument();
});
test('first layout refits coverage after mounting into a small container and reset restores coverage', async () => {
 let width = 30;
 vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width);
 vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(490);
 let resize = () => {};
 vi.stubGlobal('ResizeObserver', class { constructor(callback:() => void) { resize = callback; } observe() {} disconnect() {} });
 vi.stubGlobal('fetch',vi.fn(async (url:string) => ({ok:true,json:async () => url.endsWith('manifest') ? manifest : collection})));
 const create = vi.spyOn(L,'map');
 render(<OfflineMap incidents={[]} resources={[]} />);
 await screen.findByText(/OpenStreetMap/);
 const map = create.mock.results[0].value as L.Map;
 width = 1280;
 resize();
 expect(map.getZoom()).toBe(map.getBoundsZoom([[32.70,-80.02],[32.86,-79.84]], true));
 expect(map.getMinZoom()).toBe(map.getZoom());
 map.setView([0,0], 4, {animate:false});
 fireEvent.click(screen.getByRole('button', {name:'Reset coverage'}));
 expect(map.getCenter().lat).toBeCloseTo(32.78, 2);
 expect(map.getCenter().lng).toBeCloseTo(-79.93, 2);
 expect(map.getZoom()).toBe(map.getBoundsZoom([[32.70,-80.02],[32.86,-79.84]], true));
 expect(map.getMinZoom()).toBe(map.getZoom());
});
test('filters report ages and clusters nearby incidents for operational readability', () => {
 const now = Date.parse('2026-10-21T01:00:00Z');
 const reports = [
  {...report,id:1,timestamp:'2026-10-21T00:50:00Z',observed_at:null,latitude:32.78001,longitude:-79.93001,severity:'CRITICAL'},
  {...report,id:2,timestamp:'2026-10-21T00:20:00Z',observed_at:null,latitude:32.78002,longitude:-79.93002,severity:'LOW'},
  {...report,id:3,timestamp:'2026-10-20T18:00:00Z',observed_at:null,latitude:32.8,longitude:-79.95,severity:'HIGH'},
 ];
 expect(filterIncidentsByAge(reports,'15m',now).map(item => item.id)).toEqual([1]);
 expect(filterIncidentsByAge(reports,'1h',now).map(item => item.id)).toEqual([1,2]);
 expect(clusterIncidents(reports).map(group => group.length).sort()).toEqual([1,2]);
});
test('offline route uses local streets and avoids reported flood points', () => {
 const streets = {type:'FeatureCollection',features:[
  {type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[[0,0],[.001,0],[.002,0]]}},
  {type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[[0,0],[0,.001],[.002,.001],[.002,0]]}},
 ]} as any;
 const route = offlineRoute(streets,[0,0],[0,.002],[{latitude:0,longitude:.001}]);
 expect(route).toContainEqual([.001,0]);
 expect(route).not.toContainEqual([0,.001]);
});
test('cluster popup preserves complete information for every repeated report', () => {
 const repeated = [
  {...report,id:41,severity:'HIGH',status:'OPEN',node_id:'PHONE-9',people_affected:1,recommended_action:'Dispatch medical team',ai_reasoning:'Injury reported',description:'Tree blocking East Bay Street with one injured person'},
  {...report,id:42,severity:'HIGH',status:'DISPATCHED',description:'Tree blocking East Bay Street with one injured person'},
 ];
 const popup = clusterPopup(repeated);
 expect(popup.querySelectorAll('article')).toHaveLength(2);
 expect(popup.textContent).toContain('Report 41 · Tree blocking roadway');
 expect(popup.textContent).toContain('Report 42 · Tree blocking roadway');
 expect(popup.textContent).toContain('Status: OPEN');
 expect(popup.textContent).toContain('Status: DISPATCHED');
 expect(popup.textContent).toContain('Reporter/node: PHONE-9');
 expect(popup.textContent).toContain('People affected: 1');
 expect(popup.textContent).toContain('Recommended action: Dispatch medical team');
 expect(popup.textContent).toContain('AI reasoning: Injury reported');
 expect(popup.textContent?.match(/Tree blocking East Bay Street with one injured person/g)).toHaveLength(2);
});
test('shows incident navigator, time filters and advisory route controls', async () => {
 vi.stubGlobal('fetch',vi.fn(async (url:string) => ({ok:true,json:async () => url.endsWith('manifest') ? manifest : collection})));
 render(<OfflineMap incidents={[{...report,severity:'CRITICAL'}]} resources={[{id:1,name:'Team',type:'RESCUE',status:'AVAILABLE',latitude:32.77,longitude:-79.94}]} />);
 await screen.findByText(/OpenStreetMap/);
 expect(screen.getByRole('combobox',{name:'Report age'})).toBeInTheDocument();
 expect(screen.getByRole('heading',{name:'Incident navigator'})).toBeInTheDocument();
 expect(screen.getByRole('button',{name:/View report 1/})).toBeInTheDocument();
 expect(screen.getByRole('button',{name:/Preview route from Team/})).toBeInTheDocument();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
export const report = { id:1, category:'FLOOD', description:'<img src=x onerror=alert(1)>', timestamp:'2020-01-01T00:00:00Z', observed_at:'2019-12-31T23:00:00Z', source:'WEB', latitude:32.78, longitude:-79.93, water_depth_cm:0 };
test('report popup preserves zero, timestamps and untrusted text without HTML', () => {
 const popup = incidentPopup(report);
 expect(popup.textContent).toContain('STALE');
 expect(popup.textContent).toContain('Reported water depth: 0 cm');
 expect(popup.textContent).toContain('Received: 2020-01-01');
 expect(popup.textContent).toContain('Observed: 2019-12-31');
 expect(popup.textContent).toContain('Source: WEB');
 expect(popup.textContent).toContain(report.description);
 expect(popup.querySelector('img')).toBeNull();
 expect(incidentPopup({...report, water_depth_cm:null}).textContent).toContain('Reported water depth: unknown');
});

test('content framing ignores sparse outer map vertices to avoid blank margins', () => {
 const geometry = {type:'FeatureCollection',features:[
   {type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[
     [-79.98,32.84],[-79.94,32.75],[-79.939,32.751],[-79.938,32.752],
     [-79.937,32.753],[-79.936,32.754],[-79.935,32.755],[-79.934,32.756],
     [-79.933,32.757],[-79.932,32.758],[-79.931,32.759],[-79.93,32.76],
     [-79.929,32.761],[-79.928,32.762]
   ]}}
 ]} as any;
 const bounds=streetContentBounds(geometry)!;
 expect(bounds.isValid()).toBe(true);
 expect(bounds.getNorth()).toBeLessThan(32.84);
 expect(bounds.getSouth()).toBeGreaterThanOrEqual(32.75);
});

test('populated street data becomes the actual pan boundary', async () => {
 const streets = {type:'FeatureCollection',features:[{type:'Feature',properties:{name:'Test Street'},geometry:{type:'LineString',coordinates:[
  [-79.96,32.76],[-79.95,32.77],[-79.94,32.78],[-79.93,32.79],[-79.92,32.80],
  [-79.91,32.81],[-79.90,32.82],[-79.89,32.83],[-79.88,32.84],[-79.87,32.85],
 ]}}]};
 vi.stubGlobal('fetch',vi.fn(async (url:string) => ({ok:true,json:async () => url.endsWith('manifest') ? manifest : streets})));
 const create=vi.spyOn(L,'map');
 render(<OfflineMap incidents={[]} resources={[]} />);
 await waitFor(() => {
  const map=create.mock.results[0].value as L.Map;
  expect(map.options.maxBounds).toBeDefined();
  const bounds = map.options.maxBounds!;
   expect((bounds instanceof L.LatLngBounds ? bounds : L.latLngBounds(bounds)).getNorth()).toBeLessThan(32.86);
 });
});
