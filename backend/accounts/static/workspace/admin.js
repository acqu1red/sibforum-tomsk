(function () {
  'use strict';
  var disclosure = document.querySelector('.workspace-mobile-nav');
  if (disclosure) disclosure.addEventListener('toggle', function () {
    disclosure.closest('.workspace-sidebar').classList.toggle('is-open', disclosure.open);
  });
})();
