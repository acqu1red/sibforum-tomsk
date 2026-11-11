const {chromium}=require('playwright');const fs=require('node:fs');
(async()=>{const b=await chromium.connectOverCDP('http://127.0.0.1:9223');const results=[];
for(const [variant,port] of [['before',8096],['after',8097]]){
 const c=await b.newContext({viewport:{width:1440,height:900}});const p=await c.newPage();const d=await c.newCDPSession(p);
 await d.send('Performance.enable');await d.send('Network.enable');await d.send('Network.setCacheDisabled',{cacheDisabled:true});
 await p.goto(`http://localhost:${port}/`,{waitUntil:'load',timeout:30000});await p.waitForTimeout(1500);
 const initial=Object.fromEntries((await d.send('Performance.getMetrics')).metrics.map(x=>[x.name,x.value]));
 const frames=await p.evaluate(async()=>{let prev;const a=[];const start=performance.now();await new Promise(resolve=>{function tick(t){if(prev)a.push(t-prev);prev=t;window.scrollTo({top:(document.documentElement.scrollHeight-innerHeight)*Math.min((t-start)/3500,1),behavior:'instant'});if(t-start<4000)requestAnimationFrame(tick);else resolve();}requestAnimationFrame(tick)});a.sort((x,y)=>x-y);return {frames:a.length,p95:a[Math.floor(a.length*.95)],over50ms:a.filter(x=>x>50).length};});
 const final=Object.fromEntries((await d.send('Performance.getMetrics')).metrics.map(x=>[x.name,x.value]));
 results.push({variant,frames,scrollTaskMs:(final.TaskDuration-initial.TaskDuration)*1000,heapMiB:final.JSHeapUsedSize/1048576});await c.close();}
await b.close();fs.writeFileSync('docs/performance-results/native-mac.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));})().catch(e=>{console.error(e);process.exit(1)});
