(function () {
  'use strict';
  function init() {
    var preview = document.querySelector('[data-speaker-preview]');
    if (!preview) return;
    var urls = new Map();
    function fileUrl(input) {
      if (!input || !input.files || !input.files[0]) return '';
      var file = input.files[0];
      var old = urls.get(input);
      if (old && old.file === file) return old.url;
      if (old) URL.revokeObjectURL(old.url);
      var url = URL.createObjectURL(file);
      urls.set(input, { file: file, url: url });
      return url;
    }
    function update() {
      var base = fileUrl(document.getElementById('id_photo'));
      var clear = document.querySelector('[name="photo-clear"]');
      if (!base) base = (clear && clear.checked ? '' : preview.dataset.baseUrl) || '';
      var staticPhoto = document.getElementById('id_static_photo');
      if (!base && staticPhoto) base = staticPhoto.value;
      var contexts = {};
      document.querySelectorAll('[id$="-placement"]').forEach(function (select) {
        if (select.id.includes('__prefix__')) return;
        var prefix = select.id.slice(0, -'placement'.length);
        var deleted = document.getElementById(prefix + 'DELETE');
        if (deleted && deleted.checked) return;
        var image = document.getElementById(prefix + 'image');
        var upload = fileUrl(image);
        var clear = document.querySelector('[name="' + prefix.slice(3) + 'image-clear"]');
        var figure = preview.querySelector('[data-photo-context="' + select.value + '"]');
        var original = figure && figure.querySelector('img').dataset.original;
        var existing =
          image &&
          image.closest('.form-row') &&
          image.closest('.form-row').querySelector('.file-upload a');
        var url =
          upload ||
          (clear && clear.checked ? '' : existing ? existing.getAttribute('href') : '') ||
          base;
        contexts[select.value] = {
          url: url,
          fit: document.getElementById(prefix + 'fit').value,
          x: document.getElementById(prefix + 'focal_x').value,
          y: document.getElementById(prefix + 'focal_y').value
        };
      });
      preview.querySelectorAll('[data-photo-context]').forEach(function (figure) {
        var img = figure.querySelector('img'),
          c = contexts[figure.dataset.photoContext] || {
            url: base,
            fit: img.dataset.fit,
            x: img.dataset.x,
            y: img.dataset.y
          };
        img.src = c.url || '';
        img.style.objectFit = c.fit;
        img.style.objectPosition = c.x + '% ' + c.y + '%';
        var full = document.getElementById('id_full_name').value.trim().split(/\s+/);
        var short = document.getElementById('id_short_name').value.trim();
        figure.querySelector('[data-preview-name]').textContent =
          short || (full.length > 1 ? full[1] + ' ' + full[0] : full[0]) || 'Имя спикера';
        figure.querySelector('[data-preview-position]').textContent =
          document.getElementById('id_short_position').value;
      });
    }
    document.addEventListener('change', update);
    document.addEventListener('input', update);
    document.addEventListener('formset:added', update);
    update();
    // Keep the native file controls in place when Django returns validation
    // errors. A normal document navigation clears their selected files.
    var form = preview.closest('form');
    if (form) form.addEventListener('submit', async function (event) {
      if (![...form.querySelectorAll('input[type=file]')].some(function (input) { return input.files.length; })) return;
      event.preventDefault();
      if (form.dataset.sending === 'true') return;
      var data = new FormData(form);
      if (event.submitter && event.submitter.name) data.set(event.submitter.name, event.submitter.value);
      var buttons = [...form.querySelectorAll('input[type=submit],button[type=submit]')];
      form.dataset.sending = 'true'; buttons.forEach(function (button) { button.disabled = true; });
      try {
        var response = await fetch(form.action || location.href, {method:'POST', body:data});
        if (!response.ok) throw Error('Не удалось сохранить фотографию. Проверьте подключение и повторите попытку. Выбранный файл сохранён в форме.');
        var doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        var errors = [...doc.querySelectorAll('form .errorlist')];
        if (!errors.length && response.redirected) { location.assign(response.url); return; }
        if (!errors.length) throw Error('Проверьте сессию и обязательные поля. Фотография остаётся выбранной; можно повторить сохранение.');
        form.querySelectorAll('.errorlist,.errornote').forEach(function (el) { el.remove(); });
        form.querySelectorAll('.errors').forEach(function (el) { el.classList.remove('errors'); });
        errors.forEach(function (error) {
          var row = error.closest('.form-row'), input = row && row.querySelector('[name]');
          var target = input && form.querySelector('[name="'+CSS.escape(input.name)+'"]');
          var destination = target && target.closest('.form-row');
          if (destination) { destination.classList.add('errors'); destination.append(error.cloneNode(true)); }
          else form.prepend(error.cloneNode(true));
        });
        var note = document.createElement('p'); note.className = 'errornote'; note.tabIndex = -1;
        note.textContent = 'Исправьте выделенные поля. Фотография остаётся выбранной — загружать её заново не нужно.';
        form.prepend(note); note.focus();
      } catch (error) {
        var note = document.createElement('p'); note.className = 'errornote'; note.setAttribute('role','alert'); note.textContent = error.message; form.prepend(note);
      } finally { form.dataset.sending = 'false'; buttons.forEach(function (button) { button.disabled = false; }); }
    });
    window.addEventListener('pagehide', function () {
      urls.forEach(function (v) {
        URL.revokeObjectURL(v.url);
      });
      urls.clear();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
