const CACHE='harbor-shell-v6-map-recovery-20261023';
const SHELL=['/manifest.webmanifest','/harbor-icon.svg','/harbor-logo.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>Promise.all(SHELL.map(url=>cache.add(url).catch(()=>null)))).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 if(event.request.method!=='GET')return;
 const url=new URL(event.request.url);
 if(url.origin!==location.origin)return;
 // Always fetch the current application HTML when online; never serve an old
 // cached dashboard after deploying updated HARBOR frontend code.
 if(event.request.mode==='navigate'||url.pathname==='/'){
  event.respondWith(fetch(event.request,{cache:'no-store'}).catch(()=>new Response('HARBOR requires the local server for the dashboard.',{status:503,headers:{'Content-Type':'text/plain'}})));
  return;
 }
 if(url.pathname.startsWith('/api/')&&!url.pathname.startsWith('/api/maps/'))return;
 event.respondWith(fetch(event.request).then(response=>{if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));}return response;}).catch(()=>caches.match(event.request).then(cached=>cached||caches.match('/'))));
});
