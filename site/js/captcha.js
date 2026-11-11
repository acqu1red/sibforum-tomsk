window.ForumCaptcha = (function () {
  'use strict';
  function init(containerId, inputId) {
    var container = document.getElementById(containerId);
    var input = document.getElementById(inputId);
    if (!container || !input) return;
    var started = false;
    function load() {
      if (started) return;
      started = true;
      fetch('/api/v1/public-config/', { cache: 'no-store' })
      .then(function (response) { return response.json(); })
      .then(function (config) {
        if (!config.captcha_enabled || !config.client_id) return;
        container.hidden = false;
        window.onloadFunction = function () {
          if (!window.smartCaptcha) return;
          var widget = window.smartCaptcha.render(containerId, {
            sitekey: config.client_id,
            hl: 'ru',
            callback: function (token) { input.value = token; }
          });
          window.smartCaptcha.subscribe(widget, 'token-expired', function () { input.value = ''; });
        };
        var script = document.createElement('script');
        script.src = 'https://smartcaptcha.cloud.yandex.ru/captcha.js?render=onload&onload=onloadFunction';
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      })
      .catch(function () { container.hidden = true; started = false; });
    }
    var form = container.closest('form') || container.parentElement;
    form.addEventListener('focusin', load, { once: true });
    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function (entries) {
        if (entries.some(function (entry) { return entry.isIntersecting; })) {
          observer.disconnect(); load();
        }
      }, { rootMargin: '300px' });
      observer.observe(form);
    } else load();
  }
  return { init: init };
})();
