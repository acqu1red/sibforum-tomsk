/* Клиент API регистрации. Если сайт открыт через локальный сервер (server/server.py) — данные уходят на него.
   Если страница открыта файлом или сервер недоступен — демо-режим: те же операции в localStorage браузера. */
window.API = (function () {
  'use strict';
  var PR = window.PROGRAM;
  var DEMO_KEY = 'sf-demo-registrations';
  var mode = null;

  var ready = (location.protocol === 'file:' ? Promise.resolve('demo') :
    fetch('/api/ping', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return j && j.mode === 'server' ? 'server' : 'demo'; })
      .catch(function () { return 'demo'; })
  ).then(function (m) { mode = m; return m; });

  function post(path, body) {
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { j.status = r.status; return j; }); });
  }

  // ---------- Демо-режим (повторяет логику сервера) ----------
  var excursions = {};
  PR.days.forEach(function (d) { d.items.forEach(function (it) { if (it.excursion) excursions[it.id] = it.excursion; }); });

  function demoLoad() { return window.store.get(DEMO_KEY, []); }
  function demoSave(regs) { window.store.set(DEMO_KEY, regs); }
  function now() { return new Date().toISOString(); }
  function token() {
    var a = new Uint8Array(12);
    (window.crypto || window.msCrypto).getRandomValues(a);
    return Array.prototype.map.call(a, function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
  }
  function seatState(regs, excludeId) {
    var st = {};
    Object.keys(excursions).forEach(function (ex) {
      var cfg = excursions[ex], confirmed = 0, waiting = 0;
      regs.forEach(function (r) {
        if (r.id === excludeId || !r.events[ex]) return;
        if (r.events[ex].status === 'confirmed') confirmed++; else waiting++;
      });
      st[ex] = { limit: cfg.limit, left: Math.max(0, cfg.limit - cfg.taken - confirmed), waitlist: waiting };
    });
    return st;
  }
  function applyEvents(regs, reg, wanted) {
    var seats = seatState(regs, reg.id), old = reg.events || {}, next = {};
    wanted.forEach(function (ev) {
      if (excursions[ev]) {
        var prev = old[ev];
        if (prev && prev.status === 'confirmed') next[ev] = prev;
        else if (seats[ev].left > 0) { next[ev] = { status: 'confirmed', at: now() }; seats[ev].left--; }
        else next[ev] = prev || { status: 'waitlist', at: now(), queue: seats[ev].waitlist + 1 };
      } else {
        next[ev] = old[ev] || { status: 'confirmed', at: now() };
      }
    });
    reg.events = next;
  }
  function pub(reg) {
    return { id: reg.id, token: reg.token, person: reg.person, events: reg.events, confirmed: !!reg.confirmed_at, created_at: reg.created_at, updated_at: reg.updated_at };
  }
  function mask(email) { var p = email.split('@'); return p[0].slice(0, 2) + '•••@' + p[1]; }

  var demo = {
    register: function (payload) {
      var regs = demoLoad(), email = payload.person.email.trim().toLowerCase();
      var reg = regs.filter(function (r) { return r.person.email === email; })[0], updated = !!reg;
      if (!reg) {
        reg = { id: 'R-' + String(regs.length + 1).padStart(4, '0'), token: token(), created_at: now(), events: {}, consents: [] };
        regs.push(reg);
      }
      reg.person = Object.assign({}, payload.person, { email: email });
      reg.updated_at = now();
      reg.consents.push(Object.assign({ at: now(), version: '1.0 от 01.03.2026' }, payload.consents));
      applyEvents(regs, reg, payload.events);
      if (!reg.confirmed_at) reg.code = String(Math.floor(1000 + Math.random() * 9000));
      demoSave(regs);
      return { ok: true, id: reg.id, token: reg.token, updated: updated, confirmed: !!reg.confirmed_at, email_masked: mask(email), events: reg.events, demo_code: reg.confirmed_at ? null : reg.code };
    },
    confirm: function (body) {
      var regs = demoLoad(), reg = regs.filter(function (r) { return r.token === body.token; })[0];
      if (!reg) return { ok: false, error: 'not_found' };
      if (!reg.confirmed_at) {
        if (reg.code !== body.code) return { ok: false, error: 'wrong_code' };
        reg.confirmed_at = now(); delete reg.code; demoSave(regs);
      }
      return { ok: true, registration: pub(reg) };
    },
    get: function (t) {
      var reg = demoLoad().filter(function (r) { return r.token === t; })[0];
      return reg ? { ok: true, registration: pub(reg) } : { ok: false, error: 'not_found' };
    },
    updateEvents: function (body) {
      var regs = demoLoad(), reg = regs.filter(function (r) { return r.token === body.token; })[0];
      if (!reg) return { ok: false, error: 'not_found' };
      applyEvents(regs, reg, body.events); reg.updated_at = now(); demoSave(regs);
      return { ok: true, registration: pub(reg) };
    },
    seats: function () { return seatState(demoLoad()); }
  };

  function via(serverCall, demoCall) {
    return ready.then(function (m) { return m === 'server' ? serverCall() : demoCall(); });
  }

  return {
    ready: ready,
    mode: function () { return mode; },
    register: function (payload) { return via(function () { return post('/api/register', payload); }, function () { return demo.register(payload); }); },
    confirm: function (t, code, id) { return via(function () { return post('/api/confirm', { token: t, code: code, id: id }); }, function () { return demo.confirm({ token: t, code: code, id: id }); }); },
    get: function (t) {
      return via(function () { return fetch('/api/registration?t=' + encodeURIComponent(t), { cache: 'no-store' }).then(function (r) { return r.json(); }); },
        function () { return demo.get(t); });
    },
    updateEvents: function (t, events) { return via(function () { return post('/api/registration/events', { token: t, events: events }); }, function () { return demo.updateEvents({ token: t, events: events }); }); },
    seats: function () { return via(function () { return fetch('/api/seats', { cache: 'no-store' }).then(function (r) { return r.json(); }); }, function () { return demo.seats(); }); }
  };
})();
