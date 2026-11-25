/* «Моя программа» по личной ссылке из письма (ТЗ, разд. 4.2): выбранные события, изменения, отмена участия,
   PDF, календарь .ics, QR-код участника. Без пароля — доступ по токену в ссылке. */
(function () {
  'use strict';
  var PR = window.PROGRAM, S = window.Schedule, API = window.API;
  var esc = window.escapeHtml, icon = window.icon, plural = window.plural;
  var token, reg;

  function $(s, r) { return (r || document).querySelector(s); }
  function ids() { return Object.keys(reg.events); }

  function personalLink() { return new URL('my.html?t=' + encodeURIComponent(token), location.href).href; }

  function renderEmpty(notFound) {
    $('[data-my-person]').textContent = notFound ? 'Ссылка устарела или указана с ошибкой' : 'Вы ещё не зарегистрированы';
    $('[data-my-list]').innerHTML = '<div class="empty-state my-empty"><h3>' + (notFound ? 'Регистрация не найдена' : 'Здесь появится ваша программа') + '</h3>' +
      '<p>Ссылку на эту страницу мы присылаем в письме после регистрации. Если вы ещё не зарегистрировались — это займёт около 3 минут.</p>' +
      '<a class="btn btn-primary" href="register.html">Зарегистрироваться</a></div>';
  }

  function statusHtml(it, st) {
    if (st.status === 'waitlist') {
      return '<span class="status status-wait">Лист ожидания' + (st.queue ? ' · ' + st.queue + '-й в очереди' : '') + '</span>';
    }
    return '<span class="status status-ok">' + icon('check') + (it.excursion ? 'Место подтверждено' : 'Записаны') + '</span>';
  }

  function cardHtml(r) {
    var it = r.item, st = reg.events[it.id] || {}, v = PR.venues[it.venue];
    return '<article class="s-card my-card' + (it.changedFrom ? ' is-changed' : '') + '" style="--c:' + S.trackColor(it) + '">' +
      '<div class="s-top"><span class="s-time">' + (it.changedFrom ? '<s>' + it.changedFrom + '</s>' : '') + S.range(it) + '</span>' +
      (it.changedFrom ? '<span class="badge badge-changed">Время изменено</span>' : '') + '</div>' +
      '<span class="tag" style="--c:' + S.trackColor(it) + '"><span class="dot"></span>' + esc(S.trackLabel(it)) + '</span>' +
      '<h3 class="s-title"><a class="s-open" href="program.html?day=' + r.day.id + '&s=' + it.id + '">' + window.hyph(esc(it.title)) + '</a></h3>' +
      '<p class="s-meta">' + icon('pin') + '<span>' + esc(S.placeText(it)) + ' · ' + esc(v.address) + '</span></p>' +
      (it.excursion ? '<p class="s-mod">' + esc(it.excursion.age) + ' · ' + esc(it.excursion.docs) + '. Подтвердить участие попросим за 3 дня.</p>' : '') +
      '<div class="s-foot">' + statusHtml(it, st) +
      '<button class="s-add" type="button" data-cancel="' + it.id + '">' + icon('x') + '<span>Отменить участие</span></button></div></article>';
  }

  function render() {
    var p = reg.person, list = S.sorted(ids());
    window.store.set(window.forumKey('sf-mine'), ids());
    window.store.set(window.forumKey('sf-reg'), { token: token, id: reg.id });

    $('[data-my-person]').innerHTML = '<span>' + icon('users') + esc(p.name) + '</span><span>' + esc(p.org) + (p.position ? ', ' + esc(p.position) : '') + '</span>';
    $('[data-my-status]').innerHTML =
      (reg.confirmed ? '<span class="badge badge-open"><span class="dot"></span>Регистрация подтверждена</span>' : '<span class="badge badge-changed">Подтвердите e-mail — код в письме</span>') +
      '<span class="badge badge-open">' + (p.format === 'online' ? 'Онлайн-участие' : 'Очное участие') + '</span>' +
      '<span class="badge badge-open">Заявка ' + esc(reg.id) + '</span>';
    $('[data-my-actions]').hidden = false;

    var qr = window.qrcode(0, 'M');
    qr.addData(personalLink());
    qr.make();
    var box = $('[data-my-qr]');
    box.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 1, scalable: true, alt: 'QR-код участника' }) +
      '<p><b>QR-код участника</b>Покажите на стойке регистрации — так быстрее, чем искать фамилию в списке.</p>';
    box.hidden = false;

    var changed = list.filter(function (r) { return r.item.changedFrom; });
    $('[data-my-changes]').innerHTML = changed.length
      ? '<section class="changes" aria-live="polite"><h2>' + icon('alert') + 'После вашей регистрации ' + plural(changed.length, ['изменилось', 'изменились', 'изменились']) + ' ' + changed.length + ' ' + plural(changed.length, ['событие', 'события', 'событий']) + '</h2>' +
        changed.map(function (r) {
          return '<p>«' + esc(r.item.title) + '»: было ' + r.item.changedFrom + ', стало <b>' + S.range(r.item) + '</b>' + (r.item.changeNote ? '. ' + esc(r.item.changeNote) : '') + '. Письмо об изменении отправлено.</p>';
        }).join('') + '</section>'
      : '';

    if (!list.length) {
      $('[data-my-list]').innerHTML = '<div class="empty-state my-empty"><h3>В вашей программе пока нет событий</h3>' +
        '<p>Отметьте интересные сессии и экскурсии в программе — они появятся здесь.</p><a class="btn btn-primary" href="program.html">Открыть программу</a></div>';
      return;
    }
    var html = '', curDay = null;
    list.forEach(function (r) {
      if (r.day !== curDay) {
        if (curDay) html += '</div></section>';
        curDay = r.day;
        html += '<section class="my-day"><h2>' + esc(S.dateLabel(r.day)) + (r.day.main ? ' — главный день' : '') + '</h2><div class="my-list">';
      }
      html += cardHtml(r);
    });
    html += '</div></section>';
    $('[data-my-list]').innerHTML = html;
  }

  function cancel(id) {
    var it = S.index[id].item;
    API.updateEvents(token, ids().filter(function (x) { return x !== id; })).then(function (res) {
      if (!res || !res.ok) { window.toast('Не удалось отменить участие, попробуйте ещё раз', 'warn'); return; }
      reg = res.registration;
      render();
      window.toast('Участие отменено: «' + it.title + '»' + (it.excursion ? '. Место перейдёт следующему в листе ожидания' : ''));
    });
  }

  function printMine() {
    var notes = {};
    ids().forEach(function (id) { if (reg.events[id].status === 'waitlist') notes[id] = 'лист ожидания'; });
    S.buildPrint($('[data-print-area]'), ids(), { title: 'Моя программа', subtitle: reg.person.name + ' · заявка ' + reg.id, notes: notes });
    window.print();
  }

  document.addEventListener('DOMContentLoaded', function () {
    window.hydrateIcons();
    var p = new URLSearchParams(location.search);
    token = p.get('t') || (window.store.get(window.forumKey('sf-reg'), {}) || {}).token;
    if (!token) return renderEmpty(false);
    API.get(token).then(function (res) {
      if (!res || !res.ok) return renderEmpty(true);
      reg = res.registration;
      render();
      if (p.get('print')) setTimeout(printMine, 500);
    }).catch(function () { renderEmpty(true); });

    document.addEventListener('click', function (e) {
      var t = e.target.closest('[data-cancel], [data-my-print], [data-my-ics]');
      if (!t) return;
      if (t.hasAttribute('data-cancel')) cancel(t.getAttribute('data-cancel'));
      if (t.hasAttribute('data-my-print')) printMine();
      if (t.hasAttribute('data-my-ics')) S.downloadIcs(ids());
    });
  });
})();
