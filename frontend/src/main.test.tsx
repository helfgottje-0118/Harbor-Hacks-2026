import React from 'react';
import { afterEach, test, expect, vi } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { App } from './main';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function setup() {
 const fetcher = vi.fn(async (url:string, _options?:RequestInit) => ({ok:true,json:async ():Promise<unknown> => url.includes('/maps/') ? (url.endsWith('manifest') ? {sources:{}} : {type:'FeatureCollection',features:[]}) : url.endsWith('/status') ? {backend:'OK'} : []}));
 vi.stubGlobal('fetch',fetcher); return fetcher;
}
test('board identifies stale reports and keeps coordinate navigation local', async () => {
 const fetcher = setup();
 const standard = fetcher.getMockImplementation()!;
 fetcher.mockImplementation(async (url,options) => url === '/api/incidents' ? {ok:true,json:async () => [{id:9,category:'FLOOD',description:'Test report',timestamp:'2020-01-01T00:00:00Z',observed_at:null,source:'WEB',severity:'HIGH',people_affected:1,status:'OPEN',latitude:32.78,longitude:-79.93,water_depth_cm:0}]} : standard(url,options));
 render(<App/>);
 await screen.findAllByText('Test report');
 const card = screen.getAllByText('Test report').map(node => node.closest('article')).find(article => article?.classList.contains('incident'))!;
 expect(card.textContent).toContain('STALE');
 expect(card.textContent).toContain('Reported water depth: 0 cm');
 expect(card.querySelector('a')?.getAttribute('href')).toBe('#map-heading');
});
test('failed refresh retains last successful update and exposes failure rather than live claims', async () => {
 const fetcher = setup(); render(<App/>);
 await screen.findByText(/Last successful update:/);
 const last = screen.getByText(/Last successful update:/).textContent;
 fetcher.mockImplementation(async () => { throw new Error('local server unreachable'); });
 fireEvent.click(screen.getByText('Refresh'));
 await screen.findByText(/Refresh failed: local server unreachable/);
 expect(screen.getByText(/Last successful update:/).textContent).toBe(last);
});
test('submits optional reported depth including zero and resource coordinates with the existing forms', async () => {
 const fetcher = setup(); render(<App/>);
 await screen.findByText('Backend OK');
 fireEvent.change(screen.getByLabelText('Reported water depth (cm, optional)'),{target:{value:'0'}});
 fireEvent.click(screen.getByText('Submit + Auto Triage'));
 await waitFor(() => expect(fetcher.mock.calls.some(([url,init]) => url === '/api/incidents' && init?.body && JSON.parse(init.body as string).water_depth_cm === 0)).toBe(true));
 fireEvent.change(screen.getByLabelText('Resource latitude'),{target:{value:'32.78'}});
 fireEvent.change(screen.getByLabelText('Resource longitude'),{target:{value:'-79.93'}});
 fireEvent.click(screen.getByText('Add Resource'));
 await waitFor(() => expect(fetcher.mock.calls.some(([url,init]) => url === '/api/resources' && init?.body && JSON.parse(init.body as string).latitude === 32.78 && JSON.parse(init.body as string).longitude === -79.93)).toBe(true));
 expect(screen.queryByText(/LoRa simulation only/)).not.toBeInTheDocument();
 expect(screen.getByRole('heading',{name:/Offline Operations Map/}).compareDocumentPosition(screen.getByRole('heading',{name:'Incident Priority Board'})) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
test('renders a chronological command timeline from incidents and tasks', async () => {
 const fetcher = setup();
 const standard = fetcher.getMockImplementation()!;
 fetcher.mockImplementation(async (url,options) => url === '/api/incidents' ? {ok:true,json:async () => [{id:9,category:'FLOOD',description:'Timeline flood',timestamp:'2026-10-21T00:00:00Z',source:'WEB',severity:'HIGH',people_affected:1,status:'OPEN'}]} : url === '/api/tasks' ? {ok:true,json:async () => [{id:3,title:'Deploy Team Alpha',priority:'HIGH',status:'OPEN',created_at:'2026-10-21T00:10:00Z'}]} : standard(url,options));
 render(<App/>);
 await screen.findByRole('heading',{name:'Command Timeline'});
 expect(screen.getAllByText('Timeline flood').length).toBeGreaterThan(0);
 expect(screen.getAllByText('Deploy Team Alpha').length).toBeGreaterThan(0);
});
