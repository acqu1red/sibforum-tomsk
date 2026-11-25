/* Общее для всех страниц: шапка, мобильное меню, cookie, всплывающие сообщения, склонения. */
(function () {
  'use strict';

  // Production shares this switch with the Nginx write gate.
  // Local prototype servers do not expose this endpoint.
  window.consumeInitialData = function (url) {
    var initial = window.forumInitialData && window.forumInitialData[url];
    if (initial) delete window.forumInitialData[url];
    return initial || null;
  };
  window.publicDeploymentReady = (window.consumeInitialData('/deployment-config.json') || fetch('/deployment-config.json', { cache: 'no-store' }))
    .then(function (response) {
      if (response && typeof response.json !== 'function') return response;
      if (!response) throw new Error('Deployment status unavailable');
      if (response.status === 404) return { submissions_enabled: 1, voting_enabled: 1 };
      if (!response.ok) throw new Error('Deployment status unavailable');
      return response.json();
    }).catch(function () { return { submissions_enabled: 0, voting_enabled: 0 }; });
  window.publicSubmissionsReady = window.publicDeploymentReady.then(function(c){return c.submissions_enabled === 1 || c.submissions_enabled === true;});
  window.publicVotingReady = window.publicDeploymentReady.then(function(c){return c.voting_enabled === 1 || c.voting_enabled === true;});

  // Безопасная работа с localStorage (может быть недоступен в приватном режиме)
  window.store = {
    get: function (key, fallback) {
      try { var v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
    },
    set: function (key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* без сохранения */ }
    }
  };

  // Пути к картинкам в данных записаны от корня сайта ('img/...'). Страницы сайта форума лежат в подпапке
  // (esg2026/ — как поддомен) и задают window.SITE_ROOT = '../'.
  window.asset = function (path) {
    if (!path || /^(https?:|data:|\/)/.test(path)) return path;
    if (window.PUBLIC_ASSET_BASE_URL && path.indexOf('img/') === 0) return window.PUBLIC_ASSET_BASE_URL + '/' + path;
    return (window.SITE_ROOT || '') + path;
  };

  // Ключи хранилища отдельные для каждого форума: «Моя программа» V форума не смешается с программой следующего
  window.forumKey = function (key) {
    return window.SF && window.SF.forum && window.SF.forum.id ? key + ':' + window.SF.forum.id : key;
  };

  // Склонение: plural(5, ['день', 'дня', 'дней'])
  window.plural = function (n, forms) {
    var a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b > 1 && b < 5) return forms[1];
    if (b === 1) return forms[0];
    return forms[2];
  };

  // Мягкие переносы в длинных русских словах: браузер не везде расставляет их сам (hyphens: auto),
  // а в узких колонках иначе рвёт слово без дефиса. Перенос показывается, только если слово не влезает.
  var VOW = 'аеёиоуыэюяАЕЁИОУЫЭЮЯ';
  function isV(c) { return VOW.indexOf(c) !== -1; }
  // «пр», «тр», «кл»… не разрываем: су-прав-ле-ние, а не суп-рав-ле-ние
  function onset(a, b) { return 'бвгдкпстфхБВГДКПСТФХ'.indexOf(a) !== -1 && 'рл'.indexOf(b) !== -1; }
  window.hyph = function (text) {
    return text.replace(/[А-Яа-яЁё]{9,}/g, function (w) {
      var out = '';
      for (var i = 0; i < w.length; i++) {
        out += w[i];
        if (i < 1 || i > w.length - 4) continue;
        var a = w[i], b = w[i + 1], c = w[i + 2], d = w[i + 3];
        var vcv = isV(a) && !isV(b) && isV(c) && 'ьъй'.indexOf(b) === -1;
        var vcrv = isV(a) && onset(b, c) && isV(d);
        var vccv = !isV(a) && isV(w[i - 1]) && !isV(b) && isV(c) && 'ьъй'.indexOf(a) === -1 && 'ьъй'.indexOf(b) === -1 && !onset(a, b);
        var soft = 'ьъй'.indexOf(a) !== -1 && !isV(b) && isV(c);
        if (vcv || vcrv || vccv || soft) out += '­';
      }
      return out;
    });
  };

  window.escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  var toastEl, toastTimer;
  window.toast = function (message, type) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'toast';
      toastEl.setAttribute('role', 'status');
      toastEl.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = message;
    toastEl.classList.toggle('warn', type === 'warn');
    toastEl.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('is-visible'); }, 4200);
  };

  document.addEventListener('DOMContentLoaded', function () {
    document.addEventListener('click', function (event) {
      var button = event.target.closest('[data-load-map]');
      if (!button) return;
      var preview = button.closest('[data-map-url]');
      var frame = document.createElement('iframe');
      frame.src = preview.getAttribute('data-map-url');
      frame.title = preview.getAttribute('data-map-title');
      frame.allowFullscreen = true;
      frame.tabIndex = 0;
      preview.replaceWith(frame);
      frame.focus();
    });

    // Шапка становится плотной при прокрутке
    var header = document.getElementById('header');
    if (header && !header.classList.contains('always-solid')) {
      var onScroll = function () { header.classList.toggle('is-solid', window.scrollY > 24); };
      onScroll();
      window.addEventListener('scroll', onScroll, { passive: true });
    }

    // Мобильное меню
    var menu = document.getElementById('mobile-menu');
    var opener = document.querySelector('[data-menu-open]');
    if (menu && opener) {
      var close = function () {
        menu.classList.remove('is-open');
        opener.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
        opener.focus();
      };
      opener.addEventListener('click', function () {
        menu.classList.add('is-open');
        opener.setAttribute('aria-expanded', 'true');
        document.body.style.overflow = 'hidden';
        window.setTimeout(function () {
          if (!menu.classList.contains('is-open')) return;
          var first = menu.querySelector('a, button');
          if (first) first.focus();
        }, 280);
      });
      menu.addEventListener('click', function (event) {
        if (event.target.closest('[data-menu-close], a')) close();
      });
      document.addEventListener('keydown', function (e) {
        if (!menu.classList.contains('is-open')) return;
        if (e.key === 'Escape') close();
        if (e.key === 'Tab') {
          var items = Array.prototype.slice.call(menu.querySelectorAll('a[href], button:not([disabled])')).filter(function (item) { return item.offsetParent !== null; });
          var first = items[0], last = items[items.length - 1];
          if (first && e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          if (last && !e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      });
    }

    // Cookie
    var cookie = document.querySelector('[data-cookie]');
    if (cookie && !window.store.get('sf-cookie-ok', false)) {
      cookie.hidden = false;
      cookie.querySelector('[data-cookie-ok]').addEventListener('click', function () {
        window.store.set('sf-cookie-ok', true);
        cookie.hidden = true;
      });
    }
  });
})();
