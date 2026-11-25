/* Витрина siberianforum.ru: ближайший промтур и архив с фильтрами по серии и году. */
(function () {
  'use strict';
  var P = window.PORTAL, esc = window.escapeHtml, icon = window.icon, plural = window.plural;
  var YEARS = P.archive.map(function (f) { return f.year; }).filter(function (year, index, all) { return all.indexOf(year) === index; }).sort(function (a, b) { return b - a; });
  var filter = { series: 'all', year: 'all' };

  function qsa(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function external(url) { return /^https?:/.test(url); }
  function linkAttrs(url) { return 'href="' + esc(url) + '"' + (external(url) ? ' target="_blank" rel="noopener"' : ''); }

  function logos(key) {
    var s = P.series[key];
    return s.logo
      ? '<img class="fcard-logo" src="' + esc(s.logo) + '" alt="" width="320" height="180" loading="lazy" decoding="async">'
      : '<div class="fcard-logos">' + s.logos.map(function (l) { return '<img src="' + esc(l) + '" alt="">'; }).join('') + '</div>';
  }

  function titleHtml(f) {
    var s = P.series[f.series];
    return f.series === 'esg'
      ? (f.num ? esc(f.num) + ' ' : '') + 'Сибирский форум <span>«' + esc(s.name) + '»</span>'
      : (f.num ? esc(f.num) + ' ' : '') + 'Сибирский форум по промышленному туризму <span>' + esc(f.hashtag || s.hashtag) + '</span>';
  }

  function currentCard(f) {
    var c = P.current;
    return '<article class="fcard fcard-current series-' + f.series + '" data-hero data-state="B" aria-labelledby="current-forum-title">' +
      '<div class="fcard-cover">' + logos(f.series) + '</div>' +
      '<div class="fcard-body">' +
      '<p class="fcard-kicker">Ближайший форум · ' + esc(P.series[f.series].season.toLowerCase()) + ' ' + f.year + '</p>' +
      '<h2 class="fcard-title" id="current-forum-title">' + titleHtml(f) + '</h2>' +
      '<p class="fcard-date">' + icon('calendar') + esc(c.dates) + ' · ' + esc(c.city) + '</p>' +
      '<p class="fcard-date fcard-venue">' + icon('pin') + '<span><b>Деловая программа:</b> ' + esc(c.venue) + ', ' + esc(c.address) + '</span></p>' +
      '<div class="hero-state" data-for="A"><span class="badge badge-open"><span class="dot" style="background:var(--signal)"></span>Анонс · регистрация скоро откроется</span></div>' +
      '<div class="hero-state" data-for="B"><span class="badge badge-open"><span class="dot"></span>Регистрация открыта</span></div>' +
      '<div class="hero-state" data-for="C"><span class="badge badge-live"><span class="dot"></span>Форум идёт сейчас</span>' +
      '<p class="hero-now" data-live-title></p><p class="fcard-live-detail" data-live-detail></p></div>' +
      '<div class="hero-state" data-for="D"><span class="badge badge-muted">Форум завершён · итоги и материалы</span></div>' +
      '<div class="hero-state" data-for="A B"><p class="fcard-timer-label" id="portal-timer-label">До начала форума · 23 ноября, 09:00 по Томску</p>' +
      '<div class="timer fcard-timer" role="timer" aria-labelledby="portal-timer-label">' +
      ['d', 'h', 'm', 's'].map(function (k) { return '<div class="timer-cell"><div class="timer-num" data-t="' + k + '">—</div><div class="timer-unit" data-u="' + k + '"></div></div>'; }).join('') +
      '</div></div>' +
      '<p class="fcard-desc">' + esc(c.desc) + '</p>' +
      '<a class="fcard-route-link" href="' + esc(c.routes) + '" data-routes-link><strong>' + c.routeCount + ' экскурсионных маршрутов</strong><span>23 ноября · отправление от ТПП Томской области в 09:15</span>' + icon('arrow-right') + '</a>' +
      '<div class="fcard-actions">' +
      '<a class="btn btn-light hero-state-inline" data-for="B" href="' + esc(c.register) + '" data-register-link>Зарегистрироваться</a>' +
      '<a class="btn btn-light hero-state-inline" data-for="C" href="' + esc(c.program) + '" data-program-link>Программа на сегодня</a>' +
      '<a class="btn btn-light hero-state-inline" data-for="D" href="' + esc(c.site) + '">Итоги и материалы</a>' +
      '<a class="btn btn-ghost-light hero-state-inline" data-for="A B C D" href="' + esc(c.site) + '" data-forum-link>Перейти на сайт форума ' + icon('arrow-right') + '</a>' +
      '<a class="btn btn-ghost-light hero-state-inline" data-for="A B D" href="' + esc(c.program) + '" data-program-link>Программа</a>' +
      '<a class="btn btn-contest hero-state-inline" data-for="A B C D" href="' + esc(c.contest) + '" data-contest-link>Конкурс «Индустриальный код»</a>' +
      '</div></div></article>';
  }

  window.renderPortalCurrentCard = currentCard;

  function card(f) {
    return '<li class="fcard series-' + f.series + '" data-series="' + f.series + '" data-year="' + f.year + '">' +
      '<div class="fcard-cover">' + logos(f.series) + '</div><div class="fcard-body">' +
      '<p class="fcard-kicker">' + esc(P.series[f.series].season) + ' ' + f.year + '</p>' +
      '<h3 class="fcard-title">' + titleHtml(f) + '</h3>' +
      '<p class="fcard-date">' + icon('calendar') + esc(f.dates) + '</p>' +
      '<p class="fcard-desc">' + esc(f.desc) + '</p>' +
      '<div class="fcard-foot"><span class="fcard-status">Форум прошёл</span>' +
      '<a class="btn btn-secondary btn-sm" ' + linkAttrs(f.url) + '>Перейти на сайт ' + icon('external') + '</a></div></div></li>';
  }

  function render() {
    var cur = P.archive.filter(function (f) { return f.current; })[0];
    var current = document.querySelector('[data-current-forum]');
    if (!current.querySelector('.fcard-current')) current.innerHTML = cur ? currentCard(cur) : '';
    var list = P.archive.filter(function (f) { return !f.current; }).sort(function (a, b) {
      return b.year - a.year || (a.series === 'promtour' ? -1 : 1);
    });
    document.querySelector('[data-forums]').innerHTML = list.map(card).join('');
    document.querySelector('[data-filter-year]').innerHTML = '<button class="chip" type="button" aria-pressed="true" data-year="all">Все годы</button>' +
      YEARS.map(function (y) { return '<button class="chip" type="button" aria-pressed="false" data-year="' + y + '">' + y + '</button>'; }).join('');
  }

  function applyFilter() {
    var visible = 0;
    qsa('[data-forums] > .fcard').forEach(function (el) {
      var ok = (filter.series === 'all' || el.getAttribute('data-series') === filter.series) &&
        (filter.year === 'all' || el.getAttribute('data-year') === String(filter.year));
      el.hidden = !ok;
      if (ok) visible += 1;
    });
    qsa('[data-filter-series] .chip').forEach(function (c) { c.setAttribute('aria-pressed', String(c.getAttribute('data-series') === filter.series)); });
    qsa('[data-filter-year] .chip').forEach(function (c) { c.setAttribute('aria-pressed', String(c.getAttribute('data-year') === String(filter.year))); });
    var count = document.querySelector('[data-archive-count]');
    if (count) count.textContent = 'По выбранным фильтрам: ' + visible + ' ' + plural(visible, ['форум', 'форума', 'форумов']);
  }

  document.addEventListener('DOMContentLoaded', function () {
    render();
    window.publicSubmissionsReady.then(function (enabled) {
      if (enabled) return;
      var badge = document.querySelector('.fcard-current [data-for="B"] .badge');
      if (badge) badge.textContent = 'Приём заявок временно недоступен';
    });
    applyFilter();
    document.addEventListener('click', function (e) {
      var t = e.target.closest('[data-filter-series] .chip, [data-filter-year] .chip');
      if (!t) return;
      if (t.closest('[data-filter-series]')) filter.series = t.getAttribute('data-series');
      else filter.year = t.getAttribute('data-year') === 'all' ? 'all' : +t.getAttribute('data-year');
      applyFilter();
    });
    window.initHero(P.current);
    window.hydrateIcons();
  });
})();
