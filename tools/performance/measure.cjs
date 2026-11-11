const { chromium, webkit } = require('playwright');
const fs = require('node:fs');
const profiles = {
  desktop: { width: 1440, height: 900, deviceScaleFactor: 1, cpu: 1 },
  phone1g: { width: 360, height: 740, deviceScaleFactor: 2, isMobile: true, hasTouch: true, cpu: 10, latency: 150, bandwidth: 200000 },
  phone2g: { width: 390, height: 844, deviceScaleFactor: 3, isMobile: true, hasTouch: true, cpu: 6, latency: 150, bandwidth: 200000 },
  tablet1g: { width: 768, height: 1024, deviceScaleFactor: 2, isMobile: true, hasTouch: true, cpu: 6, latency: 150, bandwidth: 200000 },
  tablet2g: { width: 1024, height: 768, deviceScaleFactor: 2, isMobile: true, hasTouch: true, cpu: 4, latency: 80, bandwidth: 500000 },
  veryweak: { width: 320, height: 640, deviceScaleFactor: 1, isMobile: true, hasTouch: true, cpu: 12, latency: 300, bandwidth: 100000 },
};
(async () => {
  const [variant='before', profileName='desktop', output='/results/result.json'] = process.argv.slice(2);
  const p = profiles[profileName];
  const browser = await chromium.launch({headless:true,args:['--disable-dev-shm-usage']});
  const results=[];
  for (const path of (process.env.MEASURE_PATHS ? JSON.parse(process.env.MEASURE_PATHS) : ['/', '/promtour/', '/contest/'])) {
    const context = await browser.newContext({ viewport:{width:p.width,height:p.height}, deviceScaleFactor:p.deviceScaleFactor,isMobile:!!p.isMobile,hasTouch:!!p.hasTouch });
    await context.addInitScript(() => {
      window.__perf={lcp:0,cls:0,longTasks:[]};
      new PerformanceObserver(l=>l.getEntries().forEach(e=>window.__perf.lcp=e.startTime)).observe({type:'largest-contentful-paint',buffered:true});
      new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)window.__perf.cls+=e.value;})).observe({type:'layout-shift',buffered:true});
      new PerformanceObserver(l=>l.getEntries().forEach(e=>window.__perf.longTasks.push(e.duration))).observe({type:'longtask',buffered:true});
    });
    const page=await context.newPage();
    const errors=[],failed=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('requestfailed',r=>failed.push({url:r.url(),error:r.failure()?.errorText}));
    const cdp=await context.newCDPSession(page);
    await cdp.send('Performance.enable');
    await cdp.send('Network.enable');
    await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
    await cdp.send('Emulation.setCPUThrottlingRate',{rate:p.cpu});
    if(p.bandwidth)await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:p.latency,downloadThroughput:p.bandwidth,uploadThroughput:p.bandwidth,connectionType:'cellular4g'});
    let bytes=0,requests=0;
    cdp.on('Network.loadingFinished',e=>bytes+=e.encodedDataLength);
    cdp.on('Network.requestWillBeSent',()=>requests++);
    const start=Date.now();
    let navigationError;
    try { await page.goto(`${process.env.BASE_URL||'http://'+variant}${path}`,{waitUntil:'load',timeout:30000}); }
    catch(e){ navigationError=e.message.split('\n')[0]; }
    if (!navigationError && variant === 'after') {
      await page.locator(path.includes('contest') ? '[data-nomination-card]' : '[data-speaker-circles] button').first().waitFor({timeout:20000});
    }
    await page.waitForTimeout(1500);
    const initial=await page.evaluate(()=>({
      ...window.__perf, fcp:performance.getEntriesByName('first-contentful-paint')[0]?.startTime||0,
      dom:document.querySelectorAll('*').length,images:[...document.images].length,
      loadedImages:[...document.images].filter(i=>i.complete&&i.naturalWidth).length,
      decodedImageMiB:[...document.images].filter(i=>i.complete).reduce((a,i)=>a+i.naturalWidth*i.naturalHeight*4,0)/1048576,
      overflow:document.documentElement.scrollWidth>innerWidth,
      resources:performance.getEntriesByType('resource').map(r=>({name:r.name,duration:r.duration,bytes:r.transferSize})),
    }));
    const loadBytes=bytes;
    if (!navigationError && (!initial.fcp || !initial.lcp)) throw new Error('Browser did not report a paint; do not publish a zero LCP');
    const beforeScroll=(await cdp.send('Performance.getMetrics')).metrics;
    const scroll=await page.evaluate(async()=>{
      const frames=[];let previous=0; const start=performance.now();
      let mutations=0;const observer=new MutationObserver(r=>mutations+=r.length);observer.observe(document.body,{subtree:true,childList:true,characterData:true});
      await new Promise(resolve=>{
        function tick(now){if(previous)frames.push(now-previous);previous=now;
          const elapsed=now-start;
          window.scrollTo({top:Math.min(1,elapsed/3500)*(document.documentElement.scrollHeight-innerHeight),behavior:'instant'});
          if(elapsed<4000)requestAnimationFrame(tick);else resolve();}
        requestAnimationFrame(tick);
      });
      observer.disconnect();frames.sort((a,b)=>a-b);
      return {frames:frames.length,frameP95:frames[Math.floor(frames.length*.95)],slowFrames:frames.filter(x=>x>50).length,mutations};
    });
    const metrics=Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(x=>[x.name,x.value]));
    const previous=Object.fromEntries(beforeScroll.map(x=>[x.name,x.value]));
    const final=await page.evaluate(()=>({cls:window.__perf.cls,longTasks:window.__perf.longTasks,overflow:document.documentElement.scrollWidth>innerWidth,brokenImages:[...document.images].filter(i=>i.complete&&!i.naturalWidth).map(i=>i.src)}));
    const memory=Number(fs.readFileSync('/sys/fs/cgroup/memory.peak','utf8'))/1048576;
    const result={variant,profile:profileName,path,elapsed:Date.now()-start,navigationError,fcp:initial.fcp,lcp:initial.lcp,cls:final.cls,loadBytes,bytes,requests,dom:initial.dom,images:initial.images,initialLoadedImages:initial.loadedImages,initialDecodedMiB:initial.decodedImageMiB,heapMiB:metrics.JSHeapUsedSize/1048576,scrollTaskMs:(metrics.TaskDuration-previous.TaskDuration)*1000,scrollLayoutMs:(metrics.LayoutDuration-previous.LayoutDuration)*1000,scroll,peakContainerMiB:memory,overflow:final.overflow,errors,failed,brokenImages:final.brokenImages,longTasks:final.longTasks,resources:initial.resources};
    results.push(result);console.log(JSON.stringify({...result,resources:undefined,longTasks:result.longTasks.length}));
    await page.screenshot({path:output.replace('.json',path.replaceAll('/','_')+'.png'),fullPage:false});
    await context.close();
  }
  await browser.close();fs.writeFileSync(output,JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
