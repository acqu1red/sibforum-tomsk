(function () {
  'use strict';
  var disclosure = document.querySelector('.workspace-mobile-nav');
  if (disclosure) disclosure.addEventListener('toggle', function () {
    disclosure.closest('.workspace-sidebar').classList.toggle('is-open', disclosure.open);
  });
})();

(function () {
  'use strict';
  // Prepare the file before the click so mobile browsers retain the share gesture.
  var ticketFiles = new WeakMap();
  document.querySelectorAll('[data-share-ticket]').forEach(function (button) {
    button.disabled = true;
    fetch(button.dataset.shareTicket, {credentials: 'same-origin'}).then(async function (response) {
      if (!response.ok || response.redirected || !(response.headers.get('Content-Type') || '').includes('image/png')) throw Error('Билет недоступен. Обновите страницу и проверьте его статус.');
      var blob = await response.blob();
      ticketFiles.set(button, new File([blob], button.dataset.ticketFile, {type: 'image/png'}));
      button.disabled = false;
    }).catch(function (error) { button.closest('section').querySelector('[data-share-status]').textContent = error.message; });
  });
  document.addEventListener('click', async function (event) {
    var resend = event.target.closest('[data-registration-resend]');
    if (resend) {
      var status = resend.closest('.participant-tools').querySelector('[data-resend-status]');
      var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
      if (resend.disabled || !csrf) return;
      resend.disabled = true;
      status.textContent = 'Ставим письмо в очередь…';
      if (!resend.dataset.requestKey) resend.dataset.requestKey = crypto.randomUUID();
      try {
        var body = new URLSearchParams({request_key: resend.dataset.requestKey});
        var response = await fetch(resend.dataset.registrationResend, {method: 'POST', credentials: 'same-origin',
          headers: {'X-CSRFToken': csrf.value, 'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}, body: body});
        if (response.redirected) throw Error('Сессия завершилась. Войдите в панель заново.');
        var result = await response.json();
        if (!response.ok || !result.ok) throw Error(result.message || 'Не удалось поставить письмо в очередь.');
        status.textContent = result.message;
        resend.textContent = 'Письмо в очереди';
      } catch (error) { status.textContent = error.message; resend.disabled = false; }
    }
    var share = event.target.closest('[data-share-ticket]');
    if (share) {
      if (share.disabled) return;
      var shareStatus = share.closest('section').querySelector('[data-share-status]');
      share.disabled = true;
      try {
        var file = ticketFiles.get(share);
        if (!file) throw Error('QR-код ещё загружается. Повторите через несколько секунд.');
        if (navigator.canShare && navigator.canShare({files: [file]})) {
          await navigator.share({files: [file], title: 'QR-код билета на Сибирский форум'});
          shareStatus.textContent = 'QR-код передан через меню «Поделиться».';
        } else {
          var url = URL.createObjectURL(file), link = document.createElement('a');
          link.href = url; link.download = file.name; document.body.append(link); link.click(); link.remove();
          setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
          shareStatus.textContent = 'QR-код скачан. Прикрепите PNG-файл к сообщению участнику.';
        }
      } catch (error) { shareStatus.textContent = error.name === 'AbortError' ? 'Передача отменена. Можно скачать QR-код.' : error.message; }
      finally { share.disabled = false; }
    }
  });
})();
