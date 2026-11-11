const {chromium,webkit}=require('playwright');const fs=require('node:fs');
(async()=>{
 const type=process.env.ENGINE==='webkit'?webkit:chromium;const browser=await type.launch({headless:true});const results=[];
 for(const width of [320,360,768,1024,1440]){
  const context=await browser.newContext({viewport:{width,height:850},isMobile:width<1100,hasTouch:width<1100,reducedMotion:'reduce'});
  for(const path of ['/','/promtour/','/contest/']){
   const p=await context.newPage();const errors=[];const external=[];
   p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(!r.url().startsWith('http://after'))external.push(r.url())});
   await p.goto('http://after'+path);await p.waitForTimeout(500);
   if(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(`Overflow ${width} ${path}`);
   const initialExternal=external.slice();
   if(path==='/'){
    if(initialExternal.length)throw Error('Unrequested external resource before map click');
    if(await p.locator('iframe').count())throw Error('Map loaded before consent');
    await p.locator('[data-load-map]').click();await p.locator('.map iframe').waitFor();
   }
   if(path==='/promtour/'){
    await p.locator('.promtour-speaker-photo').first().click();await p.locator('dialog[open]').waitFor();await p.keyboard.press('Escape');
    if(await p.locator('dialog[open]').count())throw Error('Speaker dialog cannot be closed');
    if(!await p.locator('[data-registration-form]').isHidden())throw Error('Closed registration form visible');
   }
   if(path==='/contest/'){
    await p.locator('[data-nomination-card]').first().click();
    if(await p.locator('[data-nominee]').count()!==79)throw Error('Nominee count changed');
    if(!await p.locator('[data-ballot-form]').isHidden())throw Error('Closed ballot form visible');
   }
   results.push({engine:process.env.ENGINE||'chromium',width,path,errors,externalBeforeMap:initialExternal});
   await p.close();
  }
  await context.close();
 }
 await browser.close();fs.writeFileSync(`/results/smoke-${process.env.ENGINE||'chromium'}.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exit(1)});
