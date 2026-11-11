window.PROMTOUR_CONTENT.nominations = [];
window.loadPromtourNominations = function () {
  'use strict';
  return fetch('/api/v1/contests/promtour/', { headers: { Accept: 'application/json' } }).then(function (response) {
    return response.json().then(function (data) {
      if (!response.ok) throw new Error(data.message || 'Не удалось загрузить номинации.');
      return data;
    });
  });
};
