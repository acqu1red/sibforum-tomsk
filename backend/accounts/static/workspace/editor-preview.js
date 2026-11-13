(function(){
  'use strict';
  if(window.parent===window)return;
  var groups=[],selected=null,ready=false,draft=null,draftImage=null;
  function send(data){parent.postMessage(data,location.origin);}
  function item(kind,key){return groups.flatMap(function(g){return g.items;}).find(function(i){return i.kind===kind&&(i.id===key||i.key===key);});}
  function key(el,value,field){if(!value)return;el.dataset.visualEdit=value;if(field)el.dataset.visualField=field;el.setAttribute('title','Нажмите, чтобы изменить');}
  function decorate(){
    document.querySelectorAll('[data-edit]').forEach(function(el){key(el,el.dataset.edit);});
    document.querySelectorAll('[data-copy]').forEach(function(el){var a=el.dataset.copy.split('.'),i=item(a[0]==='contest'&&['heading','body'].includes(a[1])?'contest':'section',a[0]);if(!i&&a[0]==='contest')i=groups.flatMap(function(g){return g.items;}).find(function(i){return i.kind==='contest';});if(i)key(el,i.kind+':'+i.id,i.kind==='contest'?(a[1]==='heading'?'title':'description'):a[1]);});
    document.querySelectorAll('[data-ui]').forEach(function(el){var i=item('interface',el.dataset.ui);if(i)key(el,'interface:'+i.id,'value');});
    var page=groups.flatMap(function(g){return g.items;}).find(function(i){return i.kind==='page';});
    if(page){document.querySelectorAll('[data-page],.brand-logo,.promtour-hero-venue,.promtour-hero').forEach(function(el){if(!el.dataset.visualEdit)key(el,'page:'+page.id,el.dataset.page||'');});}
    document.querySelectorAll('[data-speaker-id]').forEach(function(el){key(el,'speaker:'+el.dataset.speakerId);});
    document.querySelectorAll('[data-nomination-card]').forEach(function(el){key(el,'nomination:'+el.dataset.nominationCard);});
    document.querySelectorAll('[data-editor-section]').forEach(function(el){var i=item('section',el.dataset.editorSection);if(i)key(el.querySelector('h2'),'section:'+i.id,'heading');});
    if(draft)patch(draft);if(draftImage)image(draftImage);if(selected)highlight(selected,false);
    if(!ready){ready=true;send({type:'ready'});}
  }
  function highlight(i,scroll){document.querySelectorAll('.visual-selected').forEach(function(el){el.classList.remove('visual-selected');});var el=document.querySelector('[data-visual-edit="'+i.kind+':'+i.id+'"]');if(el){el.classList.add('visual-selected');if(scroll)el.scrollIntoView({block:'center',behavior:'instant'});}}
  function text(selector,value){if(value===undefined)return;document.querySelectorAll(selector).forEach(function(el){if(el.textContent!==String(value))el.textContent=value;el.hidden=!value;});}
  function patch(d){var v=d.values||{},i=item(d.kind,d.id),selector='[data-visual-edit="'+d.kind+':'+d.id+'"]';
    if(d.kind==='section')Object.keys(v).forEach(function(k){text('[data-copy="'+(d.key||i&&i.key)+'.'+k+'"]',v[k]);});
    if(d.kind==='interface'){var uiKey=d.key||i&&i.key;text('[data-ui="'+uiKey+'"]',v.value);if(uiKey==='route_contact')document.querySelectorAll('[data-route-contact-label]').forEach(function(el){el.hidden=!v.value;var separator=el.querySelector('[data-contact-separator]');if(separator)separator.textContent=v.value&&!/[:：]\s*$/.test(v.value)?':':'';});}
    if(d.kind==='page')Object.keys(v).forEach(function(k){text('[data-page="'+k+'"]',v[k]);});
    if(d.kind==='contest'){text('[data-copy="contest.heading"],#contest-title',v.title);text('[data-copy="contest.body"]',v.description);}
    if(d.kind==='speaker')document.querySelectorAll('[data-speaker-id="'+d.id+'"]').forEach(function(el){textWithin(el,'b',v.short_name||v.full_name);var p=d.photos&&d.photos[el.closest('.promtour-event-speakers')?'program':el.classList.contains('promtour-person')?'circle':'card'];var img=el.querySelector('img');if(p&&p.url&&img){img.src=p.url;img.style.objectFit=p.fit;img.style.objectPosition=p.x+'% '+p.y+'%';}if(el.classList.contains('promtour-person'))textWithin(el,':scope>span:not(.promtour-photo-placeholder)',v.short_position);});
    if(d.kind==='event')document.querySelectorAll(selector).forEach(function(el){eventOrganizer(el,v.organizer);textWithin(el,'h3,h4',v.title);if(v.start_time&&v.end_time)textWithin(el,'time',v.start_time+'–'+v.end_time);if(v.contact_name!==undefined&&el.classList.contains('promtour-route')){var contact=el.querySelector('.promtour-route-contact');if(!contact){contact=document.createElement('p');contact.className='promtour-route-contact';el.querySelector('.promtour-route-facts').after(contact);}var signature=JSON.stringify([v.contact_name,v.contact_phone]);if(contact.dataset.draftContact===signature)return;contact.dataset.draftContact=signature;contact.replaceChildren();contact.hidden=!v.contact_name&&!v.contact_phone;var labelText=window.forumContent.text('route_contact','Контактное лицо');var bold=document.createElement('b'),label=document.createElement('span'),separator=document.createElement('span');bold.dataset.routeContactLabel='';bold.hidden=!labelText;label.dataset.ui='route_contact';label.textContent=labelText;separator.dataset.contactSeparator='';separator.textContent=labelText&&!/[:：]\s*$/.test(labelText)?':':'';bold.append(label,separator);contact.append(bold,' ',v.contact_name);if(v.contact_phone){var phone=document.createElement('a');phone.href='tel:'+v.contact_phone.replace(/[^+0-9]/g,'');phone.textContent=v.contact_phone;contact.append(' ',phone);}}});
    if(d.kind==='logo')document.querySelectorAll(selector).forEach(function(el){textWithin(el,'.promtour-logo-caption',v.name);var img=el.querySelector('img');if(img&&v.name!==undefined)img.alt=v.name;var caption=el.querySelector('.promtour-logo-caption');if(caption&&v.show_name!==undefined)caption.hidden=!v.show_name;if(v.image_background!==undefined)el.classList.toggle('promtour-logo-dark',v.image_background==='dark');});
    if(d.kind==='contact')document.querySelectorAll(selector).forEach(function(el){textWithin(el,'h3',v.title);textWithin(el,':scope>span',v.subtitle);var body=el.querySelector('.promtour-contact-body');if(body&&v.body!==undefined)textWithin(el,'.promtour-contact-body',(body.dataset.address?body.dataset.address+'\n':'')+v.body);[['person_name','.promtour-contact-person','span'],['phone','.promtour-contact-phone','a'],['email','.promtour-contact-email','a']].forEach(function(a){if(v[a[0]]===undefined)return;var row=el.querySelector(a[1]);if(!row)return;row.hidden=!v[a[0]];textWithin(row,a[2],v[a[0]]);if(a[0]==='phone')row.querySelector('a').href='tel:'+v.phone.replace(/[^+0-9]/g,'');if(a[0]==='email')row.querySelector('a').href='mailto:'+v.email;});});
    if(d.kind==='menu')text(selector,v.label);
  }
  function eventOrganizer(root,id){
    if(!root.classList.contains('promtour-event')||id===undefined)return;
    var signature=String(id);if(root.dataset.draftOrganizer===signature)return;root.dataset.draftOrganizer=signature;
    var old=root.querySelector('.promtour-event-organizer');if(old)old.remove();
    var company=id&&item('logo',id);if(!company)return;
    var details=root.querySelector('.promtour-event-details');
    if(!details){details=document.createElement('details');details.className='promtour-event-details';var summary=document.createElement('summary');summary.textContent='Подробнее';details.append(summary,document.createElement('div'));root.querySelector('.promtour-event-body').append(details);}
    details.open=true;
    var card=document.createElement('aside');card.className='promtour-event-organizer'+(company.background==='dark'?' promtour-logo-dark':'');card.dataset.edit='logo:'+company.id;
    var label=document.createElement('span');label.textContent='Организатор мероприятия';var body=document.createElement('div');
    if(company.image){var img=document.createElement('img');img.src=company.image;img.alt=company.name;img.width=160;img.height=80;body.append(img);}
    if(company.show_name!==false||!company.image){var name=document.createElement('b');name.className='promtour-logo-caption';name.textContent=company.name;body.append(name);}
    card.append(label,body);details.querySelector('div').append(card);
  }
  function textWithin(root,selector,value){if(value===undefined)return;root.querySelectorAll(selector).forEach(function(el){if(el.textContent!==String(value))el.textContent=value;});}
  window.addEventListener('message',function(e){if(e.origin!==location.origin||e.source!==parent)return;var d=e.data||{};if(d.type==='catalog'){groups=d.groups;decorate();}if(d.type==='select'){if(!selected||selected.kind!==d.item.kind||selected.id!==d.item.id){draft=null;draftImage=null;}selected=d.item;highlight(selected,true);}if(d.type==='scroll')window.scrollTo(0,d.top);if(d.type==='patch'){draft=d;patch(d);}if(d.type==='image'){draftImage=d;image(d);}});
  function image(d){if(d.item.kind==='page'){if(d.field==='hero_image')document.querySelector('.promtour-hero').style.setProperty('--forum-hero-image','url('+JSON.stringify(d.url)+')');if(d.field==='brand_logo')document.querySelectorAll('.brand-logo').forEach(function(img){if(img.src!==d.url)img.src=d.url;});}else document.querySelectorAll('[data-visual-edit="'+d.item.kind+':'+d.item.id+'"]').forEach(function(root){var img=root.querySelector('img');if(!img&&d.item.kind==='logo'){img=document.createElement('img');img.width=180;img.height=90;img.alt=root.querySelector('.promtour-logo-caption').textContent;root.prepend(img);}if(!img&&d.item.kind==='nominee'){var box=root.querySelector('.contest-candidate-logo');if(box){img=document.createElement('img');img.width=160;img.height=90;img.alt='';var name=box.textContent;box.replaceChildren(img);var caption=document.createElement('b');caption.textContent=name;box.after(caption);}}if(img&&img.src!==d.url)img.src=d.url;});}
  document.addEventListener('click',function(e){var el=e.target.closest('[data-visual-edit]');if(el){e.preventDefault();e.stopImmediatePropagation();var a=el.dataset.visualEdit.split(':');send({type:'edit',kind:a[0],id:a[1],field:el.dataset.visualField||(a[0]==='speaker'?(e.target.closest('img')?'photo':e.target.closest('b')?'short_name':''):'')});}else if(e.target.closest('a,button,input,select,textarea')){if(e.target.closest('summary'))return;e.preventDefault();e.stopImmediatePropagation();}},true);
  document.addEventListener('submit',function(e){e.preventDefault();e.stopImmediatePropagation();},true);
  var style=document.createElement('style');style.textContent='[data-visual-edit]{cursor:pointer!important;outline-offset:4px}[data-visual-edit]:hover{outline:2px dashed #e5b900}.visual-selected{outline:3px solid #e5b900!important}';document.head.append(style);
  var timer;new MutationObserver(function(){clearTimeout(timer);timer=setTimeout(decorate,80);}).observe(document.body,{childList:true,subtree:true});
  decorate();window.addEventListener('load',function(){send({type:'ready'});});
})();
