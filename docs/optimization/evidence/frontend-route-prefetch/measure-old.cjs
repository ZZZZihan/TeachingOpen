async (page) => {
  const port=18162;
  await page.setViewportSize({width:1440,height:1000});
  await page.addInitScript(()=>performance.setResourceTimingBufferSize(2000));
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Network.enable'); await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
  const rows=[];
  for(let i=0;i<5;i++){
    await cdp.send('Network.clearBrowserCache');
    const began=Date.now();
    await page.goto('http://127.0.0.1:'+port+'/index',{waitUntil:'load'});
    await page.waitForFunction(()=>document.querySelectorAll('.course-card-button').length===3 && document.querySelector('.course-preview')?.getAttribute('aria-busy')==='false');
    const courseReadyMs=Date.now()-began;
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('.course-card-button img')).every(x=>x.complete&&x.naturalWidth>0));
    await page.waitForTimeout(2500);
    const data=await page.evaluate(()=>{
      const nav=performance.getEntriesByType('navigation')[0];
      const same=performance.getEntriesByType('resource').filter(r=>new URL(r.name).origin===location.origin);
      const js=same.filter(r=>new URL(r.name).pathname.endsWith('.js'));
      const css=same.filter(r=>new URL(r.name).pathname.endsWith('.css'));
      return {domContentLoadedMs:Math.round(nav.domContentLoadedEventEnd),loadMs:Math.round(nav.loadEventEnd),fcpMs:Math.round(performance.getEntriesByName('first-contentful-paint')[0]?.startTime||0),sameOriginResourceCount:same.length,transferBytes:same.reduce((a,r)=>a+r.transferSize,0),encodedBytes:same.reduce((a,r)=>a+r.encodedBodySize,0),decodedBytes:same.reduce((a,r)=>a+r.decodedBodySize,0),jsRequests:js.length,jsBytes:js.reduce((a,r)=>a+r.decodedBodySize,0),cssRequests:css.length,cssBytes:css.reduce((a,r)=>a+r.decodedBodySize,0),prefetchHints:document.querySelectorAll('link[rel=prefetch]').length,preloadHints:document.querySelectorAll('link[rel=preload]').length,courseCards:document.querySelectorAll('.course-card-button').length,overflow:document.documentElement.scrollWidth>innerWidth};
    });
    rows.push({sample:i+1,courseReadyMs,...data});
  }
  await cdp.send('Network.setCacheDisabled',{cacheDisabled:false});await cdp.detach();
  return {port,viewport:{width:1440,height:1000},cache:'Network cache disabled and browser cache cleared before each sample; resource timing buffer 2000; fixed 2500ms after visible course cards; server/OS caches untouched.',scope:'Same anonymous isolated production-derived API/data, same source base; five loopback samples without network/CPU throttling. No capacity or public-network latency claim.',rows};
}
