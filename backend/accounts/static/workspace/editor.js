(function () {
  'use strict';
  var groups = JSON.parse(document.getElementById('editor-catalog-data').textContent);
  var frame = document.getElementById('editor-frame'), panel = document.getElementById('editor-panel');
  var current = null, dirty = false, loading = false, page = 'forum', pendingScroll = null;
  var initialSection = new URLSearchParams(location.search).get('section');
  var urls = new Map(), status = document.getElementById('editor-status');
  function send(data) { frame.contentWindow.postMessage(data, location.origin); }
  function all() { return groups.flatMap(function (g) { return g.items; }); }
  function setStatus(text) { status.textContent = text; }
  function tab(name) {
    document.body.dataset.tab = name;
    document.querySelectorAll('[data-tab]').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.tab === name); });
  }
  function renderCatalog() {
    var list = document.getElementById('editor-records'), search = document.getElementById('editor-search').value.toLocaleLowerCase();
    list.replaceChildren();
    groups.forEach(function (g) {
      var items = g.items.filter(function (i) { return (i.label+' '+g.title).toLocaleLowerCase().includes(search); });
      if (search && !items.length) return;
      var d = document.createElement('details'), summary = document.createElement('summary');
      summary.textContent = g.title+' ('+items.length+')';d.append(summary);d.open = !!search || g.kind === 'section';
      items.forEach(function (i) {
        var b = document.createElement('button');b.type = 'button';b.dataset.record = i.kind+':'+i.id;
        if (i.image) { var image = document.createElement('img');image.src=i.image;image.alt='';image.loading='lazy';b.append(image); }
        b.append(document.createTextNode(i.label));b.onclick=function(){ choose(i); };d.append(b);
      });
      if(g.create_url){var add=document.createElement('button');add.type='button';add.className='editor-add';add.textContent=g.kind==='logo'?'＋ Добавить организацию':'＋ Добавить контакт';add.onclick=function(){choose({kind:g.kind,id:'new',label:g.kind==='logo'?'Новая организация':'Новый контакт'});};d.append(add);}
      else if(g.add_url){var a=document.createElement('a');a.href=g.add_url;a.target='_blank';a.rel='noopener';a.textContent='Добавить новую запись';d.append(a);}
      list.append(d);
    });
  }
  function allowChange() {
    if (!dirty) return Promise.resolve(true);
    var dialog = document.getElementById('editor-discard');dialog.showModal();
    return new Promise(function (resolve) {
      function click(e) { var b=e.target.closest('[data-discard]');if(!b)return;dialog.close(b.dataset.discard); }
      function close() { dialog.removeEventListener('click',click);resolve(dialog.returnValue==='discard'); }
      dialog.addEventListener('click',click);dialog.addEventListener('close',close,{once:true});
    });
  }
  async function choose(item, field) {
    if (loading || !(await allowChange())) return;
    if(dirty)reloadFrame();
    loading=true;setStatus('Открываем: '+item.label);
    try {
      var r=await fetch('/admin/site-editor/object/'+item.kind+'/'+item.id+'/',{headers:{Accept:'application/json'}});
      if(r.redirected)throw Error('Сессия завершилась. Войдите в панель заново.');if(!r.ok)throw Error('Не удалось открыть запись. Проверьте доступ и подключение.');
      var data=await r.json();current=item;dirty=false;panel.innerHTML=data.html;panel.scrollTop=0;
      releaseUrls();setStatus('Редактирование: '+item.label);send({type:'select',item:item});tab('form');
      var input=field&&panel.querySelector('[name="'+field+'"]');if(input){input.focus({preventScroll:true});input.scrollIntoView({block:'nearest'});}
      updateImages();
    } catch(e) {setStatus(e.message);} finally{loading=false;}
  }
  function releaseUrls(){urls.forEach(function(u){URL.revokeObjectURL(u.url);});urls.clear();}
  function blob(input){if(!input||!input.files||!input.files[0])return '';var old=urls.get(input);if(old&&old.file===input.files[0])return old.url;if(old)URL.revokeObjectURL(old.url);var u=URL.createObjectURL(input.files[0]);urls.set(input,{file:input.files[0],url:u});return u;}
  function value(form,name){var el=form.elements.namedItem(name);return el?el.type==='checkbox'?el.checked:el.value:'';}
  function updateImages(){
    var form=panel.querySelector('form');if(!form||form.dataset.kind!=='speaker')return;
    var preview=form.querySelector('[data-speaker-preview]');if(!preview)return;
    var base=blob(form.elements.photo)|| (value(form,'photo-clear')?form.dataset.staticBase:preview.dataset.baseUrl),photos={};
    form.querySelectorAll('[data-placement]').forEach(function(row){
      var placement=row.dataset.placement,prefix='photo-'+placement+'-';
      photos[placement]={url:blob(form.elements.namedItem(prefix+'image'))||(value(form,prefix+'image-clear')?'':row.dataset.original)||base,fit:value(form,prefix+'fit'),x:value(form,prefix+'focal_x'),y:value(form,prefix+'focal_y')};
    });
    var full=value(form,'full_name').trim().split(/\s+/),name=value(form,'short_name')||(full.length>1?full[1]+' '+full[0]:full[0]);
    preview.querySelectorAll('[data-photo-context]').forEach(function(fig){var p=photos[fig.dataset.photoContext]||{url:base,fit:'cover',x:50,y:25},img=fig.querySelector('img');img.src=p.url||'';img.style.objectFit=p.fit;img.style.objectPosition=p.x+'% '+p.y+'%';fig.querySelector('[data-preview-name]').textContent=name;fig.querySelector('[data-preview-position]').textContent=value(form,'short_position');});
    send({type:'patch',kind:'speaker',id:current.id,values:{short_name:name,short_position:value(form,'short_position'),full_name:value(form,'full_name')},photos:photos});
  }
  function changed(e){
    var form=panel.querySelector('#editor-object-form');if(!form||!e.target.name||e.target.name.startsWith('_'))return;
    dirty=true;form.querySelector('[data-draft-status]').textContent='Есть несохранённые изменения';setStatus('Черновик — нажмите «Сохранить на сайте»');
    var values={};form.querySelectorAll('input[name],textarea[name],select[name]').forEach(function(el){if(el.type!=='file'&&el.name!=='csrfmiddlewaretoken')values[el.name]=el.type==='checkbox'?el.checked:el.value;});
    send({type:'patch',kind:current.kind,id:current.id,key:current.key,values:values});updateImages();
    if(e.target.type==='file'&&current.kind!=='speaker'){var u=blob(e.target);if(u){var field=e.target.closest('[data-field]'),preview=field.querySelector('.editor-upload-preview');if(!preview){preview=document.createElement('img');preview.className='editor-upload-preview';preview.alt='Выбранное изображение до сохранения';field.append(preview);}preview.src=u;send({type:'image',item:current,field:e.target.name,url:u});}}
  }
  function reloadFrame(){try{pendingScroll=frame.contentWindow.scrollY;}catch(e){pendingScroll=0;}frame.src='/admin/site-editor/preview/'+page+'/?v='+Date.now();}
  panel.addEventListener('input',changed);panel.addEventListener('change',changed);
  panel.addEventListener('click',function(e){
    var add=e.target.closest('[data-add-row]');if(add){var group=add.closest('[data-formset]'),total=group.querySelector('[name$="-TOTAL_FORMS"]'),n=Number(total.value);if(n>=100){setStatus('Максимум 100 записей в этом блоке.');return;}var html=group.querySelector('template').innerHTML.replaceAll('__prefix__',String(n));group.querySelector('[data-formset-rows]').insertAdjacentHTML('beforeend',html);total.value=n+1;changed({target:total});}
    if(e.target.closest('[data-revert]')&&current){allowChange().then(function(ok){if(ok){dirty=false;reloadFrame();choose(current);}});}
    if(e.target.closest('[data-remove]')&&current&&!loading){
      var dialog=document.getElementById('editor-delete-dialog');dialog.querySelector('[data-delete-name]').textContent=current.label;dialog.returnValue='cancel';dialog.showModal();
      dialog.addEventListener('close',async function(){if(dialog.returnValue!=='delete')return;var form=panel.querySelector('form'),data=new FormData();data.set('csrfmiddlewaretoken',value(form,'csrfmiddlewaretoken'));data.set('_version',value(form,'_version'));data.set('confirm','delete');loading=true;
        try{var r=await fetch('/admin/site-editor/object/'+current.kind+'/'+current.id+'/delete/',{method:'POST',body:data});var result=await r.json();if(!r.ok)throw Error(result.message||'Не удалось удалить запись.');groups=result.catalog;dirty=false;current=null;releaseUrls();panel.innerHTML='<div class="editor-welcome"><h1>Запись удалена</h1><p>Выберите другой элемент на странице или добавьте новую организацию в списке слева.</p></div>';renderCatalog();reloadFrame();setStatus(result.message);}catch(error){setStatus(error.message);}finally{loading=false;}
      },{once:true});
    }
  });
  panel.addEventListener('submit',async function(e){
    if(e.target.id!=='editor-object-form')return;e.preventDefault();if(loading)return;
    var form=e.target,button=form.querySelector('[type=submit]');loading=true;button.disabled=true;button.textContent='Сохраняем…';setStatus('Сохраняем изменения…');
    try{
      var r=await fetch('/admin/site-editor/object/'+current.kind+'/'+current.id+'/',{method:'POST',body:new FormData(form),headers:{Accept:'application/json'}});
      if(r.status===403)throw Error('Нет прав на это действие. Обратитесь к руководителю.');
      if(![200,409,422].includes(r.status))throw Error('Не удалось сохранить. Проверьте подключение и повторите попытку.');
      var data=await r.json();if(data.html&&r.status!==422)panel.innerHTML=data.html;else if(data.html){var temp=document.createElement('template');temp.innerHTML=data.html;form.querySelectorAll('.has-error').forEach(function(el){el.classList.remove('has-error');});form.querySelectorAll('.errorlist,.editor-feedback').forEach(function(el){el.remove();});temp.content.querySelectorAll('.errorlist').forEach(function(error){var field=error.closest('[data-field]'),input=field&&field.querySelector('[name]'),target=input&&form.querySelector('[name=\"'+CSS.escape(input.name)+'\"]');if(target){target.closest('[data-field]').classList.add('has-error');target.closest('[data-field]').append(error.cloneNode(true));}else form.prepend(error.cloneNode(true));});var feedback=temp.content.querySelector('.editor-feedback');if(feedback)form.querySelector('.editor-form-head').after(feedback.cloneNode(true));}setStatus(data.message);
      if(data.saved){dirty=false;releaseUrls();groups=data.catalog;if(data.object_id){current=all().find(function(i){return i.kind===current.kind&&i.id===data.object_id;})||current;}renderCatalog();reloadFrame();}else{var error=panel.querySelector('.has-error input,.has-error textarea,.has-error select,.errorlist');if(error)error.scrollIntoView({block:'center'});}
    }catch(error){setStatus(error.message);}finally{loading=false;var b=panel.querySelector('[type=submit]');if(b){b.disabled=false;b.textContent='Сохранить на сайте';}}
  });
  window.addEventListener('message',function(e){
    if(e.origin!==location.origin||e.source!==frame.contentWindow)return;var d=e.data||{};
    if(d.type==='ready'){send({type:'catalog',groups:groups});if(pendingScroll!==null){send({type:'scroll',top:pendingScroll});pendingScroll=null;}if(current)send({type:'select',item:current});if(initialSection){var initial=all().find(function(i){return i.kind==='section'&&i.key===initialSection;});initialSection=null;if(initial)choose(initial);}}
    if(d.type==='edit'){var item=all().find(function(i){return i.kind===d.kind&&(d.id?i.id===d.id:i.key===d.key);});if(item)choose(item,d.field);else setStatus('Элемент можно изменить через «Все разделы и записи».');}
  });
  document.querySelectorAll('[data-page]').forEach(function(b){b.onclick=async function(){if(!(await allowChange()))return;dirty=false;page=b.dataset.page;document.querySelectorAll('[data-page]').forEach(function(x){x.setAttribute('aria-pressed',x===b);});pendingScroll=0;reloadFrame();};});
  document.querySelectorAll('[data-width]').forEach(function(b){b.onclick=function(){frame.style.width=b.dataset.width;document.querySelectorAll('[data-width]').forEach(function(x){x.setAttribute('aria-pressed',x===b);});};});
  document.querySelectorAll('[data-tab]').forEach(function(b){b.onclick=function(){tab(b.dataset.tab);};});
  document.getElementById('editor-search').addEventListener('input',renderCatalog);
  document.querySelectorAll('[data-delete-choice]').forEach(function(b){b.onclick=function(){document.getElementById('editor-delete-dialog').close(b.dataset.deleteChoice);};});
  function openCatalog(search){var c=document.getElementById('editor-catalog');c.hidden=false;document.getElementById('catalog-toggle').setAttribute('aria-expanded','true');document.getElementById('editor-search').value=search;renderCatalog();}
  document.getElementById('editor-labels').onclick=function(){openCatalog('Подписи и пояснения');};
  document.getElementById('editor-organizations').onclick=function(){openCatalog('Организаторы, партнёры и промтуризм');};
  document.getElementById('editor-jump').onchange=function(){var i=all().find(function(i){return i.kind==='section'&&i.key===this.value;},this);if(i)choose(i);};
  document.getElementById('catalog-toggle').onclick=function(){var catalog=document.getElementById('editor-catalog');if(catalog.hidden||document.getElementById('editor-search').value){openCatalog('');}else{catalog.hidden=true;this.setAttribute('aria-expanded','false');}};
  document.getElementById('editor-start').onclick=function(){choose(all().find(function(i){return i.kind==='section'&&i.key==='hero';}));};
  window.addEventListener('beforeunload',function(e){if(dirty){e.preventDefault();e.returnValue='';}});
  window.addEventListener('pagehide',releaseUrls);renderCatalog();tab('canvas');
})();
