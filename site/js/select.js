(function(){
  'use strict';
  function enhance(select){
    if(select.dataset.enhanced)return;select.dataset.enhanced='true';
    var wrapper=document.createElement('div');wrapper.className='forum-select';select.before(wrapper);wrapper.append(select);
    var label=document.querySelector('label[for="'+select.id+'"]'),button=document.createElement('button'),value=document.createElement('span'),list=document.createElement('div'),index=0,typed='',timer;
    button.type='button';button.id=select.id+'-button';button.className='forum-select-button';button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');value.id=select.id+'-value';button.append(value);
    var chevron=document.createElement('span');chevron.className='forum-select-chevron';chevron.setAttribute('aria-hidden','true');button.append(chevron);
    list.id=select.id+'-options';list.className='forum-select-options';list.setAttribute('role','listbox');list.hidden=true;button.setAttribute('aria-controls',list.id);
    if(label){label.id=label.id||select.id+'-label';label.htmlFor=button.id;button.setAttribute('aria-labelledby',label.id+' '+value.id);list.setAttribute('aria-labelledby',label.id);}
    wrapper.append(button,list);select.classList.add('enhanced-native-select');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
    var options=[...select.options].filter(function(o){return o.value;}).map(function(option,i){var el=document.createElement('div');el.id=select.id+'-option-'+i;el.setAttribute('role','option');el.textContent=option.text;el.dataset.value=option.value;el.addEventListener('pointerdown',function(e){e.preventDefault();});el.addEventListener('click',function(){choose(i);});list.append(el);return el;});
    function sync(){value.textContent=select.options[select.selectedIndex].text;button.classList.toggle('is-placeholder',!select.value);options.forEach(function(o,i){o.setAttribute('aria-selected',o.dataset.value===select.value);if(o.dataset.value===select.value)index=i;});if(select.value)button.removeAttribute('aria-invalid');}
    function highlight(){options.forEach(function(o,i){o.classList.toggle('is-active',i===index);});button.setAttribute('aria-activedescendant',options[index].id);var option=options[index],top=option.offsetTop,bottom=top+option.offsetHeight;if(top<list.scrollTop+6)list.scrollTop=Math.max(0,top-6);else if(bottom>list.scrollTop+list.clientHeight-6)list.scrollTop=bottom-list.clientHeight+6;}
    function open(){list.hidden=false;button.setAttribute('aria-expanded','true');wrapper.classList.add('is-open');list.scrollTop=0;highlight();}
    function close(){list.hidden=true;button.setAttribute('aria-expanded','false');button.removeAttribute('aria-activedescendant');wrapper.classList.remove('is-open');}
    function choose(i){select.value=options[i].dataset.value;select.dispatchEvent(new Event('change',{bubbles:true}));sync();close();button.focus();}
    button.addEventListener('click',function(){if(list.hidden)open();else close();});
    button.addEventListener('keydown',function(e){if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();if(list.hidden){open();return;}index=e.key==='Home'?0:e.key==='End'?options.length-1:(index+(e.key==='ArrowDown'?1:-1)+options.length)%options.length;highlight();}else if(e.key==='Enter'||e.key===' '){e.preventDefault();if(list.hidden)open();else choose(index);}else if(e.key==='Escape'){e.preventDefault();close();}else if(e.key==='Tab')close();else if(e.key.length===1&&!e.ctrlKey&&!e.metaKey){typed+=e.key.toLocaleLowerCase();clearTimeout(timer);timer=setTimeout(function(){typed='';},650);var match=options.findIndex(function(o){return o.textContent.toLocaleLowerCase().startsWith(typed);});if(match>=0){index=match;if(list.hidden)open();highlight();}}});
    document.addEventListener('pointerdown',function(e){if(!wrapper.contains(e.target))close();});
    select.addEventListener('change',sync);select.addEventListener('invalid',function(e){e.preventDefault();button.setAttribute('aria-invalid','true');button.focus();open();});
    if(select.form)select.form.addEventListener('reset',function(){setTimeout(sync,0);});sync();
  }
  function init(){document.querySelectorAll('select[data-enhance-select]').forEach(enhance);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
