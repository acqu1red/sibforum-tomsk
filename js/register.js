/* Регистрация (ТЗ, п. 5.1): выбор событий → анкета → согласия → подтверждение e-mail → личная программа и QR-код. */
(function () {
  'use strict';
  var PR = window.PROGRAM, S = window.Schedule, API = window.API;
  var esc = window.escapeHtml, icon = window.icon, plural = window.plural;
  var DRAFT_KEY = 'sf-reg-draft';
  var FIELDS = ['name', 'email', 'phone', 'org', 'position', 'city', 'inn', 'source', 'comment', 'birth_date', 'citizenship'];
  var STEP_OF = { events: 1, pd: 3, policy: 3 }; // остальные ошибки — на шаге 2

  function pickable(id) { var r = S.index[id]; return !!r && !r.item.closed; }

  var state = {
    step: 1,
    selected: window.store.get(window.forumKey('sf-mine'), PR.defaultMine).filter(pickable),
    seats: {},
    payload: null,
    result: null,
    touched: {}
  };

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function isSel(id) { return state.selected.indexOf(id) !== -1; }
  function digits(v) { return String(v || '').replace(/\D/g, ''); }
  function hasExcursion() { return state.selected.some(function (id) { return !!S.index[id].item.excursion; }); }
  function seatsLeft(it) { var s = state.seats[it.id]; return s ? s.left : Math.max(0, it.excursion.limit - it.excursion.taken); }
  function form() { return $('[data-form]'); }

  // ---------- Шаг 1: выбор событий ----------
  function seatBadge(it) {
    var left = seatsLeft(it);
    return left > 0
      ? '<span class="badge badge-seats">Осталось ' + left + ' ' + plural(left, ['место', 'места', 'мест']) + '</span>'
      : '<span class="badge badge-changed">Мест нет · лист ожидания</span>';
  }

  function pickHtml(it) {
    var x = it.excursion, on = isSel(it.id);
    var cls = 'pick' + (x ? ' pick-x' : '') + (on ? ' is-checked' : '') + (it.closed ? ' is-disabled' : '');
    var badges = (it.changedFrom ? '<span class="badge badge-changed">Время изменено</span>' : '') +
      (it.closed ? '<span class="badge badge-closed">По приглашениям</span>' : '') + (x ? seatBadge(it) : '');
    return '<label class="' + cls + '" style="--c:' + S.trackColor(it) + '" data-pick="' + it.id + '">' +
      '<input type="checkbox" value="' + it.id + '"' + (on ? ' checked' : '') + (it.closed ? ' disabled' : '') + ' aria-describedby="w-' + it.id + '">' +
      (x ? '<img class="x-photo" src="' + window.asset(it.photo) + '" alt="" loading="lazy">' : '') +
      '<span class="pick-time">' + (it.changedFrom ? '<s>' + it.changedFrom + '</s>' : '') + S.range(it) + badges + '</span>' +
      '<span class="pick-title">' + window.hyph(esc(it.title)) + '</span>' +
      '<span class="pick-meta">' + esc(S.trackLabel(it)) + ' · ' + esc(S.placeText(it)) + '</span>' +
      (x ? '<span class="x-req">' + esc(x.age) + ' · ' + esc(x.docs) + '</span>' : '') +
      '<span class="pick-warn" id="w-' + it.id + '" hidden></span></label>';
  }

  function renderPick() {
    var openNow = {};
    $$('.pick-day').forEach(function (d) { openNow[d.getAttribute('data-day')] = d.open; });
    $('[data-pick-days]').innerHTML = PR.days.map(function (d) {
      var keys = [];
      d.items.forEach(function (it) { if (keys.indexOf(it.slot) === -1) keys.push(it.slot); });
      var groups = keys.map(function (k) {
        var items = d.items.filter(function (it) { return it.slot === k; });
        var start = items.map(function (i) { return i.start; }).sort()[0];
        var n = items.length;
        return '<div class="pick-slot"><div class="pick-slot-head">' + start +
          (n > 1 ? '<span>' + n + ' ' + plural(n, ['событие', 'события', 'событий']) + ' в это время</span>' : '') + '</div>' +
          '<div class="pick-list">' + items.map(pickHtml).join('') + '</div></div>';
      }).join('');
      var plenary = d.items.filter(function (it) { return it.type === 'plenary'; })[0];
      var open = d.id in openNow ? openNow[d.id] : (d.main || d.items.some(function (it) { return isSel(it.id); }));
      return '<details class="pick-day" data-day="' + d.id + '"' + (open ? ' open' : '') + '><summary>' +
        '<span>' + esc(S.dateLabel(d)) + '<span class="sub">' + esc(d.main ? 'Главный день' + (plenary ? ' · пленарное заседание в 13:00' : '') : d.label) + '</span></span>' +
        '<span class="badge badge-muted" data-day-count></span><span class="chev">' + icon('chevron-down') + '</span></summary>' +
        '<div class="pick-day-body">' + groups + '</div></details>';
    }).join('');
    refreshPick();
  }

  function refreshPick() {
    $$('[data-pick]').forEach(function (el) {
      var id = el.getAttribute('data-pick'), it = S.index[id].item, on = isSel(id), msg = '';
      el.classList.toggle('is-checked', on);
      if (on) {
        var c = S.conflicts(id, state.selected);
        if (c.length) msg = 'Пересекается по времени с «' + c[0].title + '», ' + S.range(c[0]) + (c.length > 1 ? ' и ещё ' + (c.length - 1) : '');
        if (it.excursion && seatsLeft(it) <= 0) msg = (msg ? msg + '. ' : '') + 'Мест нет — запишем вас в лист ожидания';
      }
      var w = el.querySelector('.pick-warn');
      w.hidden = !msg;
      w.innerHTML = msg ? icon('alert') + '<span>' + esc(msg) + '</span>' : '';
    });
    $$('.pick-day').forEach(function (d) {
      var day = PR.days[+d.getAttribute('data-day') - 1];
      var n = day.items.filter(function (it) { return isSel(it.id); }).length;
      var badge = d.querySelector('[data-day-count]');
      badge.textContent = 'Выбрано: ' + n;
      badge.hidden = !n;
    });
    var n = state.selected.length;
    $('[data-nav-count]').textContent = n ? 'Выбрано ' + n + ' ' + plural(n, ['событие', 'события', 'событий']) : 'Ничего не выбрано';
    renderAside();
    toggleExcursionFields();
  }

  function toggleEvent(id, on) {
    var i = state.selected.indexOf(id);
    if (on && i === -1) state.selected.push(id);
    if (!on && i !== -1) state.selected.splice(i, 1);
    window.store.set(window.forumKey('sf-mine'), state.selected);
    if (state.selected.length) setError('events', '');
    refreshPick();
  }

  // ---------- Боковая панель ----------
  function renderAside() {
    var list = S.sorted(state.selected), html = '', curDay = null;
    list.forEach(function (r) {
      if (r.day !== curDay) { curDay = r.day; html += '<li class="aside-day">' + esc(S.dateLabel(r.day)) + '</li>'; }
      var it = r.item, warn = '';
      if (S.conflicts(it.id, state.selected).length) warn = 'Пересекается по времени';
      if (it.excursion && seatsLeft(it) <= 0) warn = 'Лист ожидания';
      html += '<li class="aside-item" style="--c:' + S.trackColor(it) + '"><b>' + S.range(it) + '</b>' + esc(it.title) +
        (warn ? '<span class="warn">' + warn + '</span>' : '') + '</li>';
    });
    $('[data-aside-count]').textContent = list.length;
    $('[data-aside-list]').innerHTML = list.length ? '<ul class="aside-list">' + html + '</ul>' :
      '<p class="aside-empty">Пока ничего не выбрано. Отметьте события слева — или выберите их в <a href="program.html">программе</a>.</p>';
  }

  // ---------- Поля и проверка ----------
  function value(name) {
    var f = form().elements[name];
    if (!f) return '';
    if (f.length && f[0] && f[0].type === 'radio') {
      var c = Array.prototype.filter.call(f, function (r) { return r.checked; })[0];
      return c ? c.value : '';
    }
    if (f.type === 'checkbox') return f.checked;
    return f.value;
  }

  var RULES = {
    name: function (v) { return v.trim().split(/\s+/).filter(Boolean).length >= 2 ? '' : (v.trim() ? 'Укажите фамилию и имя полностью' : 'Укажите фамилию и имя'); },
    email: function (v) { v = v.trim(); return /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(v) ? '' : (v ? 'Проверьте адрес — например, ivanov@company.ru' : 'Укажите e-mail'); },
    phone: function (v) { var d = digits(v); return d.length === 11 ? '' : (d.length > 1 ? 'Номер неполный: нужно 10 цифр после +7' : 'Укажите телефон'); },
    org: function (v) { return v.trim() ? '' : 'Укажите организацию'; },
    position: function (v) { return v.trim() ? '' : 'Укажите должность'; },
    category: function (v) { return v ? '' : 'Выберите категорию'; },
    format: function (v) {
      if (!v) return 'Выберите формат участия';
      return v === 'online' && hasExcursion() ? 'Экскурсии доступны только при очном участии: выберите «Очно» или уберите экскурсии на шаге 1' : '';
    },
    inn: function (v) { return !v || /^(\d{10}|\d{12})$/.test(v) ? '' : 'ИНН — 10 цифр для организации или 12 для ИП'; },
    birth_date: function (v) { return !hasExcursion() || v ? '' : 'Для пропуска на предприятие нужна дата рождения'; },
    citizenship: function (v) { return !hasExcursion() || v ? '' : 'Укажите гражданство'; },
    pd: function (v) { return v ? '' : 'Без этого согласия мы не можем принять заявку'; },
    policy: function (v) { return v ? '' : 'Подтвердите, что ознакомились с политикой'; }
  };
  var LABELS = { name: 'ФИО', email: 'E-mail', phone: 'Телефон', org: 'Организация', position: 'Должность', category: 'Категория участника',
    format: 'Формат участия', inn: 'ИНН', birth_date: 'Дата рождения', citizenship: 'Гражданство' };

  function fieldEl(name) {
    return form().querySelector('fieldset[data-field="' + name + '"]') || form().querySelector('label.check[data-field="' + name + '"]') ||
      form().elements[name] || null;
  }

  function setError(name, msg) {
    var err = document.getElementById('err-' + name), el = fieldEl(name);
    if (err) { err.textContent = msg; err.hidden = !msg; }
    if (el && el.setAttribute) {
      if (msg) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid');
    }
  }

  function hasError(name) { var e = document.getElementById('err-' + name); return !!e && !e.hidden; }

  function check(name) {
    var msg = RULES[name] ? RULES[name](value(name)) : '';
    setError(name, msg);
    return msg;
  }

  function validateStep(step) {
    var errors = [];
    if (step === 1) {
      if (!state.selected.length) {
        setError('events', 'Отметьте хотя бы одно событие — так мы поймём, куда вас ждать');
        errors.push('events');
      }
    }
    if (step === 2) {
      ['name', 'email', 'phone', 'org', 'position', 'category', 'format', 'inn', 'birth_date', 'citizenship'].forEach(function (n) {
        if (check(n)) errors.push(n);
      });
      var box = $('[data-error-summary]');
      if (errors.length > 1) {
        box.innerHTML = '<b>Проверьте поля:</b><ul>' + errors.map(function (n) {
          return '<li><a href="#" data-jump="' + n + '">' + LABELS[n] + '</a></li>';
        }).join('') + '</ul>';
        box.hidden = false;
        box.focus();
      } else {
        box.hidden = true;
      }
    }
    if (step === 3) {
      ['pd', 'policy'].forEach(function (n) { if (check(n)) errors.push(n); });
    }
    if (errors.length && !(step === 2 && errors.length > 1)) focusField(errors[0]);
    return !errors.length;
  }

  function focusField(name) {
    if (name === 'events') { $('#err-events').scrollIntoView({ block: 'center' }); return; }
    var el = form().elements[name];
    var target = el && el.length && el[0] && el[0].type === 'radio' ? el[0] : el;
    if (target && target.focus) { target.focus(); if (target.scrollIntoView) target.scrollIntoView({ block: 'center' }); }
  }

  function toggleExcursionFields() {
    var box = $('[data-excursion-fields]');
    box.hidden = !hasExcursion();
    if (box.hidden) { setError('birth_date', ''); setError('citizenship', ''); }
  }

  // Маска телефона: +7 (999) 123-45-67
  function formatPhone(v) {
    var d = digits(v);
    if (!d) return '';
    if (d[0] === '8') d = '7' + d.slice(1);
    if (d[0] !== '7') d = '7' + d;
    d = d.slice(0, 11);
    var out = '+7';
    if (d.length > 1) out += ' (' + d.slice(1, 4);
    if (d.length >= 4) out += ')';
    if (d.length > 4) out += ' ' + d.slice(4, 7);
    if (d.length > 7) out += '-' + d.slice(7, 9);
    if (d.length > 9) out += '-' + d.slice(9, 11);
    return out;
  }

  // ---------- Черновик формы (только в этом браузере) ----------
  function saveDraft() {
    var draft = {};
    FIELDS.concat(['category', 'format']).forEach(function (n) { draft[n] = value(n); });
    window.store.set(DRAFT_KEY, draft);
  }
  function restoreDraft() {
    var d = window.store.get(DRAFT_KEY, null);
    if (!d) return;
    Object.keys(d).forEach(function (n) {
      var f = form().elements[n];
      if (!f || !d[n]) return;
      if (f.length && f[0] && f[0].type === 'radio') {
        Array.prototype.forEach.call(f, function (r) { r.checked = r.value === d[n]; });
      } else {
        f.value = d[n];
      }
    });
    syncChoiceCards();
  }
  function syncChoiceCards() {
    $$('.choice-card').forEach(function (c) { c.classList.toggle('is-checked', c.querySelector('input').checked); });
  }

  // ---------- Шаги ----------
  function showStep(step) {
    state.step = step;
    $$('.step').forEach(function (s) { s.hidden = s.getAttribute('data-step') !== String(step); });
    var num = typeof step === 'number' ? step : 4;
    $$('[data-step-ind]').forEach(function (li) {
      var i = +li.getAttribute('data-step-ind');
      li.setAttribute('data-state', i < num ? 'done' : i === num ? 'current' : 'todo');
      if (i === num) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    });
    if (step === 2) toggleExcursionFields();
    if (step === 3) renderSummary();
    var top = $('#reg').getBoundingClientRect().top + window.scrollY - 80;
    if (window.scrollY > top) window.scrollTo({ top: top, behavior: 'smooth' });
    var title = $('.step[data-step="' + step + '"] .step-title');
    if (title) { title.setAttribute('tabindex', '-1'); title.focus({ preventScroll: true }); }
  }

  function go(step) {
    if (step > state.step) {
      for (var s = state.step; s < step; s++) {
        if (!validateStep(s)) { if (s !== state.step) showStep(s); return; }
      }
    }
    showStep(step);
  }

  function person() {
    var p = {};
    FIELDS.concat(['category', 'format']).forEach(function (n) { p[n] = typeof value(n) === 'string' ? value(n).trim() : value(n); });
    if (!hasExcursion()) { p.birth_date = ''; p.citizenship = ''; }
    return p;
  }

  var CATEGORY = { business: 'Бизнес', plant: 'Промышленное предприятие', university: 'Вуз', school: 'Школа, колледж', government: 'Орган власти', media: 'СМИ', other: 'Другое' };

  function renderSummary() {
    var p = person();
    var events = S.sorted(state.selected).map(function (r) {
      var it = r.item, wait = it.excursion && seatsLeft(it) <= 0;
      return '<li><b>' + esc(r.day.tab.split(', ')[1]) + ', ' + S.range(it) + '</b>' + esc(it.title) + (wait ? ' <span class="status status-wait">лист ожидания</span>' : '') + '</li>';
    }).join('');
    $('[data-summary]').innerHTML =
      '<div class="summary-block"><header><h3>Участник</h3><button class="link-btn" type="button" data-go="2">Изменить</button></header><dl>' +
      '<dt>ФИО</dt><dd>' + esc(p.name) + '</dd><dt>E-mail</dt><dd>' + esc(p.email) + '</dd><dt>Телефон</dt><dd>' + esc(p.phone) + '</dd>' +
      '<dt>Организация</dt><dd>' + esc(p.org) + ', ' + esc(p.position) + '</dd><dt>Категория</dt><dd>' + esc(CATEGORY[p.category] || '') + '</dd>' +
      '<dt>Формат</dt><dd>' + (p.format === 'online' ? 'Онлайн' : 'Очно') + '</dd></dl></div>' +
      '<div class="summary-block"><header><h3>События · ' + state.selected.length + '</h3><button class="link-btn" type="button" data-go="1">Изменить</button></header><ul>' + events + '</ul></div>';
  }

  // ---------- Отправка ----------
  function busy(btn, on) {
    btn.disabled = on;
    btn.setAttribute('aria-busy', String(on));
  }

  function submit() {
    if (!validateStep(3)) return;
    var btn = $('[data-submit]'), errBox = $('[data-form-error]');
    errBox.hidden = true;
    state.payload = {
      forum: window.SF.forum.id,
      events: state.selected.slice(),
      person: person(),
      consents: { pd: value('pd'), policy: value('policy'), media: value('media'), news: value('news') }
    };
    busy(btn, true);
    btn.firstChild.textContent = 'Отправляем… ';
    API.register(state.payload).then(function (res) {
      busy(btn, false);
      btn.firstChild.textContent = 'Отправить заявку ';
      if (res && res.ok) {
        state.result = res;
        window.store.set(window.forumKey('sf-reg'), { token: res.token, id: res.id, email: res.email_masked });
        if (res.confirmed) return finish(res);
        return showCode(res);
      }
      if (res && res.errors) {
        var first = null;
        Object.keys(res.errors).forEach(function (n) { setError(n, res.errors[n]); if (!first) first = n; });
        showStep(STEP_OF[first] || 2);
        focusField(first);
        return;
      }
      throw new Error('bad response');
    }).catch(function () {
      busy(btn, false);
      btn.firstChild.textContent = 'Отправить заявку ';
      errBox.textContent = 'Не удалось отправить заявку. Проверьте интернет и попробуйте ещё раз — введённые данные сохранены.';
      errBox.hidden = false;
    });
  }

  // ---------- Подтверждение e-mail ----------
  var resendTimer;
  function showCode(res) {
    $$('[data-email-masked]').forEach(function (el) { el.textContent = res.email_masked; });
    var demo = $('[data-demo-code]');
    demo.hidden = !res.demo_code;
    if (res.demo_code) demo.querySelector('b').textContent = res.demo_code;
    $('#f-code').value = '';
    setError('code', '');
    showStep('code');
    $('#f-code').focus();
    startResendTimer();
  }

  function startResendTimer() {
    var btn = $('[data-resend]'), left = 60;
    clearInterval(resendTimer);
    btn.disabled = true;
    btn.textContent = 'Отправить код ещё раз через ' + left + ' с';
    resendTimer = setInterval(function () {
      left--;
      if (left <= 0) { clearInterval(resendTimer); btn.disabled = false; btn.textContent = 'Отправить код ещё раз'; return; }
      btn.textContent = 'Отправить код ещё раз через ' + left + ' с';
    }, 1000);
  }

  function confirmCode() {
    var code = digits($('#f-code').value);
    if (code.length !== 4) {
      setError('code', 'Введите 4 цифры из письма');
      $('#f-code').setAttribute('aria-invalid', 'true');
      return;
    }
    var btn = $('[data-confirm]');
    busy(btn, true);
    API.confirm(state.result.token, code, state.result.id).then(function (res) {
      busy(btn, false);
      if (res && res.ok) return finish(state.result, res.registration);
      setError('code', res && res.error === 'wrong_code' ? 'Неверный код. Проверьте письмо или запросите код ещё раз' : 'Не удалось проверить код, попробуйте ещё раз');
      $('#f-code').setAttribute('aria-invalid', 'true');
      $('#f-code').select(); // новый код можно вводить сразу, не стирая старый
    }).catch(function () {
      busy(btn, false);
      setError('code', 'Нет связи с сервером, попробуйте ещё раз');
    });
  }

  // ---------- Готово ----------
  function finish(res, registration) {
    clearInterval(resendTimer);
    var events = (registration && registration.events) || res.events || {};
    var ids = Object.keys(events);
    var link = new URL('my.html?t=' + encodeURIComponent(res.token), location.href).href;
    window.store.set(window.forumKey('sf-mine'), ids);
    window.store.set(DRAFT_KEY, null);

    $('[data-done-lead]').innerHTML = (res.updated
      ? 'Вы уже были зарегистрированы — мы обновили выбор событий. '
      : '') + 'Письмо с подтверждением и личной программой отправлено на <b>' + esc(res.email_masked) + '</b>.';
    $('[data-reg-id]').textContent = res.id || (registration && registration.id) || '—';
    $('[data-personal-link]').value = link;
    $('[data-my-link]').href = 'my.html?t=' + encodeURIComponent(res.token);
    $('[data-pdf-link]').href = 'my.html?t=' + encodeURIComponent(res.token) + '&print=1';
    $('[data-excursion-note]').hidden = !ids.some(function (id) { return S.index[id] && S.index[id].item.excursion; });

    var qr = window.qrcode(0, 'M');
    qr.addData(link);
    qr.make();
    $('[data-qr]').innerHTML = qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true, alt: 'QR-код участника' });

    var rows = S.sorted(ids).map(function (r) {
      var st = events[r.item.id] || {};
      var status = st.status === 'waitlist'
        ? '<span class="status status-wait">Лист ожидания' + (st.queue ? ' · ' + st.queue + '-й в очереди' : '') + '</span>'
        : '<span class="status status-ok">' + icon('check') + 'Записаны</span>';
      return '<li><b>' + esc(r.day.tab) + ', ' + S.range(r.item) + '</b> ' + esc(r.item.title) + ' ' + status + '</li>';
    }).join('');
    $('[data-done-events]').innerHTML = '<div class="summary-block"><header><h3>Ваши события · ' + ids.length + '</h3>' +
      '<a class="link-btn" href="program.html">Добавить ещё</a></header><ul>' + rows + '</ul></div>';
    state.doneIds = ids;
    showStep('done');
    renderAsideDone(ids);
  }

  function renderAsideDone(ids) {
    state.selected = ids.slice();
    renderAside();
  }

  // ---------- Инициализация ----------
  function bind() {
    $('[data-pick-days]').addEventListener('change', function (e) {
      if (e.target.matches('input[type="checkbox"]')) toggleEvent(e.target.value, e.target.checked);
    });
    document.addEventListener('click', function (e) {
      var t = e.target.closest('[data-go], [data-jump], [data-close-dialog], [data-copy], [data-ics-all], [data-confirm], [data-resend]');
      if (!t) {
        if (e.target.matches('dialog')) e.target.close();
        return;
      }
      if (t.hasAttribute('data-go')) { go(+t.getAttribute('data-go')); return; }
      if (t.hasAttribute('data-jump')) { e.preventDefault(); focusField(t.getAttribute('data-jump')); return; }
      if (t.hasAttribute('data-close-dialog')) { t.closest('dialog').close(); return; }
      if (t.hasAttribute('data-confirm')) { confirmCode(); return; }
      if (t.hasAttribute('data-resend')) {
        API.register(state.payload).then(function (res) {
          if (res && res.ok) { state.result = res; showCode(res); window.toast('Новый код отправлен на ' + res.email_masked); }
        });
        return;
      }
      if (t.hasAttribute('data-copy')) {
        var inp = $('[data-personal-link]');
        var done = function () { window.toast('Ссылка скопирована'); };
        if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(inp.value).then(done);
        else { inp.select(); document.execCommand('copy'); done(); }
        return;
      }
      if (t.hasAttribute('data-ics-all')) { S.downloadIcs(state.doneIds || state.selected); }
    });

    var f = form();
    f.addEventListener('submit', function (e) { e.preventDefault(); submit(); });
    f.addEventListener('input', function (e) {
      var n = e.target.name;
      if (n === 'phone') {
        var pos = e.target.value.length === e.target.selectionStart;
        e.target.value = formatPhone(e.target.value);
        if (pos) e.target.selectionStart = e.target.selectionEnd = e.target.value.length;
      }
      if (n === 'inn') e.target.value = digits(e.target.value).slice(0, 12);
      // ошибка исчезает прямо при вводе — иначе она пропадёт на blur, вёрстка сдвинется
      // в момент клика по следующему полю, и клик промахнётся
      if ((state.touched[n] || hasError(n)) && RULES[n]) check(n);
      saveDraft();
    });
    f.addEventListener('change', function (e) {
      var n = e.target.name;
      if (e.target.type === 'radio') { syncChoiceCards(); check(n); if (n === 'format') check('format'); }
      if (e.target.type === 'checkbox' && RULES[n]) check(n);
      saveDraft();
    });
    f.addEventListener('focusout', function (e) {
      var n = e.target.name;
      if (!n || !RULES[n] || e.target.type === 'radio' || e.target.type === 'checkbox') return;
      // новая ошибка показывается с задержкой: клик по следующему полю успевает завершиться до сдвига вёрстки
      if (e.target.value) { state.touched[n] = true; setTimeout(function () { check(n); }, 200); }
    });
    $('#f-code').addEventListener('input', function (e) {
      e.target.value = digits(e.target.value).slice(0, 4);
      e.target.removeAttribute('aria-invalid');
      setError('code', '');
      if (e.target.value.length === 4) confirmCode();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    renderPick();
    restoreDraft();
    bind();
    showStep(1);
    window.hydrateIcons();
    API.ready.then(function (mode) { $('[data-demo-note]').hidden = mode !== 'demo'; });
    API.seats().then(function (st) { if (st && !st.error) { state.seats = st; renderPick(); } });
    var reg = window.store.get(window.forumKey('sf-reg'), null);
    if (reg && reg.token) {
      var note = document.createElement('p');
      note.className = 'demo-note';
      note.style.background = 'var(--indigo-50)';
      note.style.color = 'var(--ink-700)';
      note.innerHTML = icon('bookmark') + '<span>Вы уже регистрировались в этом браузере. Изменить выбор событий можно на <a href="my.html?t=' + encodeURIComponent(reg.token) + '">личной странице</a> — или отправьте форму ещё раз с тем же e-mail: мы обновим заявку, а не создадим новую.</span>';
      $('[data-demo-note]').insertAdjacentElement('afterend', note);
    }
  });
})();
