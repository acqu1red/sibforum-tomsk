/* Портал использует реальные даты промтура. Архивный шаблон ESG сохраняет прежние демонстрационные состояния. */
window.initHero = function (forum) {
  'use strict';
  var hero = document.querySelector('[data-hero]') || document.querySelector('.hero[data-state]');
  if (!hero) return;
  var UNITS = { d: ['день', 'дня', 'дней'], h: ['час', 'часа', 'часов'], m: ['минута', 'минуты', 'минут'], s: ['секунда', 'секунды', 'секунд'] };

  var timerNodes = {};
  Object.keys(UNITS).forEach(function (key) { timerNodes[key] = [hero.querySelector('[data-t="' + key + '"]'), hero.querySelector('[data-u="' + key + '"]')]; });
  function setText(node, value) { if (node && node.textContent !== value) node.textContent = value; }

  function updateTimer(target) {
    var left = Math.max(0, target - Date.now());
    var v = { d: Math.floor(left / 864e5), h: Math.floor(left / 36e5) % 24, m: Math.floor(left / 6e4) % 60, s: Math.floor(left / 1e3) % 60 };
    Object.keys(v).forEach(function (k) {
      setText(timerNodes[k][0], k === 'd' ? String(v[k]) : String(v[k]).padStart(2, '0'));
      setText(timerNodes[k][1], window.plural(v[k], UNITS[k]));
    });
  }

  if (forum.id === 'promtour2026') {
    var timerId = null;
    var currentState = '';
    var start = new Date(forum.start).getTime();
    var end = new Date(forum.end).getTime();
    var registrationOpen = forum.registrationOpen ? new Date(forum.registrationOpen).getTime() : NaN;
    var program = null;
    var programRequested = false;
    var lastLiveMinute = -1;
    function loadLiveProgram() {
      if (programRequested) return;
      programRequested = true;
      fetch('/api/v1/forums/promtour/program/', { headers: { Accept: 'application/json' } }).then(function (response) { return response.ok ? response.json() : null; }).then(function (data) { program = data; if (currentState === 'C') updateLive(Date.now()); }).catch(function () { programRequested = false; });
    }

    function stateByDates(now) {
      if (now < start) return Number.isFinite(registrationOpen) && now < registrationOpen ? 'A' : 'B';
      if (now <= end) return 'C';
      return 'D';
    }

    function updateLive(now) {
      var live = (forum.liveDays || []).filter(function (item) {
        return now >= new Date(item.start).getTime() && now < new Date(item.end).getTime();
      })[0];
      var title = hero.querySelector('[data-live-title]');
      var detail = hero.querySelector('[data-live-detail]');
      var eventText = '';
      if (program) {
        var local = new Date(now + 7 * 36e5);
        var date = local.toISOString().slice(0, 10);
        var time = local.toISOString().slice(11, 16);
        var day = program.days.filter(function (item) { return item.date === date; })[0];
        if (day) {
          var summary = day.events.some(function (event) { return event.slug === 'routes'; });
          eventText = day.events.filter(function (event) {
            return !(summary && event.kind === 'route') && event.start_time <= time && time < event.end_time;
          }).map(function (event) { return event.title; }).join(' · ');
        }
      }
      if (title) title.textContent = live ? live.title : 'Сибирский форум по промышленному туризму';
      if (detail) detail.textContent = eventText || (live ? live.detail : forum.venue + ', ' + forum.address);
    }

    function renderPortalState() {
      var now = Date.now();
      var state = stateByDates(now);
      if (state !== currentState) {
        currentState = state;
        hero.setAttribute('data-state', state);
      }
      if (state === 'A' || state === 'B') updateTimer(start);
      if (state === 'C') {
        var minute = Math.floor(now / 60000);
        if (minute !== lastLiveMinute) { lastLiveMinute = minute; loadLiveProgram(); updateLive(now); }
      }
      if (state === 'D' && timerId) {
        clearInterval(timerId);
        timerId = null;
      }
    }

    function resumeTimer() {
      if (timerId) clearInterval(timerId);
      timerId = null;
      if (document.hidden) return;
      renderPortalState();
      if (currentState !== 'D') timerId = setInterval(renderPortalState, 1000);
    }
    document.addEventListener('visibilitychange', resumeTimer);
    resumeTimer();
    return;
  }

  var target, timerId;
  function legacyStateByDates(now) {
    if (now < new Date(forum.start)) return 'B';
    if (now <= new Date(forum.end)) return 'C';
    return 'D';
  }

  function setLegacyState(state) {
    hero.setAttribute('data-state', state);
    document.querySelectorAll('[data-proto-state]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-proto-state') === state));
    });
    clearInterval(timerId);
    if (state === 'A' || state === 'B') {
      var start = new Date(forum.start).getTime();
      target = start > Date.now() ? start : Date.now() + ((23 * 24 + 14) * 60 + 5) * 6e4 + 32e3;
      updateTimer(target);
      timerId = setInterval(function () { if (!document.hidden) updateTimer(target); }, 1000);
    }
    var url = new URL(window.location.href);
    url.searchParams.set('state', state);
    history.replaceState(null, '', url);
  }

  var param = new URLSearchParams(location.search).get('state');
  setLegacyState(param === 'auto' ? legacyStateByDates(new Date()) : (/^[ABCD]$/.test(param || '') ? param : 'B'));
  document.querySelectorAll('[data-proto-state]').forEach(function (b) {
    b.addEventListener('click', function () { setLegacyState(b.getAttribute('data-proto-state')); });
  });
};
