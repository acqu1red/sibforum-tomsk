(function(){
  'use strict';
  var button=document.getElementById('camera-start'),video=document.getElementById('camera'),status=document.getElementById('camera-status');
  var stream=null,timer=null,busy=false,starting=false,generation=0,readerPromise;
  var canvas=document.createElement('canvas'),context=canvas.getContext('2d',{willReadFrequently:true});
  function reader(){if(window.jsQR)return Promise.resolve(window.jsQR);if(!readerPromise)readerPromise=new Promise(function(resolve,reject){var s=document.createElement('script');s.src='/static/workspace/vendor/jsQR-1.4.0.js';s.onload=function(){resolve(window.jsQR);};s.onerror=function(){readerPromise=null;reject(Error('Не удалось загрузить распознавание. Проверьте подключение.'));};document.head.append(s);});return readerPromise;}
  function stop(){generation++;starting=false;clearTimeout(timer);if(stream)stream.getTracks().forEach(function(t){t.stop();});stream=null;video.srcObject=null;video.classList.remove('active');button.textContent='Включить камеру';button.disabled=false;busy=false;}
  function found(value){var input=document.getElementById('ticket-code');input.value=value;stop();status.textContent='Код распознан. Открываем билет…';input.form.requestSubmit();}
  function pixels(source,width,height,max){var scale=Math.min(1,max/Math.max(width,height));canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));context.drawImage(source,0,0,canvas.width,canvas.height);return context.getImageData(0,0,canvas.width,canvas.height);}
  async function start(){
    if(starting)return;if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){status.textContent='Камера недоступна. Откройте страницу по HTTPS или выберите фотографию QR.';return;}
    starting=true;button.disabled=true;status.textContent='Разрешите доступ к камере…';var current=++generation;
    try{
      var next=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280}},audio:false});
      if(current!==generation){next.getTracks().forEach(function(t){t.stop();});return;}
      stream=next;video.srcObject=stream;video.classList.add('active');await video.play();
      var detector=null,decode=null;
      if(window.BarcodeDetector){try{var formats=await BarcodeDetector.getSupportedFormats();if(formats.includes('qr_code'))detector=new BarcodeDetector({formats:['qr_code']});}catch(e){/* use the bundled decoder */}}
      if(!detector)decode=await reader();if(current!==generation)return;
      starting=false;button.disabled=false;button.textContent='Выключить камеру';status.textContent='Наведите камеру на QR. Держите билет ровно, чтобы код целиком помещался в кадр.';
      async function tick(){if(!stream||current!==generation)return;if(!busy&&video.readyState>=2){busy=true;try{if(detector){var codes=await detector.detect(video);if(codes.length){found(codes[0].rawValue);return;}}else{var data=pixels(video,video.videoWidth,video.videoHeight,800),code=decode(data.data,data.width,data.height,{inversionAttempts:'dontInvert'});if(code){found(code.data);return;}}}catch(e){/* try the next frame */}finally{busy=false;}}if(stream)timer=setTimeout(tick,350);}
      tick();
    }catch(e){stop();status.textContent=e.name==='NotAllowedError'?'Доступ к камере не разрешён. Включите его в настройках браузера или выберите фото QR.':e.name==='NotFoundError'?'Камера не найдена. Выберите фотографию QR или найдите участника по имени.':e.message||'Не удалось открыть камеру. Используйте фотографию или поиск.';}
  }
  button.addEventListener('click',function(){if(stream||starting){stop();status.textContent='Камера выключена.';}else start();});
  document.getElementById('qr-file').addEventListener('change',async function(e){
    var file=e.target.files[0];if(!file)return;stop();if(file.size>15*1024*1024){status.textContent='Выберите фотографию до 15 МБ.';return;}status.textContent='Читаем QR с фотографии…';var url=URL.createObjectURL(file);
    try{var image=new Image();image.src=url;await image.decode();if(image.naturalWidth*image.naturalHeight>40000000)throw Error('Фотография слишком большая. Обрежьте её вокруг QR-кода.');var decode=await reader(),code=null;for(var size of [1000,1800]){var data=pixels(image,image.naturalWidth,image.naturalHeight,size);code=decode(data.data,data.width,data.height);if(code)break;}if(!code)throw Error('QR не найден. Выберите чёткое фото, где код виден целиком, или воспользуйтесь поиском.');found(code.data);}catch(error){status.textContent=error.message||'Не удалось прочитать фотографию.';}finally{URL.revokeObjectURL(url);e.target.value='';}
  });
  document.addEventListener('visibilitychange',function(){if(document.hidden)stop();});window.addEventListener('pagehide',stop);
})();
