const {chromium}=require('playwright');const fs=require('node:fs');
(async()=>{
 const creds=JSON.parse(fs.readFileSync(process.env.ADMIN_CREDENTIALS_FILE,'utf8'));
 const b=await chromium.connectOverCDP('http://127.0.0.1:9223');
 for (const old of b.contexts().slice(1)) { if (old.pages().every(p=>p.url().startsWith('http://localhost:8097'))) await old.close(); }
 const context=await b.newContext({viewport:{width:1440,height:1000}});const p=await context.newPage();const errors=[];
 p.on('pageerror',e=>errors.push(e.message));
 const base='http://localhost:8097'; const qaUsername='qa-reception-'+Date.now();
 await p.goto(base+'/admin/login/');await p.locator('#id_username').fill(creds.username);await p.locator('#id_password').fill(creds.password);
 await Promise.all([p.waitForURL(base+'/admin/'),p.locator('input[type=submit]').click()]);
 if(!await p.getByText('Что нужно сделать?',{exact:true}).count())throw Error('Dashboard did not load');
 const results=[];
 for(const [name,width,height] of [['desktop',1440,1000],['tablet',768,1024],['phone',360,800]]){
  await p.setViewportSize({width,height});await p.screenshot({path:`docs/performance-results/admin-${name}.png`,fullPage:true});
  const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth); if(overflow)throw Error('Admin overflow at '+width+' '+JSON.stringify(await p.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,15).map(e=>({tag:e.tagName,id:e.id,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right,display:getComputedStyle(e).display}))))); results.push({name,overflow,sidebarVisible:await p.locator('.workspace-sidebar').isVisible()});
  if(width<900){await p.locator('.workspace-mobile-nav summary').click();await p.locator('.workspace-sidebar nav').waitFor({state:'visible'});await p.locator('.workspace-mobile-nav summary').click();}
 }
 await p.setViewportSize({width:1440,height:1000});await p.goto(base+'/admin/auth/user/add/');
 await p.locator('#id_username').fill(qaUsername);await p.locator('#id_first_name').fill('Проверка');await p.locator('#id_last_name').fill('Регистрации');await p.locator('#id_role').selectOption('registration');
 await p.locator('#id_password1').fill('Audit-only-user-pass-704!');await p.locator('#id_password2').fill('Audit-only-user-pass-704!');
 await Promise.all([p.waitForURL('**/admin/auth/user/'),p.locator('input[name=_save]').click()]);
 if(!await p.getByText(qaUsername,{exact:true}).count())throw Error('Staff creation failed');
 await p.locator('#logout-form button').click(); await p.goto(base+'/admin/login/');
 await p.locator('#id_username').fill(qaUsername); await p.locator('#id_password').fill('Audit-only-user-pass-704!');
 await Promise.all([p.waitForURL(base+'/admin/'),p.locator('input[type=submit]').click()]);
 if(await p.locator('.workspace-sidebar').getByRole('link',{name:'Сотрудники',exact:true}).count())throw Error('Staff sees account management');
 const denied=await p.goto(base+'/admin/auth/user/add/'); if(denied.status()!==403)throw Error('Staff can create accounts');
 await p.goto(base+'/admin/'); await p.locator('#logout-form button').click(); await p.goto(base+'/admin/login/');
 await p.locator('#id_username').fill(creds.username); await p.locator('#id_password').fill(creds.password);
 await Promise.all([p.waitForURL(base+'/admin/'),p.locator('input[type=submit]').click()]);
 results.push({staffPasswordLogin:true,staffAccountCreationDenied:true});

 for(const path of ['/admin/forums/event/','/admin/forums/event/add/','/admin/voting/nomination/','/admin/registrations/registration/','/admin/auth/user/add/']){
   await p.goto(base+path);if(await p.locator('body').innerText().then(s=>s.includes('Traceback')))throw Error(path+' backend error');
   for(const width of [360,768,1440]){ await p.setViewportSize({width,height:900}); const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth); if(overflow)throw Error('Form overflow '+path+' '+width); results.push({path,width,title:await p.title(),overflow}); }
 }
 await p.goto(base+'/admin/');await p.screenshot({path:'docs/performance-results/admin-desktop.png',fullPage:true});
 console.log(JSON.stringify({results,errors}));
 fs.writeFileSync('docs/performance-results/admin-smoke.json',JSON.stringify({results,errors},null,2));
 await context.close();await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
