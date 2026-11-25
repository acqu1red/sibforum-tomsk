/* Программа форума: дни, фильтры, сетка «время × трек» / список, «Моя программа», карточка события, .ics, печать. */
(function () {
  'use strict';
  var SF = window.SF, PR = window.PROGRAM, S = window.Schedule, esc = window.escapeHtml, icon = window.icon, plural = window.plural;
  var people = PR.people, venues = PR.venues, formats = PR.formats, days = PR.days;
  var mqGrid = window.matchMedia('(min-width: 1100px)');

  var state = {
    day: 5,
    tracks: [],
    venue: '',
    format: '',
    view: 'grid',
    mine: window.store.get(window.forumKey('sf-mine'), PR.defaultMine).slice()
  };

  var index = S.index, mins = S.mins, range = S.range, dateLabel = S.dateLabel, placeText = S.placeText;
  var seats = {}; // свободные места на экскурсиях — с сервера (или из демо-хранилища)

  function seatsLeft(it) {
    var s = seats[it.id];
    return s ? s.left : Math.max(0, it.excursion.limit - it.excursion.taken);
  }
  function seatBadge(it) {
    if (!it.excursion) return '';
    var left = seatsLeft(it);
    return left > 0
      ? '<span class="badge badge-seats">Осталось ' + left + ' ' + plural(left, ['место', 'места', 'мест']) + '</span>'
      : '<span class="badge badge-changed">Мест нет · лист ожидания</span>';
  }

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function track(id) { return SF.tracks[id - 1]; }
  function dayById(id) { return days.filter(function (d) { return d.id === id; })[0]; }
  function isMine(id) { return state.mine.indexOf(id) !== -1; }
  function initials(name) { return name.split(' ').map(function (w) { return w[0]; }).slice(0, 2).join(''); }
  var hyph = window.hyph;
  function speakersOf(it) { return (it.speakers || []).map(function (k) { return people[k]; }); }
  function moderatorsOf(it) { return (it.moderators || []).map(function (k) { return people[k]; }); }

  // ---------- Фильтрация ----------
  function passes(it) {
    if (state.venue && it.venue !== state.venue) return false;
    if (state.format && it.format !== state.format) return false;
    // пленарное — общее для всех треков
    if (state.tracks.length && it.type !== 'plenary' && state.tracks.indexOf(it.track) === -1) return false;
    return true;
  }
  function filterCount() { return state.tracks.length + (state.venue ? 1 : 0) + (state.format ? 1 : 0); }

  // ---------- Фрагменты разметки ----------
  function tagHtml(it) {
    if (it.type === 'plenary') return '<span class="tag" style="--c: var(--esg-strong)"><span class="dot"></span>Пленарное заседание</span>';
    var t = track(it.track);
    return '<span class="tag" style="--c: var(--t' + t.id + ')"><span class="dot"></span>Т' + t.id + ' · ' + esc(t.short) + '</span>';
  }

  function avatarsHtml(it) {
    var list = moderatorsOf(it).concat(speakersOf(it));
    if (!list.length) return '<span></span>';
    var shown = list.slice(0, 4).map(function (p) {
      return p.photo ? '<img src="' + window.asset(p.photo) + '" alt="" title="' + esc(p.name) + '" loading="lazy">' : '<span class="ph" title="' + esc(p.name) + '">' + initials(p.name) + '</span>';
    }).join('');
    var more = list.length > 4 ? '<span class="more">+' + (list.length - 4) + '</span>' : '';
    return '<span class="avatars" aria-label="Спикеров: ' + list.length + '">' + shown + more + '</span>';
  }

  function addBtn(it) {
    if (it.closed) return '<span class="s-closed">' + icon('lock') + 'По приглашениям</span>';
    var on = isMine(it.id);
    return '<button class="s-add" type="button" data-add="' + it.id + '" aria-pressed="' + on + '">' +
      icon(on ? 'check' : 'plus') + '<span>' + (on ? 'В программе' : 'В <span class="opt">мою </span>программу') + '</span></button>';
  }

  function cardHtml(it) {
    var cls = 's-card' + (isMine(it.id) ? ' is-mine' : '') + (it.live ? ' is-live' : '') +
      (it.changedFrom ? ' is-changed' : '') + (it.closed ? ' is-closed' : '');
    var badges = (it.live ? '<span class="badge badge-live"><span class="dot"></span>Идёт сейчас</span>' : '') +
      (it.changedFrom ? '<span class="badge badge-changed">Время изменено</span>' : '') +
      (it.closed ? '<span class="badge badge-closed">Закрытое</span>' : '') + seatBadge(it);
    var time = it.changedFrom ? '<s>' + it.changedFrom + '</s>' + range(it) : range(it);
    var mods = moderatorsOf(it).map(function (p) { return p.name; });
    return '<article class="' + cls + '" style="--c: var(--t' + it.track + ')" data-id="' + it.id + '">' +
      '<div class="s-top"><span class="s-time">' + time + '</span>' + badges + '</div>' +
      tagHtml(it) +
      '<h3 class="s-title"><a class="s-open" href="?s=' + it.id + '" data-open="' + it.id + '">' + hyph(esc(it.title)) + '</a></h3>' +
      '<p class="s-meta">' + icon('pin') + '<span><span class="fmt">' + esc(formats[it.format]) + ' · </span>' +
        (it.hall ? '<span class="fmt">' + esc(venues[it.venue].name) + ' · </span>' + esc(it.hall) : esc(venues[it.venue].name)) + '</span></p>' +
      (mods.length ? '<p class="s-mod"><b>' + (mods.length > 1 ? 'Модераторы' : 'Модератор') + ':</b> ' + esc(mods.join(', ')) + '</p>' : '') +
      '<div class="s-foot">' + avatarsHtml(it) + addBtn(it) + '</div></article>';
  }

  function plenaryHtml(it) {
    var list = moderatorsOf(it).map(function (p) { return { p: p, role: 'Модератор' }; })
      .concat(speakersOf(it).map(function (p) { return { p: p, role: p.role }; }));
    var chips = list.slice(0, 8).map(function (x) {
      return '<span class="person-chip"><img src="' + window.asset(x.p.photo) + '" alt="" loading="lazy"><span><b>' + esc(x.p.name) + '</b><span>' + esc(x.role) + '</span></span></span>';
    }).join('');
    return '<article class="plenary' + (isMine(it.id) ? ' is-mine' : '') + '" data-id="' + it.id + '">' +
      '<div class="s-top"><span class="s-time">' + range(it) + '</span><span class="badge badge-main">Пленарное заседание</span></div>' +
      '<h3><a href="?s=' + it.id + '" data-open="' + it.id + '">' + esc(it.title) + '</a></h3>' +
      '<p class="lead">' + esc(it.lead) + '</p>' +
      '<p class="s-meta">' + icon('pin') + '<span>' + esc(placeText(it)) + ' · ' + esc(venues[it.venue].address) + '</span></p>' +
      '<div class="plenary-people">' + chips + '</div>' +
      '<div class="plenary-actions">' + addBtn(it) +
      '<a class="btn btn-ghost-light" href="' + SF.forum.stream + '" target="_blank" rel="noopener">' + icon('play') + 'Трансляция</a></div></article>';
  }

  function svcHtml(s) {
    return '<div class="svc">' + icon(s.icon || 'coffee') + '<b>' + s.start + '–' + s.end + '</b><span>' + esc(s.title) + '</span></div>';
  }

  function spanOf(items) {
    var start = items.map(function (i) { return i.start; }).sort()[0];
    var end = items.map(function (i) { return i.end; }).sort().slice(-1)[0];
    return { start: start, end: end };
  }

  // ---------- Вид «сетка» (десктоп, дни со слотами) ----------
  function renderGrid(day, visible) {
    var cols = [];
    visible.forEach(function (it) { if (it.track && cols.indexOf(it.track) === -1) cols.push(it.track); });
    cols.sort(function (a, b) { return a - b; });
    var html = '<div class="pgrid-scroll"><div class="pgrid" style="--cols:' + Math.max(cols.length, 1) + '">' +
      '<div class="g-corner">Время</div>' +
      cols.map(function (id) { return '<div class="g-head" style="--c: var(--t' + id + ')"><b>Трек ' + id + '</b>' + esc(track(id).short) + '</div>'; }).join('');
    if (!cols.length) html += '<div></div>';
    day.slots.forEach(function (s) {
      if (s.type === 'service') { html += '<div class="g-row-full">' + svcHtml(s) + '</div>'; return; }
      var items = visible.filter(function (it) { return it.slot === s.key; });
      if (!items.length) return;
      if (s.type === 'plenary') {
        html += '<div class="g-time"><b>' + s.start + '</b><span>до ' + s.end + '</span></div><div class="g-plenary">' + plenaryHtml(items[0]) + '</div>';
        return;
      }
      var sp = spanOf(items);
      html += '<div class="g-time"><b>' + sp.start + '</b><span>до ' + sp.end + '<br>' + items.length + ' ' + plural(items.length, ['сессия', 'сессии', 'сессий']) + '</span></div>';
      cols.forEach(function (id) {
        var it = items.filter(function (x) { return x.track === id; })[0];
        html += it ? cardHtml(it) : '<div class="g-empty" aria-hidden="true"></div>';
      });
    });
    return html + '</div></div>';
  }

  // ---------- Вид «список» (телефон и дни без слотов) ----------
  function renderList(day, visible) {
    var groups;
    if (day.slots) {
      groups = day.slots.map(function (s) { return { slot: s, items: visible.filter(function (it) { return it.slot === s.key; }) }; });
    } else {
      var keys = [];
      visible.forEach(function (it) { if (keys.indexOf(it.slot) === -1) keys.push(it.slot); });
      groups = keys.map(function (k) { return { slot: { key: k, type: 'block' }, items: visible.filter(function (it) { return it.slot === k; }) }; });
    }
    return groups.map(function (g) {
      if (g.slot.type === 'service') return '<div class="slot">' + svcHtml(g.slot) + '</div>';
      if (!g.items.length) return '';
      var sp = spanOf(g.items), n = g.items.length;
      if (g.slot.type === 'plenary') {
        return '<section class="slot"><div class="slot-head"><b>' + sp.start + '–' + sp.end + '</b><span>Общая программа</span></div>' + plenaryHtml(g.items[0]) + '</section>';
      }
      var label = n > 1 ? n + ' ' + plural(n, ['параллельная сессия', 'параллельные сессии', 'параллельных сессий']) : '1 событие';
      return '<section class="slot"><div class="slot-head"><b>' + sp.start + '–' + sp.end + '</b><span>' + label + '</span></div>' +
        '<div class="slot-cards">' + g.items.map(cardHtml).join('') + '</div></section>';
    }).join('');
  }

  function emptyHtml() {
    var other = [];
    if (state.tracks.length) {
      days.forEach(function (d) {
        if (d.id !== state.day && d.items.some(function (it) { return state.tracks.indexOf(it.track) !== -1; })) other.push(d);
      });
    }
    return '<div class="empty-state"><h3>В этот день нет событий по выбранным фильтрам</h3>' +
      (other.length ? '<p>Выбранные треки идут в другие дни:</p>' + other.map(function (d) {
        return '<button class="btn btn-secondary" type="button" data-goto-day="' + d.id + '" style="margin:12px 6px 0">' + esc(d.tab) + '</button>';
      }).join('') : '') +
      '<div><button class="btn btn-primary" type="button" data-filters-reset>Сбросить фильтры</button></div></div>';
  }

  // ---------- Шапка дня ----------
  function renderIntro(day, visibleCount) {
    var venuesUsed = [];
    day.items.forEach(function (it) { if (venuesUsed.indexOf(it.venue) === -1) venuesUsed.push(it.venue); });
    var place = day.main ? 'ОЭЗ «Томск», пр. Развития, 3' : venuesUsed.map(function (v) { return venues[v].name; }).join(' · ');
    var legend = day.main
      ? '<div class="legend"><span class="badge badge-live"><span class="dot"></span>Идёт сейчас</span><span class="badge badge-changed">Время изменено</span><span class="badge badge-closed">Закрытое</span></div>'
      : '';
    $('[data-day-intro]').innerHTML = '<h2>' + esc(dateLabel(day)) + (day.main ? ' — главный день' : ' — ' + esc(day.label)) + '</h2>' +
      '<p>' + icon('pin') + esc(place) + '</p>' + legend;
    var rc = $('[data-results-count]');
    rc.textContent = visibleCount + ' ' + plural(visibleCount, ['событие', 'события', 'событий']);
  }

  // ---------- Главная отрисовка ----------
  function render() {
    var day = dayById(state.day);
    var visible = day.items.filter(passes);
    var useGrid = mqGrid.matches && day.slots && state.view === 'grid';
    renderIntro(day, visible.length);
    $('[data-program]').innerHTML = visible.length ? (useGrid ? renderGrid(day, visible) : renderList(day, visible)) : emptyHtml();

    $$('[data-day-tabs] .day-tab').forEach(function (b) { b.setAttribute('aria-selected', String(+b.getAttribute('data-day') === state.day)); });
    $$('[data-view]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-view') === (useGrid ? 'grid' : 'list')));
      if (b.getAttribute('data-view') === 'grid') b.disabled = !day.slots;
    });
    var dayTracks = day.items.map(function (it) { return it.track; });
    $$('[data-track-chips] .chip').forEach(function (c) {
      var id = +c.getAttribute('data-track');
      c.setAttribute('aria-pressed', String(state.tracks.indexOf(id) !== -1));
      c.classList.toggle('is-absent', dayTracks.indexOf(id) === -1);
    });
    $('[data-filter-venue]').value = state.venue;
    $('[data-filter-format]').value = state.format;
    var n = filterCount(), fc = $('[data-filter-count]');
    fc.hidden = !n;
    fc.textContent = n;
    $('[data-apply-label]').textContent = 'Показать ' + visible.length + ' ' + plural(visible.length, ['событие', 'события', 'событий']);
    syncUrl();
  }

  function syncUrl() {
    var url = new URL(location.href);
    url.searchParams.set('day', state.day);
    if (state.tracks.length) url.searchParams.set('track', state.tracks.join(',')); else url.searchParams.delete('track');
    url.searchParams.delete('print');
    history.replaceState(null, '', url);
  }

  // ---------- «Моя программа» ----------
  function conflictsOf(id) { return S.conflicts(id, state.mine); }

  function saveMine() { window.store.set(window.forumKey('sf-mine'), state.mine); }

  function toggleMine(id) {
    var it = index[id].item;
    if (isMine(id)) {
      state.mine.splice(state.mine.indexOf(id), 1);
      window.toast('Удалено из моей программы');
    } else {
      var c = conflictsOf(id);
      state.mine.push(id);
      if (c.length) window.toast('Добавлено. Пересекается по времени: «' + c[0].title + '», ' + range(c[0]), 'warn');
      else window.toast('Добавлено в мою программу');
    }
    saveMine();
    $$('[data-id="' + id + '"]').forEach(function (el) {
      el.classList.toggle('is-mine', isMine(id));
      var b = el.querySelector('[data-add]');
      if (b) b.outerHTML = addBtn(it);
    });
    var dlg = $('[data-session-dialog]');
    if (dlg.open && dlg.getAttribute('data-current') === id) openSession(id);
    if ($('[data-mine-dialog]').open) renderMine();
    updateMineUi();
  }

  function updateMineUi() {
    var n = state.mine.length;
    $$('[data-mine-count]').forEach(function (el) { el.textContent = n; });
    $('[data-mine-bar-text]').textContent = n ? 'Моя программа · ' + n + ' ' + plural(n, ['событие', 'события', 'событий']) : 'Моя программа пока пуста';
  }

  function mineSorted() { return S.sorted(state.mine); }

  function renderMine() {
    var dlg = $('[data-mine-dialog]'), list = mineSorted(), body = '';
    if (!list.length) {
      body = '<div class="empty-state"><h3>Пока пусто</h3><p>Отмечайте события кнопкой «В мою программу» — они соберутся здесь.</p></div>';
    } else {
      var curDay = null;
      list.forEach(function (r) {
        if (r.day !== curDay) {
          if (curDay) body += '</div>';
          curDay = r.day;
          body += '<div class="mine-day"><h3>' + esc(dateLabel(r.day)) + '</h3>';
        }
        var it = r.item, c = conflictsOf(it.id);
        body += '<div class="mine-item" style="--c: var(' + (it.type === 'plenary' ? '--esg-strong' : '--t' + it.track) + ')">' +
          '<b>' + (it.changedFrom ? '<s>' + it.changedFrom + '</s> ' : '') + range(it) + '</b>' +
          '<p>' + esc(it.title) + '</p><small>' + esc(placeText(it)) + (c.length ? ' · ⚠ пересекается по времени' : '') + '</small>' +
          '<button class="icon-btn" type="button" data-add="' + it.id + '" aria-label="Убрать из программы">' + icon('trash') + '</button></div>';
      });
      body += '</div>';
    }
    dlg.innerHTML = '<div class="dialog-head"><h2 id="mine-title" style="font:700 20px/1.2 var(--font)">Моя программа · ' + list.length + '</h2>' +
      '<button class="icon-btn" type="button" data-close-dialog aria-label="Закрыть">' + icon('x') + '</button></div>' +
      '<div class="dialog-body"><p class="mine-note">' + icon('mail') + '<span>Если время или зал изменятся, придёт письмо на почту, указанную при регистрации. Личная ссылка на эту страницу — в письме.</span></p><div style="margin-top:16px">' + body + '</div></div>' +
      '<div class="dialog-foot">' + (function () {
        var reg = window.store.get(window.forumKey('sf-reg'), null);
        return reg && reg.token
          ? '<a class="btn btn-primary" href="my.html?t=' + encodeURIComponent(reg.token) + '">' + icon('bookmark') + 'Моя личная страница</a>'
          : '<a class="btn btn-primary" href="register.html"' + (list.length ? '' : ' aria-disabled="true"') + '>' + icon('check') + 'Зарегистрироваться на выбранные</a>';
      })() +
      '<button class="btn btn-secondary" type="button" data-print="mine"' + (list.length ? '' : ' disabled') + '>' + icon('download') + 'Скачать PDF</button>' +
      '<button class="btn btn-secondary" type="button" data-ics="mine"' + (list.length ? '' : ' disabled') + '>' + icon('calendar') + 'В календарь (.ics)</button></div>';
  }

  // ---------- Карточка события (диалог) ----------
  function personHtml(p, role) {
    var ph = p.photo ? '<img src="' + window.asset(p.photo) + '" alt="" loading="lazy">' : '<span class="ph">' + initials(p.name) + '</span>';
    return '<li class="person">' + ph + '<div><b>' + esc(p.name) + '</b><span>' + esc(role || p.role) + '</span></div></li>';
  }

  function openSession(id) {
    var rec = index[id];
    if (!rec) return;
    var it = rec.item, d = rec.day, dlg = $('[data-session-dialog]');
    var v = venues[it.venue], conflicts = isMine(id) ? conflictsOf(id) : [];
    var notices = '';
    if (it.changedFrom) notices += '<div class="notice notice-changed">' + icon('alert') + '<span><b>Время изменено:</b> было ' + it.changedFrom + ', стало ' + range(it) + '.' + (it.changeNote ? ' ' + esc(it.changeNote) + '.' : '') + ' Записавшиеся получили письмо.</span></div>';
    if (it.live) notices += '<div class="notice notice-live">' + icon('play') + '<span><b>Идёт сейчас.</b> Трансляция — на VK Видео.</span></div>';
    if (it.closed) notices += '<div class="notice notice-closed">' + icon('lock') + '<span><b>Закрытое мероприятие:</b> участие по приглашениям организаторов.</span></div>';
    if (it.excursion) {
      var left = seatsLeft(it);
      notices += '<div class="notice ' + (left > 0 ? 'notice-closed' : 'notice-changed') + '">' + icon('users') + '<span><b>' +
        (left > 0 ? 'Осталось ' + left + ' из ' + it.excursion.limit + ' мест.' : 'Мест нет — можно встать в лист ожидания.') + '</b> ' +
        'Возраст: ' + esc(it.excursion.age) + '. Документы: ' + esc(it.excursion.docs) + '. За 3 дня попросим подтвердить участие.</span></div>';
    }
    if (conflicts.length) notices += '<div class="notice notice-conflict">' + icon('alert') + '<span>Пересекается с событием из вашей программы: «' + esc(conflicts[0].title) + '», ' + range(conflicts[0]) + '.</span></div>';
    var mods = moderatorsOf(it), sps = speakersOf(it);
    dlg.setAttribute('data-current', id);
    dlg.innerHTML = '<div class="dialog-head">' + tagHtml(it) + '<span class="badge badge-muted">' + esc(formats[it.format]) + '</span>' +
      '<button class="icon-btn" type="button" data-close-dialog aria-label="Закрыть">' + icon('x') + '</button></div>' +
      '<div class="dialog-body"><h2 id="session-title">' + esc(it.title) + '</h2>' +
      '<div class="dialog-facts">' +
      '<div>' + icon('calendar') + '<span>' + esc(dateLabel(d)) + ' 2026</span></div>' +
      '<div>' + icon('clock') + '<span>' + (it.changedFrom ? '<s>' + it.changedFrom + '</s> ' : '') + range(it) + ' (томское время)</span></div>' +
      '<div>' + icon('pin') + '<span>' + esc(placeText(it)) + '<br><span style="color:var(--ink-600)">' + esc(v.address) + '</span></span></div></div>' +
      notices +
      (it.lead ? '<p class="dialog-text"><b>' + esc(it.lead) + '</b></p>' : '') +
      (it.desc ? '<p class="dialog-text">' + esc(it.desc) + '</p>' : '') +
      (it.talks ? '<h3 class="dialog-sub">Доклады</h3><ol class="talks">' + it.talks.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ol>' : '') +
      (mods.length ? '<h3 class="dialog-sub">' + (mods.length > 1 ? 'Модераторы' : 'Модератор') + '</h3><ul class="people">' + mods.map(function (p) { return personHtml(p); }).join('') + '</ul>' : '') +
      (sps.length ? '<h3 class="dialog-sub">Спикеры</h3><ul class="people">' + sps.map(function (p) { return personHtml(p); }).join('') + '</ul>' : '') +
      (it.materials ? '<p class="notice notice-closed" style="margin-top:24px">' + icon('file') + '<span>После форума здесь появятся запись и презентации спикеров.</span></p>' : '') +
      '</div><div class="dialog-foot">' + addBtn(it) +
      '<button class="btn btn-secondary" type="button" data-ics="' + it.id + '">' + icon('calendar') + 'В календарь</button>' +
      (it.stream || it.live ? '<a class="btn btn-secondary" href="' + SF.forum.stream + '" target="_blank" rel="noopener">' + icon('play') + 'Трансляция</a>' : '') +
      '</div>';
    if (!dlg.open) dlg.showModal();
    var url = new URL(location.href);
    url.searchParams.set('s', id);
    history.replaceState(null, '', url);
  }

  // ---------- Календарь и печать — общие функции из schedule.js ----------
  function downloadIcs(ids) { S.downloadIcs(ids); }
  function printNow(mineOnly) {
    S.buildPrint($('[data-print-area]'), mineOnly ? state.mine.slice() : null, { title: mineOnly ? 'Моя программа' : 'Программа' });
    window.print();
  }

  // ---------- Шторка фильтров (телефон) ----------
  // Шторка живёт в прилипающей панели со своим z-index — на время открытия переносим её в body,
  // чтобы она была над затемнением и нижней плашкой.
  var filtersHome, filtersNext, sheetTimer;
  function setSheet(open) {
    var f = $('[data-filters]'), bd = $('[data-sheet-backdrop]'), opener = $('[data-filters-open]');
    if (!filtersHome) { filtersHome = f.parentNode; filtersNext = f.nextSibling; }
    if (mqGrid.matches) open = false;
    clearTimeout(sheetTimer);
    if (open) {
      document.body.appendChild(f);
      void f.offsetHeight; // чтобы сработала анимация выезда
      f.classList.add('is-open');
    } else {
      f.classList.remove('is-open');
      var restore = function () { if (f.parentNode !== filtersHome) filtersHome.insertBefore(f, filtersNext); };
      if (mqGrid.matches) restore(); else sheetTimer = setTimeout(restore, 260);
    }
    bd.hidden = !open;
    document.body.classList.toggle('sheet-open', open);
    opener.setAttribute('aria-expanded', String(open));
    document.body.style.overflow = open ? 'hidden' : '';
    if (open) { var c = f.querySelector('.chip'); if (c) c.focus(); }
  }

  // ---------- Инициализация ----------
  function initControls() {
    $('[data-day-tabs]').innerHTML = days.map(function (d) {
      return '<button class="day-tab' + (d.main ? ' is-main' : '') + '" type="button" role="tab" data-day="' + d.id + '" aria-selected="false">' +
        '<b>' + esc(d.tab) + '</b><span>' + esc(d.label) + '</span></button>';
    }).join('');
    $('[data-track-chips]').innerHTML = SF.tracks.map(function (t) {
      return '<button class="chip" type="button" data-track="' + t.id + '" aria-pressed="false" style="--c: var(--t' + t.id + ')" title="' + esc(t.name) + '">' +
        '<span class="dot"></span>Т' + t.id + ' · ' + esc(t.short) + '</button>';
    }).join('');
    var vSel = $('[data-filter-venue]'), fSel = $('[data-filter-format]');
    Object.keys(venues).forEach(function (k) { vSel.insertAdjacentHTML('beforeend', '<option value="' + k + '">' + esc(venues[k].name) + '</option>'); });
    Object.keys(formats).forEach(function (k) { fSel.insertAdjacentHTML('beforeend', '<option value="' + k + '">' + esc(formats[k]) + '</option>'); });
    vSel.addEventListener('change', function () { state.venue = vSel.value; render(); });
    fSel.addEventListener('change', function () { state.format = fSel.value; render(); });
    window.hydrateIcons();
  }

  function readUrl() {
    var p = new URLSearchParams(location.search);
    var tr = (p.get('track') || '').split(',').map(Number).filter(function (n) { return n >= 1 && n <= 8; });
    state.tracks = tr;
    var d = +p.get('day');
    if (d >= 1 && d <= 5) state.day = d;
    else if (tr.length) {
      // день с выбранным треком: главный день, если трек там есть, иначе первый подходящий
      var withTrack = days.filter(function (x) { return x.items.some(function (it) { return tr.indexOf(it.track) !== -1; }); });
      if (withTrack.length && !withTrack.some(function (x) { return x.main; })) state.day = withTrack[0].id;
    }
    return p;
  }

  function bind() {
    document.addEventListener('click', function (e) {
      var t = e.target.closest('button, a');
      if (!t) {
        if (e.target.matches('dialog')) e.target.close();
        return;
      }
      if (t.hasAttribute('data-day')) { state.day = +t.getAttribute('data-day'); render(); return; }
      if (t.hasAttribute('data-goto-day')) { state.day = +t.getAttribute('data-goto-day'); render(); return; }
      if (t.hasAttribute('data-track')) {
        var id = +t.getAttribute('data-track'), i = state.tracks.indexOf(id);
        if (i === -1) state.tracks.push(id); else state.tracks.splice(i, 1);
        render(); return;
      }
      if (t.hasAttribute('data-filters-reset')) { state.tracks = []; state.venue = ''; state.format = ''; render(); return; }
      if (t.hasAttribute('data-filters-open')) { setSheet(true); return; }
      if (t.hasAttribute('data-filters-close')) { setSheet(false); return; }
      if (t.hasAttribute('data-view')) { if (!t.disabled) { state.view = t.getAttribute('data-view'); render(); } return; }
      if (t.hasAttribute('data-add')) { e.preventDefault(); toggleMine(t.getAttribute('data-add')); return; }
      if (t.hasAttribute('data-open')) { e.preventDefault(); openSession(t.getAttribute('data-open')); return; }
      if (t.hasAttribute('data-mine-open')) { renderMine(); $('[data-mine-dialog]').showModal(); return; }
      if (t.hasAttribute('data-close-dialog')) { t.closest('dialog').close(); return; }
      if (t.hasAttribute('data-ics')) {
        var v = t.getAttribute('data-ics');
        downloadIcs(v === 'mine' ? mineSorted().map(function (r) { return r.item.id; }) : [v]);
        return;
      }
      if (t.hasAttribute('data-print')) { printNow(t.getAttribute('data-print') === 'mine'); return; }
    });
    $('[data-sheet-backdrop]').addEventListener('click', function () { setSheet(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && $('[data-filters]').classList.contains('is-open')) setSheet(false); });
    $('[data-session-dialog]').addEventListener('close', function () {
      var url = new URL(location.href);
      url.searchParams.delete('s');
      history.replaceState(null, '', url);
    });
    var onResize = function () {
      document.documentElement.style.setProperty('--toolbar-h', $('[data-toolbar]').offsetHeight + 'px');
    };
    window.addEventListener('resize', onResize);
    onResize();
    mqGrid.addEventListener('change', function () { setSheet(false); render(); });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var p = readUrl();
    initControls();
    bind();
    render();
    updateMineUi();
    window.API.seats().then(function (st) { if (st && !st.error) { seats = st; render(); } });
    if (p.get('s')) openSession(p.get('s'));
    if (p.get('print')) setTimeout(function () { printNow(false); }, 600);
  });
})();
