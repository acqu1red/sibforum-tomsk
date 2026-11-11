window.ForumCaptcha = (function () {
  'use strict';
  function init(containerId, inputId) {
    var container = document.getElementById(containerId);
    var input = document.getElementById(inputId);
    if (!container || !input) return;
    fetch('/api/v1/public-config/', { cache: 'no-store' })
      .then(function (response) { return response.json(); })
      .then(function (config) {
        if (!config.captcha_enabled || !config.client_id) return;
        container.hidden = false;
        window.onloadFunction = function () {
          if (!window.smartCaptcha) return;
          window.smartCaptcha.render(containerId, {
            sitekey: config.client_id,
            hl: 'ru',
            callback: function (token) { input.value = token; }
          });
        };
        var script = document.createElement('script');
        script.src = 'https://smartcaptcha.cloud.yandex.ru/captcha.js?render=onload&onload=onloadFunction';
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      })
      .catch(function () { container.hidden = true; });
  }
  return { init: init };
})();
