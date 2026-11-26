window.PROMTOUR_CONTENT.nominations = [];
window.loadPromtourNominations = function () {
  'use strict';
  var initial = window.consumeInitialData('/api/v1/contests/promtour/');
  if (initial) return initial.then(function (data) { return data || window.loadPromtourNominations(); });
  return fetch('/data/contest.json?v=bfc1bbe5ced5', { headers: { Accept: 'application/json' } }).then(function (response) {
    return response.json().then(function (data) {
      if (!response.ok) throw new Error(data.message || 'Не удалось загрузить номинации.');
      return data;
    });
  });
};
