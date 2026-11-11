const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const engine=process.env.ENGINE||'chromium',base=process.env.BASE_URL||'http://after',browser=await({chromium,webkit}[engine]).launch({headless:true,args:engine==='chromium'?['--disable-dev-shm-usage']:[]}),results=[];
 for(const width of [320,360,390,768,1024,1440]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(new URL(r.url()).origin!==new URL(base).origin)external.push(new URL(r.url()).hostname)});
  await page.goto(base+'/');await page.locator('[data-speaker-circles] button').first().waitFor();
  assert.equal(await page.locator('[data-speaker-circles] button').count(),13);assert.equal(await page.locator('iframe').count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.locator('[data-speaker-circles] button').first().click();assert.equal(await page.locator('[data-speaker-dialog]').evaluate(d=>d.open),true);await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(()=>document.activeElement.matches('[data-speaker-circles] button')),true);
  if(width<=1024){const opener=page.locator('[data-menu-open]');if(await opener.isVisible()){await opener.click();await page.locator('[data-site-mobile-navigation] a').first().click();assert.equal(await page.locator('#mobile-menu').evaluate(el=>el.classList.contains('is-open')),false)}}
  assert.equal(await page.locator('[data-registration-form]').isHidden(),process.env.REGISTRATION_OPEN!=='1');
  await page.goto(base+'/contest/');await page.locator('[data-nomination-card]').first().waitFor();
  assert.equal(await page.locator('[data-nomination-card]').count(),8);assert.equal(await page.locator('[data-skip-nomination]').count(),0);
  assert.equal(await page.locator('#vote-email').isHidden(),true);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.locator('[data-nomination-card]').first().evaluate(el=>el.open=true);
  for(let i=0;i<4;i++)await page.locator('[data-nomination-card]').first().locator('[data-nominee]').nth(i).click();
  assert.equal(await page.locator('[data-nominee]:checked').count(),3);
  await page.locator('[data-nominee-info]').first().click();assert.equal(await page.locator('[data-nominee-dialog]').evaluate(d=>d.open),true);await page.keyboard.press('Escape');assert.equal(await page.locator('[data-nominee]:checked').count(),3);
  assert.equal(await page.locator('[data-nominee]').count(),79);assert.deepEqual(errors,[]);assert.ok(external.every(host=>host==='sibforum-tomsk-media-2026.storage.yandexcloud.net'));
  await page.screenshot({path:'/results/meeting-'+engine+'-'+width+'.png',fullPage:false});results.push({engine,width,errors,external,checks:12});await context.close();
 }
 fs.writeFileSync('/results/meeting-'+engine+'-responsive.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
