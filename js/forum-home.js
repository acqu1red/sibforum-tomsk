/* Главная сайта форума (шаблон): спикеры, темы, программа кратко, экскурсии, логотипы, площадки, первый экран.
   Все данные — из data/forum.js и data/program.js этого форума. */
(function () {
  'use strict';
  var SF = window.SF, PR = window.PROGRAM, S = window.Schedule, esc = window.escapeHtml, icon = window.icon, plural = window.plural;

  function qs(sel) { return document.querySelector(sel); }

  // ---------- Спикеры: 8 видны, остальные — по кнопке ----------
  function renderSpeakers() {
    var list = qs('[data-speakers]');
    if (!list) return;
    list.innerHTML = SF.featured.map(function (p, i) {
      return '<li class="speaker"' + (i >= 8 ? ' hidden data-extra' : '') + '>' +
        '<img class="speaker-photo" src="' + window.asset('img/speakers/' + p.photo + '.jpg') + '" alt="" width="156" height="156" loading="lazy">' +
        '<h3 class="speaker-name">' + esc(p.name) + '</h3>' +
        '<p class="speaker-role">' + esc(p.role) + '</p></li>';
    }).join('');
    var btn = qs('[data-speakers-toggle]');
    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') !== 'true';
      list.querySelectorAll('[data-extra]').forEach(function (li) { li.hidden = !open; });
      btn.setAttribute('aria-expanded', String(open));
      btn.textContent = open ? 'Свернуть' : 'Показать всех спикеров (' + SF.featured.length + ')';
    });
  }

  // ---------- Темы = треки программы ----------
  function renderThemes() {
    var list = qs('[data-themes]');
    if (!list) return;
    list.innerHTML = SF.tracks.map(function (t) {
      return '<li><a class="theme" href="program.html?track=' + t.id + '" style="--c: var(--t' + t.id + ')">' +
        '<span class="theme-icon">' + icon('track-' + t.id) + '</span>' +
        '<span class="theme-body"><span class="theme-num"><span class="dot"></span>Трек ' + t.id + '</span>' +
        '<span class="theme-name">«' + window.hyph(esc(t.name)) + '»</span></span>' +
        '<span class="theme-go">' + icon('arrow-right', 'icon-lg') + '</span></a></li>';
    }).join('');
  }

  // ---------- Программа кратко ----------
  function trackTag(id) {
    var t = SF.tracks[id - 1];
    return '<span class="tag" style="--c: var(--t' + id + ')"><span class="dot"></span>Т' + id + ' · ' + esc(t.short) + '</span>';
  }
  function renderDays() {
    var box = qs('[data-days]');
    if (!box) return;
    box.innerHTML = SF.daysBrief.map(function (d) {
      var tags = d.tracks.length > 3
        ? '<span class="tag" style="--c: var(--indigo-600)"><span class="dot"></span>' + d.tracks.length + ' треков параллельно</span>'
        : d.tracks.map(trackTag).join('');
      return '<a class="day-row' + (d.main ? ' is-main' : '') + '" href="program.html?day=' + d.day + '">' +
        '<div class="day-date">' + esc(d.date) + '<small>' + esc(d.weekday) + ' · день ' + d.day + '</small></div>' +
        '<div><p class="day-title">' + (d.main ? '<span class="badge badge-main" style="margin-right:8px">Главный день</span>' : '') + esc(d.title) + '</p>' +
        '<div class="day-meta"><span class="place">' + icon('pin') + esc(d.place) + '</span><span class="day-tags">' + tags + '</span></div></div>' +
        (d.photo ? '<img class="day-thumb" src="' + window.asset(d.photo) + '" alt="" loading="lazy">' : '<span class="theme-go" style="color:var(--indigo-600)">' + icon('arrow-right', 'icon-lg') + '</span>') +
        '</a>';
    }).join('');
  }

  // ---------- Экскурсии: карточки со счётчиком мест ----------
  var seats = {};
  function excursions() {
    var list = [];
    PR.days.forEach(function (d) { d.items.forEach(function (it) { if (it.excursion) list.push({ item: it, day: d }); }); });
    return list;
  }
  function renderExcursions() {
    var box = qs('[data-excursions]');
    if (!box) return;
    var mine = window.store.get(window.forumKey('sf-mine'), PR.defaultMine);
    box.innerHTML = excursions().map(function (r) {
      var it = r.item, x = it.excursion, s = seats[it.id];
      var left = s ? s.left : Math.max(0, x.limit - x.taken);
      var chosen = mine.indexOf(it.id) !== -1;
      var badge = left > 0
        ? '<span class="badge badge-seats">Осталось ' + left + ' ' + plural(left, ['место', 'места', 'мест']) + ' из ' + x.limit + '</span>'
        : '<span class="badge badge-changed">Мест нет · лист ожидания</span>';
      return '<li class="x-card"><img src="' + window.asset(it.photo) + '" alt="" loading="lazy">' +
        '<div class="x-body"><p class="x-when">' + icon('calendar') + esc(r.day.tab) + ' · ' + S.range(it) + '</p>' +
        '<h3 class="x-title">' + esc(it.title) + '</h3>' +
        '<p class="x-desc">' + esc(it.desc) + '</p>' +
        '<p class="x-req">' + icon('users') + esc(x.age) + ' · ' + esc(x.docs) + '</p>' +
        '<div class="x-foot">' + badge +
        (chosen ? '<a class="btn btn-secondary btn-sm" href="register.html">' + icon('check') + 'Выбрано</a>'
          : '<a class="btn btn-primary btn-sm" href="register.html" data-pick-excursion="' + it.id + '">' + (left > 0 ? 'Записаться' : 'В лист ожидания') + '</a>') +
        '</div></div></li>';
    }).join('');
  }

  // ---------- Площадки ----------
  function renderVenues() {
    var box = qs('[data-venues]');
    if (!box) return;
    var used = [];
    PR.days.forEach(function (d) { d.items.forEach(function (it) { if (used.indexOf(it.venue) === -1 && it.venue !== 'plants' && it.venue !== 'bus') used.push(it.venue); }); });
    box.innerHTML = used.map(function (k) {
      var v = PR.venues[k];
      return '<li>' + icon('pin') + '<span><b>' + esc(v.name) + '</b>' + esc(v.address) + '</span></li>';
    }).join('');
  }

  // ---------- Логотипы ----------
  function renderLogos() {
    document.querySelectorAll('[data-logos]').forEach(function (ul) {
      var kind = ul.getAttribute('data-logos');
      ul.innerHTML = SF[kind].map(function (o) {
        return '<li><a class="logo-item" href="' + o.url + '" target="_blank" rel="noopener">' +
          '<img src="' + window.asset('img/logos/' + kind + '/' + o.logo) + '" alt="" loading="lazy">' +
          '<span class="logo-caption">' + esc(o.name) + '</span></a></li>';
      }).join('');
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    renderSpeakers();
    renderThemes();
    renderDays();
    renderExcursions();
    renderVenues();
    renderLogos();
    window.initHero(SF.forum);
    window.hydrateIcons();
    window.API.seats().then(function (st) { if (st && !st.error) { seats = st; renderExcursions(); } });
    // «Записаться» на экскурсию — экскурсия попадает в выбор на первом шаге регистрации
    document.addEventListener('click', function (e) {
      var a = e.target.closest('[data-pick-excursion]');
      if (!a) return;
      var mine = window.store.get(window.forumKey('sf-mine'), PR.defaultMine);
      if (mine.indexOf(a.getAttribute('data-pick-excursion')) === -1) mine.push(a.getAttribute('data-pick-excursion'));
      window.store.set(window.forumKey('sf-mine'), mine);
    });
  });
})();
