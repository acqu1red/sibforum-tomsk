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
