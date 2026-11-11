(function () {
  'use strict';
  var API = '/api/v1/contests/promtour';
  var esc = window.escapeHtml;
  var state = { contest: null, email: '', open: false, lastFocus: null };

  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
  function showError(selector, message) {
    var box = $(selector);
    box.textContent = message || '';
    box.hidden = !message;
  }
  function api(path, options) {
    options = options || {};
    options.headers = Object.assign({ 'Accept': 'application/json' }, options.headers || {});
    if (options.body) options.headers['Content-Type'] = 'application/json';
    return fetch(API + path, options).then(function (response) {
      return response.json().catch(function () { throw new Error('Сервер вернул некорректный ответ.'); }).then(function (data) {
        if (!response.ok) throw new Error(data.message || 'Не удалось выполнить запрос.');
        return data;
      });
    }).catch(function (error) {
      if (error instanceof TypeError) throw new Error('Сервис временно недоступен. Попробуйте обновить страницу позже.');
      throw error;
    });
  }
  function votingIsOpen(contest) {
    var now = Date.now();
    return contest.is_open && (!contest.voting_opens_at || now >= new Date(contest.voting_opens_at).getTime()) && (!contest.voting_closes_at || now <= new Date(contest.voting_closes_at).getTime());
  }
  function safeWebsiteUrl(value) {
    try {
      var url = new URL(value);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : '';
    } catch (error) {
      return '';
    }
  }

  function candidateHtml(nomination, nominee) {
    var website = safeWebsiteUrl(nominee.website_url);
    return '<article class="promtour-nominee"><label class="check"><input type="checkbox" data-nomination="' + esc(nomination.id) + '" data-nominee="' + esc(nominee.id) + '"><span><b>' + esc(nominee.name) + '</b></span></label>' +
      (nominee.description ? '<p>' + esc(nominee.description) + '</p>' : '') +
      (website ? '<p class="contest-nominee-site"><a href="' + esc(website) + '" target="_blank" rel="noopener noreferrer">Сайт компании<span class="visually-hidden"> (откроется в новой вкладке)</span></a></p>' : '') + '</article>';
  }

  function nominationHtml(nomination) {
    var count = nomination.nominees.length;
    var limit = nomination.max_selections === 1 ? 'Можно выбрать одного кандидата.' : 'Можно выбрать не более ' + nomination.max_selections + ' кандидатов.';
    return '<details class="promtour-nomination" data-nomination-card="' + esc(nomination.id) + '">' +
      '<summary><span class="promtour-nomination-number">' + String(nomination.number).padStart(2, '0') + '</span><span><b>' + esc(nomination.title) + '</b><small>' + count + ' ' + window.plural(count, ['номинант', 'номинанта', 'номинантов']) + ' · можно пропустить</small></span></summary>' +
      '<div class="promtour-nomination-body"><label class="check promtour-skip"><input type="checkbox" data-skip-nomination="' + esc(nomination.id) + '"><span>Я не знаком(а) с этой номинацией — пропустить</span></label>' +
      '<p class="contest-nomination-limit">' + limit + '</p><div class="promtour-nominees">' + nomination.nominees.map(function (nominee) { return candidateHtml(nomination, nominee); }).join('') + '</div></div></details>';
  }

  function renderContest() {
    var contest = state.contest;
    state.open = votingIsOpen(contest);
    $('[data-contest-description]').textContent = contest.description || 'Восемь номинаций для проектов Томской области в сфере промышленного туризма.';
    $('[data-contest-state]').textContent = state.open
      ? 'Онлайн-голосование открыто. Подтвердите email, чтобы отправить бюллетень и защитить конкурс от повторных голосов.'
      : 'Голосование закрыто или ещё не началось. Номинации и кандидаты доступны для просмотра.';
    var primary = contest.nominations.filter(function (nomination) { return Number(nomination.visual_group) === 1; });
    var rest = contest.nominations.filter(function (nomination) { return Number(nomination.visual_group) !== 1; });
    var html = '';
    if (primary.length) html += '<div class="promtour-nomination-group"><h2>Бренд, маршрут и музей</h2><p>Три самостоятельные номинации с раздельным выбором.</p>' + primary.map(nominationHtml).join('') + '</div>';
    html += rest.map(nominationHtml).join('');
    $('[data-nominations]').innerHTML = html;
    $('[data-ballot-form]').hidden = !state.open;
    $$('[data-nomination-card]').forEach(syncNomination);
    updateSelectionSummary();
  }

  function syncNomination(card) {
    var skipped = $('[data-skip-nomination]', card).checked;
    $$('[data-nominee]', card).forEach(function (input) {
      input.disabled = skipped || !state.open;
      if (skipped) input.checked = false;
    });
    $('[data-skip-nomination]', card).disabled = !state.open;
    card.classList.toggle('is-skipped', skipped);
  }

  function updateSelectionSummary() {
    var selected = $$('input[data-nominee]:checked');
    var nominations = {};
    selected.forEach(function (input) { nominations[input.getAttribute('data-nomination')] = true; });
    var nominationCount = Object.keys(nominations).length;
    $('[data-selection-summary]').textContent = selected.length
      ? 'Выбрано: ' + selected.length + ' ' + window.plural(selected.length, ['кандидат', 'кандидата', 'кандидатов']) + ' в ' + nominationCount + ' ' + window.plural(nominationCount, ['номинации', 'номинациях', 'номинациях']) + '.'
      : 'Вы пока не выбрали кандидатов. Незнакомые номинации можно пропустить.';
  }

  function selectionPayload() {
    var selections = {};
    $$('input[data-nominee]:checked').forEach(function (input) {
      var nomination = input.getAttribute('data-nomination');
      if (!selections[nomination]) selections[nomination] = [];
      selections[nomination].push(input.getAttribute('data-nominee'));
    });
    return Object.keys(selections).map(function (id) { return { nomination_id: id, nominee_ids: selections[id] }; });
  }

  function openBallotReview() {
    if (!state.contest) return;
    state.lastFocus = document.activeElement;
    var html = '<h2 id="ballot-dialog-title">Проверка бюллетеня</h2><p>Проверьте выбранных кандидатов перед подтверждением email.</p><div class="promtour-ballot-review">';
    state.contest.nominations.forEach(function (nomination) {
      var card = $('[data-nomination-card="' + nomination.id + '"]');
      var skipped = $('[data-skip-nomination]', card).checked;
      var selected = $$('[data-nominee]:checked', card).map(function (input) {
        var nominee = nomination.nominees.find(function (item) { return item.id === input.getAttribute('data-nominee'); });
        return nominee ? nominee.name : '';
      }).filter(Boolean);
      html += '<section><h3>' + esc(nomination.title) + '</h3>' +
        (selected.length ? '<ul>' + selected.map(function (name) { return '<li>' + esc(name) + '</li>'; }).join('') + '</ul>' : '<p>' + (skipped ? 'Номинация пропущена' : 'Выбор не сделан') + '</p>') + '</section>';
    });
    html += '</div><p class="promtour-contest-disclaimer">Голос ещё не отправлен. Он будет зарегистрирован только после ввода кода из письма.</p><p><button class="btn btn-primary" type="button" data-dialog-close>Вернуться к бюллетеню</button></p>';
    $('[data-ballot-dialog-content]').innerHTML = html;
    $('[data-ballot-dialog]').showModal();
  }

  function submitBallot(event) {
    event.preventDefault();
    var form = event.currentTarget;
    showError('[data-form-error]', '');
    if (!state.open) {
      showError('[data-form-error]', 'Голосование закрыто или ещё не началось.');
      return;
    }
    var selections = selectionPayload();
    if (!selections.length) {
      showError('[data-form-error]', 'Выберите хотя бы одного кандидата в любой номинации.');
      return;
    }
    if (!form.reportValidity()) return;
    var email = $('#vote-email').value.trim();
    state.email = email;
    var button = $('[data-submit-ballot]');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    api('/ballots/', {
      method: 'POST',
      body: JSON.stringify({ email: email, selections: selections, captcha_token: $('#captcha-token').value })
    }).then(function (result) {
      $('[data-nominations]').hidden = true;
      showError('[data-selection-error]', '');
      form.hidden = true;
      $('[data-verify-email]').textContent = email;
      var debug = $('[data-debug-code]');
      debug.hidden = !result.debug_code;
      if (result.debug_code) debug.textContent = 'Локальный DEBUG-код: ' + result.debug_code;
      $('[data-verify]').hidden = false;
      $('#vote-code').focus();
    }).catch(function (error) {
      showError('[data-form-error]', error.message);
    }).finally(function () {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    });
  }

  function verifyBallot(event) {
    event.preventDefault();
    var form = event.currentTarget;
    if (!form.reportValidity()) return;
    var button = $('[type="submit"]', form);
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    showError('[data-verify-error]', '');
    api('/ballots/verify/', {
      method: 'POST',
      body: JSON.stringify({ email: state.email, code: $('#vote-code').value.trim() })
    }).then(function (result) {
      $('[data-verify]').hidden = true;
      $('[data-complete]').innerHTML = '<h2>Ваш голос принят</h2><p>Бюллетень <b>' + esc(result.ballot_id) + '</b> зарегистрирован. Спасибо за участие.</p><p>Итоги будут опубликованы после завершения голосования.</p><p><a class="btn btn-secondary" href="/promtour/#contest">Вернуться на сайт форума</a></p>';
      $('[data-complete]').hidden = false;
      $('[data-complete]').focus();
    }).catch(function (error) {
      showError('[data-verify-error]', error.message);
    }).finally(function () {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    window.hydrateIcons();
    window.ForumCaptcha.init('smart-captcha', 'captcha-token');
    $('[data-nominations]').addEventListener('change', function (event) {
      var card = event.target.closest('[data-nomination-card]');
      if (!card || !state.contest) return;
      showError('[data-selection-error]', '');
      if (event.target.matches('[data-nominee]') && event.target.checked) {
        var nominationId = event.target.getAttribute('data-nomination');
        var nomination = state.contest.nominations.find(function (item) { return item.id === nominationId; });
        var checked = $$('input[data-nomination="' + nominationId + '"]:checked');
        if (checked.length > nomination.max_selections) {
          event.target.checked = false;
          var message = nomination.max_selections === 1
            ? 'В номинации «' + nomination.title + '» можно выбрать только одного кандидата.'
            : 'В номинации «' + nomination.title + '» можно выбрать не более ' + nomination.max_selections + ' кандидатов.';
          showError('[data-selection-error]', message);
        } else {
          $('[data-skip-nomination]', card).checked = false;
        }
      }
      syncNomination(card);
      updateSelectionSummary();
    });
    $('[data-ballot-form]').addEventListener('submit', submitBallot);
    $('[data-verify-form]').addEventListener('submit', verifyBallot);
    document.addEventListener('click', function (event) {
      if (event.target.closest('[data-ballot-review]')) openBallotReview();
      var close = event.target.closest('[data-dialog-close]');
      if (close) close.closest('dialog').close();
      if (event.target.matches('dialog.contest-dialog')) event.target.close();
    });
    $('[data-ballot-dialog]').addEventListener('close', function () {
      if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
    });
    Promise.all([api(''), window.publicSubmissionsReady]).then(function (values) {
      var contest = values[0];
      if (!values[1]) contest.is_open = false;
      contest.nominations.forEach(function (nomination, index) { nomination.number = index + 1; });
      state.contest = contest;
      renderContest();
    }).catch(function (error) {
      showError('[data-api-error]', error.message);
      $('[data-contest-state]').textContent = 'Не удалось проверить статус голосования.';
      $('[data-nominations]').innerHTML = '<p role="alert">Не удалось загрузить номинации. Попробуйте обновить страницу позже.</p>';
    });
  });
})();
