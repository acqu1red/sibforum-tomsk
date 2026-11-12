(function () {
  'use strict';
  var API = '/api/v1/contests/promtour',
    esc = window.escapeHtml;
  var state = {
    contest: null,
    open: false,
    email: '',
    csrf: '',
    already: false,
    lastFocus: null,
    gallery: [],
    photoIndex: 0,
    complete: false
  };
  function $(s, r) {
    return (r || document).querySelector(s);
  }
  function $$(s, r) {
    return Array.prototype.slice.call((r || document).querySelectorAll(s));
  }
  function error(s, message) {
    var el = $(s);
    el.textContent = message || '';
    el.hidden = !message;
  }
  function api(path, options) {
    var initial = !options && window.consumeInitialData(API + path);
    if (initial) return initial.then(function (data) { return data || api(path, {}); });
    options = options || {};
    options.cache = 'no-store';
    options.headers = Object.assign({ Accept: 'application/json' }, options.headers || {});
    if (options.body) {
      options.headers['Content-Type'] = 'application/json';
      options.headers['X-CSRFToken'] = state.csrf;
    }
    return fetch(API + path, options)
      .then(function (r) {
        return r.json().then(function (d) {
          if (!r.ok) {
            var e = Error(d.message || 'Не удалось выполнить запрос.');
            e.code = d.error;
            throw e;
          }
          return d;
        });
      })
      .catch(function (e) {
        if (e instanceof TypeError) throw Error('Сервис временно недоступен. Попробуйте позже.');
        throw e;
      });
  }
  function canVote(c) {
    var now = Date.now();
    return (
      c.is_open &&
      (!c.voting_opens_at || now >= new Date(c.voting_opens_at).getTime()) &&
      (!c.voting_closes_at || now <= new Date(c.voting_closes_at).getTime())
    );
  }
  function selected() {
    var map = {};
    $$('input[data-nominee]:checked').forEach(function (el) {
      var id = el.dataset.nomination;
      (map[id] || (map[id] = [])).push(el.dataset.nominee);
    });
    return Object.keys(map).map(function (id) {
      return { nomination_id: id, nominee_ids: map[id] };
    });
  }
  function nominationFor(id) {
    return state.contest.nominations.find(function (n) {
      return n.id === id;
    });
  }
  function nomineeFor(id) {
    for (var i = 0; i < state.contest.nominations.length; i++) {
      var n = state.contest.nominations[i],
        candidate = n.nominees.find(function (c) {
          return c.id === id;
        });
      if (candidate) return { nomination: n, nominee: candidate };
    }
    return null;
  }
  function candidateHtml(n, c) {
    var logo = window.forumContent.safeLink(c.logo);
    return (
      '<article class="contest-candidate" data-edit="nominee:' + esc(c.id) + '"><label><input type="checkbox" data-nomination="' +
      esc(n.id) +
      '" data-nominee="' +
      esc(c.id) +
      '"><span class="contest-candidate-logo">' +
      (logo
        ? '<img src="' +
          esc(logo) +
          '" alt="" width="160" height="90" loading="lazy" decoding="async">'
        : '<span class="contest-logo-text">' + esc(c.name) + '</span>') +
      '</span>' +
      (logo ? '<b>' + esc(c.name) + '</b>' : '') +
      '<span class="contest-candidate-selection">Выбрать</span></label><button type="button" class="contest-details-button" data-nominee-info="' +
      esc(c.id) +
      '">' + esc(window.forumContent.text('contest_details', 'Описание')) + '<span class="visually-hidden">: ' +
      esc(c.name) +
      '</span></button></article>'
    );
  }
  function render() {
    var previous = selected(),
      opened = $$('[data-nomination-card][open]').map(function (el) {
        return el.dataset.nominationCard;
      });
    var c = state.contest;
    state.open = state.enabled && canVote(c) && !state.already && !state.complete;
    document.title = c.title + ' — онлайн-голосование';
    $('#contest-title').textContent = c.title;
    $('[data-contest-description]').textContent = c.description || '';
    $('[data-contest-rules]').textContent = c.rules_text || '';
    $('[data-contest-rules]').hidden = !c.rules_text;
    $('[data-contest-state]').textContent = state.already
      ? 'Ваш бюллетень уже принят. Повторное голосование ограничено.'
      : state.open
        ? 'Голосование открыто. Выберите проекты и отправьте бюллетень.'
        : 'Голосование закрыто или ещё не началось. Номинации и проекты доступны для просмотра.';
    $('[data-nominations]').innerHTML = c.nominations
      .map(function (n, i) {
        var limit =
          'Выберите не более ' +
          n.max_selections +
          ' ' +
          window.plural(n.max_selections, ['участника', 'участников', 'участников']);
        return (
          '<details class="promtour-nomination" id="nomination-' +
          esc(n.id) +
          '" data-nomination-card="' +
          esc(n.id) +
          '"><summary><span class="promtour-nomination-number">' +
          String(i + 1).padStart(2, '0') +
          '</span><span><b>' +
          esc(n.title) +
          '</b><small>' +
          n.nominees.length +
          ' ' +
          window.plural(n.nominees.length, ['участник', 'участника', 'участников']) +
          '</small></span></summary><div class="promtour-nomination-body"><p class="contest-nomination-limit">' +
          limit +
          '</p>' +
          (n.selection_hint
            ? '<p class="contest-selection-hint">' + esc(n.selection_hint) + '</p>'
            : '') +
          (n.description ? '<p>' + esc(n.description) + '</p>' : '') +
          '<div class="contest-candidates">' +
          n.nominees
            .map(function (c) {
              return candidateHtml(n, c);
            })
            .join('') +
          '</div></div></details>'
        );
      })
      .join('');
    previous.forEach(function (s) {
      var n = nominationFor(s.nomination_id);
      if (!n) return;
      s.nominee_ids.slice(0, n.max_selections).forEach(function (id) {
        var el = $('input[data-nominee="' + id + '"]');
        if (el) el.checked = true;
      });
    });
    $$('[data-nomination-card]').forEach(function (el) {
      el.open = opened.indexOf(el.dataset.nominationCard) !== -1;
    });
    $$('[data-nominee]').forEach(function (el) {
      el.disabled = !state.open;
    });
    $('[data-ballot-form]').hidden = !state.open;
    var emailMode = c.voting_mode === 'email';
    $('[data-email-field]').hidden = !emailMode;
    $('[data-email-privacy]').hidden = !emailMode;
    $('#vote-email').required = emailMode;
    $('[data-ballot-intro]').textContent = emailMode
      ? 'Проверьте выбор и укажите email. Мы отправим код для подтверждения.'
      : 'Проверьте выбранные проекты. После отправки бюллетень будет принят сразу; повторное голосование с этой сети и браузера ограничено.';
    $('[data-submit-ballot]').textContent = emailMode
      ? 'Получить код подтверждения'
      : 'Отправить голос';
    updateSummary();
    openHash();
  }
  function updateSummary() {
    var choices = selected(),
      count = choices.reduce(function (a, s) {
        return a + s.nominee_ids.length;
      }, 0);
    $('[data-selection-summary]').textContent = count
      ? 'Выбрано: ' +
        count +
        ' ' +
        window.plural(count, ['участник', 'участника', 'участников']) +
        ' в ' +
        choices.length +
        ' ' +
        window.plural(choices.length, ['номинации', 'номинациях', 'номинациях']) +
        '.'
      : 'Выберите хотя бы одного участника в любой знакомой номинации.';
    $$('[data-nominee]').forEach(function (el) {
      var card = el.closest('.contest-candidate');
      card.classList.toggle('is-selected', el.checked);
      $('.contest-candidate-selection', card).textContent = el.checked ? 'Выбрано' : 'Выбрать';
    });
  }
  function openHash() {
    if (!/^#nomination-[a-f0-9-]+$/.test(location.hash)) return;
    var el = document.getElementById(location.hash.slice(1));
    if (el) {
      el.open = true;
      requestAnimationFrame(function () {
        el.scrollIntoView({ block: 'start' });
      });
    }
  }
  function showDialog(selector) {
    state.lastFocus = document.activeElement;
    $(selector).showModal();
  }
  function openCandidate(id) {
    var pair = nomineeFor(id);
    if (!pair) return;
    var c = pair.nominee,
      n = pair.nomination,
      logo = window.forumContent.safeLink(c.logo),
      site = window.forumContent.safeLink(c.website_url);
    state.gallery = c.photos || [];
    state.photoIndex = 0;
    $('[data-nominee-dialog-content]').innerHTML =
      '<p class="contest-dialog-nomination">' +
      esc(n.title) +
      '</p><h2 id="nominee-dialog-title">' +
      esc(c.name) +
      '</h2>' +
      (logo
        ? '<img class="contest-dialog-logo" src="' +
          esc(logo) +
          '" alt="" width="180" height="100">'
        : '') +
      (c.description
        ? '<p class="contest-project-description">' + esc(c.description) + '</p>'
        : '<p>' + esc(window.forumContent.text('contest_empty_description', 'Описание готовит организатор.')) + '</p>') +
      (state.gallery.length
        ? '<figure class="contest-gallery"><img data-gallery-image alt="" width="800" height="560"><figcaption data-gallery-caption></figcaption></figure><div class="contest-gallery-controls"><button type="button" data-gallery-step="-1" aria-label="Предыдущая фотография">Назад</button><span data-gallery-count aria-live="polite"></span><button type="button" data-gallery-step="1" aria-label="Следующая фотография">Далее</button></div>'
        : '') +
      (site
        ? '<p><a class="btn btn-secondary" href="' +
          esc(site) +
          '" target="_blank" rel="noopener noreferrer">' + esc(window.forumContent.text('contest_website', 'Сайт организации')) + '<span class="visually-hidden"> (откроется в новой вкладке)</span></a></p>'
        : '');
    showDialog('[data-nominee-dialog]');
    renderGallery();
  }
  function renderGallery() {
    if (!state.gallery.length) return;
    var photo = state.gallery[state.photoIndex];
    $('[data-gallery-image]').src = window.forumContent.safeLink(photo.url);
    $('[data-gallery-image]').alt = photo.caption || 'Фотография участника конкурса';
    $('[data-gallery-caption]').textContent = photo.caption || '';
    $('[data-gallery-count]').textContent = state.photoIndex + 1 + ' из ' + state.gallery.length;
    $$('[data-gallery-step]').forEach(function (b) {
      b.disabled = state.gallery.length < 2;
    });
  }
  function review() {
    var choices = selected();
    var html = '<h2 id="ballot-dialog-title">Ваш выбор</h2><div class="promtour-ballot-review">';
    choices.forEach(function (s) {
      var n = nominationFor(s.nomination_id);
      html +=
        '<section><h3>' +
        esc(n.title) +
        '</h3><ul>' +
        s.nominee_ids
          .map(function (id) {
            var p = nomineeFor(id);
            return p ? '<li>' + esc(p.nominee.name) + '</li>' : '';
          })
          .join('') +
        '</ul></section>';
    });
    html +=
      '</div><p>' +
      (choices.length
        ? 'Голос ещё не отправлен. Закройте это окно и нажмите кнопку отправки бюллетеня.'
        : 'Пока нет выбранных проектов.') +
      '</p><button type="button" class="btn btn-secondary" data-dialog-close>Вернуться к выбору</button>';
    $('[data-ballot-dialog-content]').innerHTML = html;
    showDialog('[data-ballot-dialog]');
  }
  function complete(result) {
    state.complete = true;
    state.already = true;
    $('[data-ballot-form]').hidden = true;
    $('[data-verify]').hidden = true;
    $$('[data-nominee]').forEach(function (el) {
      el.disabled = true;
    });
    $('[data-complete]').innerHTML =
      '<h2>Ваш голос принят</h2><p>Спасибо за участие. Бюллетень <b>' +
      esc(result.ballot_id) +
      '</b> сохранён.</p><p>Итоги появятся после публикации организатором.</p><a class="btn btn-secondary" href="/#contest">Вернуться на сайт форума</a>';
    $('[data-complete]').hidden = false;
    $('[data-complete]').focus();
    $('[data-contest-state]').textContent = 'Ваш бюллетень принят. Спасибо за участие.';
  }
  function submit(event) {
    event.preventDefault();
    error('[data-form-error]', '');
    if (!state.open) return;
    var choices = selected();
    if (!choices.length) {
      error('[data-form-error]', 'Выберите хотя бы одного участника.');
      return;
    }
    if (!event.currentTarget.reportValidity()) return;
    var button = $('[data-submit-ballot]');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    state.email = $('#vote-email').value.trim();
    api('/ballots/', {
      method: 'POST',
      body: JSON.stringify({
        email: state.email,
        selections: choices,
        captcha_token: $('#captcha-token').value
      })
    })
      .then(function (result) {
        if (result.status === 'submitted') {
          complete(result);
          return;
        }
        $('[data-ballot-form]').hidden = true;
        $('[data-verify-email]').textContent = state.email;
        $('[data-verify]').hidden = false;
        var debug = $('[data-debug-code]');
        debug.hidden = !result.debug_code;
        if (result.debug_code) debug.textContent = 'Локальный тестовый код: ' + result.debug_code;
        $('#vote-code').focus();
      })
      .catch(function (e) {
        error('[data-form-error]', e.message);
        if (e.code === 'already_voted') {
          state.already = true;
          $$('[data-nominee]').forEach(function (el) {
            el.disabled = true;
          });
        }
      })
      .finally(function () {
        button.disabled = false;
        button.removeAttribute('aria-busy');
      });
  }
  function verify(event) {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    var button = $('button', event.currentTarget);
    button.disabled = true;
    error('[data-verify-error]', '');
    api('/ballots/verify/', {
      method: 'POST',
      body: JSON.stringify({ email: state.email, code: $('#vote-code').value.trim() })
    })
      .then(complete)
      .catch(function (e) {
        error('[data-verify-error]', e.message);
      })
      .finally(function () {
        button.disabled = false;
      });
  }
  function load() {
    return Promise.all([
      api('/'),
      api('/voter-session/'),
      window.publicVotingReady,
      (window.consumeInitialData('/api/v1/forums/promtour/program/') || fetch('/api/v1/forums/promtour/program/', { cache: 'no-store' })).then(function (r) {
        if (r && typeof r.json !== 'function') return r;
        if (!r || !r.ok) throw Error('Не удалось загрузить страницу форума.');
        return r.json();
      })
    ]).then(function (values) {
      state.contest = values[0];
      state.revision = values[3].revision;
      state.csrf = values[1].csrf_token;
      state.already = values[1].already_voted;
      state.enabled = values[2];
      window.forumContent.apply(values[3].page);
      render();
      if (state.open && state.contest.voting_mode === 'email')
        window.ForumCaptcha.init('smart-captcha', 'captcha-token');
    });
  }
  document.addEventListener('DOMContentLoaded', function () {
    window.hydrateIcons();
    $('[data-nominations]').addEventListener('change', function (event) {
      var input = event.target;
      if (!input.matches('[data-nominee]')) return;
      error('[data-selection-error]', '');
      var n = nominationFor(input.dataset.nomination);
      if (
        input.checked &&
        $$('input[data-nomination="' + n.id + '"]:checked').length > n.max_selections
      ) {
        input.checked = false;
        error(
          '[data-selection-error]',
          'В номинации «' +
            n.title +
            '» можно выбрать не более ' +
            n.max_selections +
            ' участников.'
        );
      }
      updateSummary();
    });
    $('[data-ballot-form]').addEventListener('submit', submit);
    $('[data-verify-form]').addEventListener('submit', verify);
    document.addEventListener('click', function (event) {
      var info = event.target.closest('[data-nominee-info]');
      if (info) openCandidate(info.dataset.nomineeInfo);
      if (event.target.closest('[data-ballot-review]')) review();
      var step = event.target.closest('[data-gallery-step]');
      if (step) {
        state.photoIndex =
          (state.photoIndex + Number(step.dataset.galleryStep) + state.gallery.length) %
          state.gallery.length;
        renderGallery();
      }
      var close = event.target.closest('[data-dialog-close]');
      if (close) close.closest('dialog').close();
      if (event.target.matches('dialog.contest-dialog')) event.target.close();
    });
    $$('dialog').forEach(function (d) {
      d.addEventListener('close', function () {
        if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
      });
    });
    window.addEventListener('hashchange', openHash);
    load()
      .then(function () {
        window.forumContent.watch(load, state.revision);
      })
      .catch(function (e) {
        error('[data-api-error]', e.message);
        $('[data-contest-state]').textContent = 'Не удалось проверить статус голосования.';
        $('[data-nominations]').innerHTML =
          '<p role="alert">Не удалось загрузить номинации. Обновите страницу позже.</p>';
      });
  });
})();
