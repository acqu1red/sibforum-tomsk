(function () {
  'use strict';

  var body = document.body;
  var slug = body.getAttribute('data-forum-slug');
  var API = '/api/v1';
  var content = window.PROMTOUR_CONTENT;
  var esc = function (value) { return window.escapeHtml(value == null ? '' : String(value)); };
  var state = {
    program: null,
    speakers: null,
    selected: {},
    email: '',
    token: new URLSearchParams(location.search).get('t') || '',
    routeEvents: {},
    exchangeEvents: [],
    lastFocus: null
  };
  var STATUS = {
    confirmed: 'Подтверждено', pending_review: 'На рассмотрении', approved: 'Одобрено',
    rejected: 'Отклонено', cancelled_by_user: 'Отменено участником', cancelled_by_admin: 'Отменено администратором'
  };
  var POLICY = {
    auto: 'Подтверждение после email', moderated: 'Заявка на модерацию', external: 'Внешняя регистрация',
    none: 'Без регистрации', invite_only: 'По приглашению'
  };

  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
  function speakerById(id) {
    return (state.speakers || content.speakers).find(function (speaker) { return speaker.id === id; });
  }
  function formatDay(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return value || '';
    return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(value + 'T00:00:00Z'));
  }
  function formatPrice(value) {
    var price = Number(value);
    return value !== null && value !== '' && Number.isFinite(price) ? new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(price) + ' ₽' : 'Стоимость и условия уточняются куратором';
  }
  function routeNumberFor(event) {
    var match = (event.slug || '').match(/^route-(\d+)$/) || (event.title || '').match(/маршрут\s*[№#]?\s*(\d+)/i);
    var number = match ? Number(match[1]) : 0;
    if (!number) Object.keys(state.routeEvents).some(function (key) {
      if (state.routeEvents[key].id === event.id) { number = Number(key); return true; }
      return false;
    });
    return number;
  }
  function staticEventFor(slug) {
    var found = null;
    content.days.forEach(function (day) {
      day.events.forEach(function (event) { if (event.id === slug) found = event; });
    });
    return found;
  }
  function speakerEventName(event) {
    return typeof event === 'string' ? event : event.title + (event.role ? ' · ' + event.role : '');
  }
  function safeHttpsUrl(value) {
    try {
      var url = new URL(value);
      return url.protocol === 'https:' ? url.href : '';
    } catch (error) {
      return '';
    }
  }
  function eventById(id) {
    var found = null;
    if (!state.program) return null;
    state.program.days.forEach(function (day) {
      day.events.forEach(function (event) { if (event.id === id) found = event; });
    });
    return found;
  }
  function dayById(id) {
    var found = null;
    if (!state.program) return null;
    state.program.days.forEach(function (day) {
      day.events.forEach(function (event) { if (event.id === id) found = day; });
    });
    return found;
  }
  function overlaps(a, b) { return a.start_time < b.end_time && b.start_time < a.end_time; }
  function selectedIds() { return Object.keys(state.selected); }
  function showError(selector, message) {
    var box = $(selector);
    if (!box) return;
    box.textContent = message || '';
    box.hidden = !message;
  }
  function validExternalUrl(value) {
    if (!value || /^https:\/\/(disk\.yandex\.ru|leader-id\.ru)\/?$/i.test(value)) return '';
    try {
      var url = new URL(value);
      return url.protocol === 'https:' ? url.href : '';
    } catch (error) {
      return '';
    }
  }
  function api(path, options) {
    options = options || {};
    options.headers = Object.assign({ 'Accept': 'application/json' }, options.headers || {});
    if (options.body) options.headers['Content-Type'] = 'application/json';
    return fetch(API + path, options).then(function (response) {
      return response.json().catch(function () {
        throw new Error('Сервер вернул некорректный ответ.');
      }).then(function (data) {
        if (!response.ok) throw new Error(data.message || 'Не удалось выполнить запрос.');
        return data;
      });
    }).catch(function (error) {
      if (error instanceof TypeError) throw new Error('Сервис регистрации недоступен. Попробуйте позже или напишите на mail@tomsktpp.ru.');
      throw error;
    });
  }

  function speakerButtons(links) {
    if (!links || !links.length) return '';
    return '<div class="promtour-event-speakers"><span>Спикеры и ведущие</span><div>' + links.map(function (link) {
      var id = typeof link === 'string' ? link : link.id;
      var speaker = speakerById(id);
      var role = typeof link === 'object' && link.role && link.role !== 'Спикер' ? ' · ' + link.role : '';
      return speaker ? '<button type="button" data-speaker-id="' + esc(id) + '">' + esc(speaker.name + role) + '</button>' : '';
    }).join('') + '</div></div>';
  }

  function programDays() {
    if (!state.program) return content.days;
    return state.program.days.map(function (day) {
      var hasSummary = day.events.some(function (event) { return event.slug === 'routes'; });
      var routeCount = day.events.filter(function (event) { return event.kind === 'route'; }).length;
      var events = day.events.filter(function (event) { return !(hasSummary && event.kind === 'route'); }).map(function (event) {
        var fallback = staticEventFor(event.slug);
        var anchors = { routes: ['routes', 'Выбрать маршрут'], seminar: ['speakers', 'Спикеры и темы'], exchange: ['exchange', 'О бирже и лотах'], awards: ['contest', 'Номинации конкурса'] };
        var anchor = anchors[event.slug] || (fallback && fallback.anchor ? [fallback.anchor, fallback.anchorLabel] : null);
        var externalUrl = safeHttpsUrl(event.external_url);
        var externalLink = externalUrl && validExternalUrl(externalUrl)
          ? '<a class="link-arrow" href="' + esc(externalUrl) + '" target="_blank" rel="noopener noreferrer">Внешняя регистрация<span class="visually-hidden"> (откроется в новой вкладке)</span> <span aria-hidden="true">→</span></a>'
          : (event.registration_policy === 'external' ? '<p class="promtour-event-meta">Ссылка на страницу внешней регистрации уточняется организатором.</p>' : '');
        var annotation = event.annotation || (fallback ? fallback.annotation : '');
        if (event.slug === 'routes' && routeCount) annotation = routeCount + ' ' + window.plural(routeCount, ['маршрут', 'маршрута', 'маршрутов']) + ' с отправлением от Союза «ТПП Томской области» в 09:15. Можно выбрать только один маршрут.';
        return {
          id: event.slug || event.id,
          time: event.start_time + '–' + event.end_time,
          title: event.title,
          annotation: annotation,
          description: event.has_details ? event.description : '',
          venue: event.venue ? event.venue.name + ' · ' + event.venue.address : '',
          speakers: event.speakers || (fallback ? fallback.speakerIds : []),
          extra: (anchor ? '<a class="link-arrow" href="#' + esc(anchor[0]) + '">' + esc(anchor[1]) + ' <span aria-hidden="true">→</span></a>' : '') + externalLink
        };
      });
      var mainVenue = (day.events.find(function (event) { return event.slug === 'opening'; }) || day.events[0] || {}).venue;
      return { title: day.title, date: formatDay(day.date), venue: mainVenue ? mainVenue.name + ' · ' + mainVenue.address : '', events: events };
    });
  }

  function renderProgram() {
    $('[data-program-days]').innerHTML = programDays().map(function (day) {
      return '<section class="promtour-day"><div class="promtour-day-head"><div><h3>' + esc(day.title) + '</h3><p>' + esc(day.date) + '</p></div>' +
        (day.venue ? '<p class="promtour-day-venue">' + esc(day.venue) + '</p>' : '') + '</div>' +
        '<div class="promtour-timeline">' + day.events.map(function (event) {
          var extra = speakerButtons(event.speakers || event.speakerIds) + (event.description ? '<p>' + esc(event.description) + '</p>' : '') + (event.extra || '');
          if (event.anchor) extra += '<a class="link-arrow" href="#' + esc(event.anchor) + '">' + esc(event.anchorLabel) + ' <span aria-hidden="true">→</span></a>';
          if (event.externalUrl) extra += '<p class="promtour-event-meta">Ссылка на страницу внешней регистрации уточняется организатором.</p>';
          return '<article class="promtour-event" id="event-' + esc(event.id) + '">' +
            '<time class="promtour-event-time">' + esc(event.time) + '</time>' +
            '<div class="promtour-event-body"><h4>' + esc(event.title) + '</h4><p>' + esc(event.annotation) + '</p>' +
            (event.venue ? '<p class="promtour-event-meta">' + esc(event.venue) + '</p>' : '') +
            (extra ? '<details class="promtour-event-details"><summary>Подробнее</summary><div>' + extra + '</div></details>' : '') +
            '</div></article>';
        }).join('') + '</div></section>';
    }).join('');
  }

  function renderRoutes() {
    var routes = content.routes;
    if (state.program) {
      routes = [];
      state.program.days.forEach(function (day) {
        day.events.forEach(function (event) { if (event.kind === 'route') routes.push(event); });
      });
    }
    $('[data-routes]').innerHTML = routes.map(function (route, index) {
      var number = route.number || routeNumberFor(route) || index + 1;
      var day = state.program ? dayById(route.id) : null;
      var enterprises = route.enterprises || [];
      return '<article class="promtour-route" data-route-number="' + number + '">' +
        '<div class="promtour-route-top"><span class="promtour-route-number">' + String(number).padStart(2, '0') + '</span><span class="promtour-paid">' + (route.is_paid === false ? 'Условия уточняются' : 'Платно') + '</span></div>' +
        '<h3>' + esc(route.title) + '</h3>' +
        (enterprises.length ? '<ul class="promtour-enterprises">' + enterprises.map(function (enterprise) {
          return '<li><strong>' + esc(enterprise.name) + '</strong><span>' + esc(enterprise.description) + '</span></li>';
        }).join('') + '</ul>' : '<p>Состав предприятий уточняется организатором.</p>') +
        '<div class="promtour-route-facts"><p><b>Дата:</b> ' + esc(day ? formatDay(day.date) : '23.11.2026') + '</p><p><b>Отправление:</b> ' + esc(route.venue ? route.venue.name + ', ' + route.venue.address : 'от ТПП в 09:15') + ' в ' + esc(route.start_time || '09:15') + '</p><p><b>Стоимость:</b> ' + esc(formatPrice(route.price === undefined ? 2500 : route.price)) + '</p><p><b>Оплата:</b> ' + esc(route.payment_note || 'После звонка куратора. Заявка не является оплатой.') + '</p><p><b>Статус:</b> ' + esc(POLICY[route.registration_policy] || 'заявка на рассмотрении') + '</p></div>' +
        '<p class="promtour-route-rule">Можно выбрать только один маршрут</p>' +
        '<button class="btn btn-secondary btn-block" type="button" data-route-select="' + number + '" disabled>Проверяем запись…</button>' +
        '</article>';
    }).join('');
  }

  function speakerPhoto(speaker, className) {
    if (speaker.photo) {
      var responsive = speaker.photo.indexOf('/img/promtour/speakers/') === 0 && /\.webp$/.test(speaker.photo);
      var stem = speaker.photo.replace(/\.webp$/, '');
      var sources = responsive ? ' srcset="' + esc(stem) + '-320.webp 320w, ' + esc(stem) + '-640.webp 640w" sizes="(min-width: 1024px) 240px, (min-width: 560px) 45vw, 90vw"' : '';
      return '<img class="' + className + '" src="' + esc(responsive ? stem + '-640.webp' : speaker.photo) + '"' + sources + ' alt="' + esc(speaker.name) + '" loading="lazy" decoding="async" width="320" height="360">';
    }
    var initials = speaker.name.split(' ').slice(0, 2).map(function (part) { return part.charAt(0); }).join('');
    return '<span class="' + className + ' promtour-photo-placeholder" role="img" aria-label="Фотография не предоставлена"><b>' + esc(initials) + '</b><small>Фото не предоставлено</small></span>';
  }

  function renderSpeakers() {
    var speakers = state.speakers || content.speakers;
    $('[data-speakers]').innerHTML = speakers.map(function (speaker) {
      var events = (speaker.events || []).map(speakerEventName);
      var search = [speaker.name, speaker.position, speaker.topic].concat(events).join(' ').toLowerCase();
      return '<article class="promtour-speaker" data-speaker-card="' + esc(speaker.id) + '" data-search="' + esc(search) + '">' +
        '<button class="promtour-speaker-photo" type="button" data-speaker-id="' + esc(speaker.id) + '" aria-label="Подробнее: ' + esc(speaker.name) + '">' + speakerPhoto(speaker, 'promtour-speaker-image') + '</button>' +
        '<div class="promtour-speaker-body"><h3>' + esc(speaker.name) + '</h3>' +
        '<p class="promtour-speaker-position">' + esc(speaker.position) + '</p>' +
        (speaker.topic ? '<p class="promtour-speaker-topic"><span>Тема</span>' + esc(speaker.topic) + '</p>' : '') +
        '<p class="promtour-event-meta">' + esc(events.join(' · ')) + '</p>' +
        '<button class="btn btn-secondary btn-sm" type="button" data-speaker-id="' + esc(speaker.id) + '">Подробнее</button></div></article>';
    }).join('') || '<p class="promtour-empty">Список спикеров уточняется организатором.</p>';
  }

  function openSpeaker(id) {
    var speaker = speakerById(id);
    if (!speaker) return;
    state.lastFocus = document.activeElement;
    var events = (speaker.events || []).map(speakerEventName);
    $('[data-speaker-dialog-content]').innerHTML = '<div class="promtour-dialog-person">' + speakerPhoto(speaker, 'promtour-dialog-photo') +
      '<div><p class="eyebrow">Участник форума</p><h2 id="speaker-dialog-title">' + esc(speaker.name) + '</h2></div></div>' +
      '<h3>Должность и регалии</h3><p>' + esc(speaker.position) + '</p>' +
      (speaker.topic ? '<h3>Тема</h3><p>' + esc(speaker.topic) + '</p>' : '') +
      (events.length ? '<h3>Мероприятия и роль</h3><ul>' + events.map(function (event) { return '<li>' + esc(event) + '</li>'; }).join('') + '</ul>' : '');
    $('[data-speaker-dialog]').showModal();
  }

  function renderNominations() {
    if (!content.nominations.length) {
      $('[data-nominations]').innerHTML = '<p>Загружаем номинации…</p>';
      return;
    }
    var primary = content.nominations.filter(function (nomination) { return Number(nomination.visualGroup) === 1; });
    var rest = content.nominations.filter(function (nomination) { return Number(nomination.visualGroup) !== 1; });
    function nominationHtml(nomination) {
      return '<article class="promtour-nomination promtour-nomination-static"><span class="promtour-nomination-number">' + String(nomination.number).padStart(2, '0') + '</span>' +
        '<div><h3>' + esc(nomination.title) + '</h3><p>' + nomination.nomineeCount + ' ' + window.plural(nomination.nomineeCount, ['номинант', 'номинанта', 'номинантов']) + '</p></div></article>';
    }
    var html = '';
    if (primary.length) html += '<div class="promtour-nomination-group"><h3>Бренд, маршрут и музей</h3><p>Три самостоятельные номинации.</p>' + primary.map(nominationHtml).join('') + '</div>';
    $('[data-nominations]').innerHTML = html + rest.map(nominationHtml).join('');
  }

  function contentEventFor(event) {
    var backendEvent = eventById(event.id) || event;
    if (backendEvent.kind === 'route' || routeNumberFor(backendEvent)) return backendEvent;
    var id = backendEvent.slug || '';
    if (backendEvent.kind === 'seminar') id = 'seminar';
    if (backendEvent.kind === 'exchange') id = 'exchange';
    if (backendEvent.kind === 'plenary') id = 'opening';
    if (backendEvent.kind === 'masterclass') id = 'masterclass';
    if (backendEvent.kind === 'session') {
      if (/стратег/i.test(backendEvent.title)) id = 'strategy';
      if (/квиз/i.test(backendEvent.title)) id = 'quiz';
      if (/кругл/i.test(backendEvent.title)) id = 'roundtable';
    }
    return staticEventFor(id);
  }

  function registrationView(event) {
    var backendEvent = eventById(event.id) || event;
    var view = contentEventFor(backendEvent);
    var day = dayById(backendEvent.id);
    var route = backendEvent.kind === 'route' || !!routeNumberFor(backendEvent);
    var enterprises = backendEvent.enterprises || (view ? view.enterprises : null);
    return {
      title: backendEvent.title || (view && view.title) || '',
      time: backendEvent.start_time ? backendEvent.start_time + '–' + backendEvent.end_time : (view && view.time) || '',
      day: day ? formatDay(day.date) : (backendEvent.day ? formatDay(backendEvent.day) : backendEvent.day_title || ''),
      annotation: backendEvent.annotation || (enterprises ? enterprises.map(function (item) { return item.name; }).join(' · ') : (view && view.annotation) || ''),
      paid: backendEvent.is_paid !== undefined ? !!backendEvent.is_paid : route,
      price: backendEvent.price !== undefined ? backendEvent.price : (route ? 2500 : null),
      payment_note: backendEvent.payment_note || 'Оплата после звонка куратора. Заявка не является оплатой.',
      enterprises: enterprises || []
    };
  }

  function realLots(event) {
    return (event.lots || []).filter(function (lot) { return !!validExternalUrl(lot.technical_url); });
  }

  function renderExchange() {
    var allLots = [];
    state.exchangeEvents.forEach(function (event) {
      realLots(event).forEach(function (lot) { allLots.push({ event: event, lot: lot }); });
    });
    $('[data-exchange-lots]').innerHTML = allLots.length ? '<div class="promtour-public-lots">' + allLots.map(function (item) {
      var lot = item.lot;
      return '<article class="promtour-public-lot"><span>Лот ' + esc(lot.number) + '</span><h4>' + esc(lot.title) + '</h4>' +
        (lot.customer_name ? '<p>' + esc(lot.customer_name) + '</p>' : '') +
        '<a href="' + esc(validExternalUrl(lot.technical_url)) + '" target="_blank" rel="noopener noreferrer">Технические материалы <span class="visually-hidden">(откроется в новой вкладке)</span></a></article>';
    }).join('') + '</div>' : '<div class="promtour-dark-note"><p>Лоты и ссылки на технические задания пока не опубликованы. Они появятся здесь после загрузки организатором.</p><p>До публикации лотов выбор биржи в регистрации недоступен: отправить заявку без технического запроса нельзя.</p></div>';
  }

  function lotsHtml(event) {
    if (event.kind !== 'exchange') return '';
    var lots = realLots(event);
    if (!lots.length) return '<p class="promtour-unavailable">Выбор станет доступен после публикации лотов и технических материалов.</p>';
    return '<fieldset class="promtour-lots"><legend>Лоты для переговоров — выберите от ' + event.min_lot_selections + (event.max_lot_selections ? ' до ' + event.max_lot_selections : '') + '</legend>' + lots.map(function (lot) {
      return '<div class="promtour-lot"><label><input type="checkbox" data-lot="' + esc(lot.id) + '" data-event="' + esc(event.id) + '"><span><b>Лот ' + esc(lot.number) + ':</b> ' + esc(lot.title) + (lot.customer_name ? ' · ' + esc(lot.customer_name) : '') + '</span></label>' +
        '<a href="' + esc(validExternalUrl(lot.technical_url)) + '" target="_blank" rel="noopener noreferrer">Технические материалы<span class="visually-hidden"> (откроется в новой вкладке)</span></a></div>';
    }).join('') + '</fieldset>';
  }

  function registrationEventHtml(event) {
    var view = registrationView(event);
    var unavailable = event.kind === 'exchange' && !realLots(event).length;
    return '<article class="promtour-registration-event" data-event-card="' + esc(event.id) + '">' +
      '<label class="promtour-event-head"><input type="checkbox" data-event-select="' + esc(event.id) + '"' + (unavailable ? ' disabled' : '') + '><span><span class="promtour-event-title">' + esc(view.title) + '</span><span class="promtour-event-time">' + esc(view.day) + ' · ' + esc(view.time) + '</span></span></label>' +
      '<span class="promtour-policy">' + esc(POLICY[event.registration_policy] || '') + '</span>' +
      (view.paid ? '<div class="promtour-price"><strong>Платное участие</strong><small>Стоимость: ' + esc(formatPrice(view.price)) + '. ' + esc(view.payment_note) + '</small></div>' : '') +
      (event.kind === 'route' ? '<p class="promtour-event-meta">Можно выбрать только один маршрут</p>' : '') + lotsHtml(event) + '</article>';
  }

  function registrationGroup(title, note, events) {
    if (!events.length) return '';
    return '<section class="promtour-registration-group"><h3>' + esc(title) + '</h3>' + (note ? '<p>' + esc(note) + '</p>' : '') + '<div class="promtour-registration-grid">' + events.map(registrationEventHtml).join('') + '</div></section>';
  }

  function renderRegistration() {
    if (state.submissionsEnabled === false) {
      $('[data-registration-status]').textContent = 'Приём заявок временно недоступен. Программа и описание маршрутов доступны для просмотра.';
      $('[data-registration-status]').hidden = false;
      $('[data-registration-form]').hidden = true;
      $$('[data-route-select]').forEach(function (button) {
        button.disabled = true;
        button.textContent = 'Приём заявок временно недоступен';
      });
      return;
    }
    var routeEvents = Object.keys(state.routeEvents).sort(function (a, b) { return Number(a) - Number(b); }).map(function (number) { return state.routeEvents[number]; });
    var routeDay = state.program.days.find(function (day) { return day.events.some(function (event) { return event.kind === 'route'; }); });
    var businessDay = state.program.days.find(function (day) { return day.events.some(function (event) { return event.kind === 'plenary'; }); }) || state.program.days[1];
    var otherEvents = businessDay ? businessDay.events.filter(function (event) {
      return event.registration_policy === 'auto' || event.registration_policy === 'moderated';
    }) : [];
    var plenary = otherEvents.filter(function (event) { return event.kind === 'plenary'; });
    var morning = otherEvents.filter(function (event) { return event.kind === 'seminar' || event.kind === 'exchange'; });
    var afternoon = otherEvents.filter(function (event) { return event.kind === 'session' || event.kind === 'roundtable' || event.kind === 'quiz'; });
    $('[data-registration-events]').innerHTML = registrationGroup(routeDay ? formatDay(routeDay.date) + ' · экскурсии' : 'Экскурсии', 'Только один платный маршрут. Заявка проходит модерацию.', routeEvents) +
      registrationGroup(businessDay ? formatDay(businessDay.date) + ' · общая часть' : 'Общая часть', 'Обычное событие подтверждается после проверки email.', plenary) +
      registrationGroup(businessDay ? formatDay(businessDay.date) + ' · до обеда' : 'До обеда', 'Семинар или биржа — не более одного события.', morning) +
      registrationGroup(businessDay ? formatDay(businessDay.date) + ' · после обеда' : 'После обеда', 'Не более одного параллельного мероприятия.', afternoon);
    $('[data-registration-status]').hidden = true;
    $('[data-registration-form]').hidden = !!state.token;
    $$('[data-route-select]').forEach(function (button) {
      var number = button.getAttribute('data-route-select');
      var available = !!state.routeEvents[number] && !state.token;
      button.disabled = !available;
      button.textContent = state.routeEvents[number] ? (state.token ? 'Заявка уже оформлена' : 'Выбрать маршрут') : 'Онлайн-запись пока недоступна';
    });
    syncSelection();
  }

  function syncSelection() {
    $$('[data-event-card]').forEach(function (card) {
      var id = card.getAttribute('data-event-card');
      card.classList.toggle('is-selected', !!state.selected[id]);
      var checkbox = $('[data-event-select]', card);
      if (checkbox) checkbox.checked = !!state.selected[id];
      $$('[data-lot]', card).forEach(function (lot) {
        lot.checked = !!(state.selected[id] && state.selected[id].indexOf(lot.getAttribute('data-lot')) !== -1);
      });
    });
    var ids = selectedIds();
    var html = ids.length ? '<p><b>Выбрано событий: ' + ids.length + '</b></p>' + ids.map(function (id) {
      var event = eventById(id);
      var view = registrationView(event);
      var lotCount = state.selected[id].length;
      return '<p>• ' + esc(view.title) + (lotCount ? ' · лотов: ' + lotCount : '') + '</p>';
    }).join('') : '<p>Пока ничего не выбрано. Отметьте события выше.</p>';
    $('[data-selection-summary]').innerHTML = html;
  }

  function toggleEvent(id, checked) {
    var event = eventById(id);
    if (!event) return;
    if (checked && event.kind === 'exchange' && !realLots(event).length) return;
    if (!checked) {
      delete state.selected[id];
      syncSelection();
      return;
    }
    if (event.kind === 'route') {
      Object.keys(state.routeEvents).forEach(function (number) {
        var otherId = state.routeEvents[number].id;
        if (otherId !== id) delete state.selected[otherId];
      });
    }
    state.program.days.forEach(function (day) {
      day.choice_groups.forEach(function (group) {
        if (group.event_ids.indexOf(id) === -1) return;
        group.event_ids.forEach(function (otherId) {
          if (otherId !== id && state.selected[otherId] && group.max_selections === 1) delete state.selected[otherId];
        });
      });
    });
    selectedIds().forEach(function (otherId) {
      var other = eventById(otherId);
      if (!other || dayById(otherId).id !== dayById(id).id) return;
      if (overlaps(event, other)) delete state.selected[otherId];
    });
    state.selected[id] = state.selected[id] || [];
    syncSelection();
  }

  function toggleLot(eventId, lotId, checked) {
    if (checked && !state.selected[eventId]) toggleEvent(eventId, true);
    if (!state.selected[eventId]) return;
    var list = state.selected[eventId];
    var event = eventById(eventId);
    if (checked && list.indexOf(lotId) === -1) list.push(lotId);
    if (!checked) state.selected[eventId] = list.filter(function (id) { return id !== lotId; });
    if (event.max_lot_selections && state.selected[eventId].length > event.max_lot_selections) {
      state.selected[eventId] = state.selected[eventId].filter(function (id) { return id !== lotId; });
      showError('[data-form-error]', 'Можно выбрать не более ' + event.max_lot_selections + ' лотов.');
    }
    syncSelection();
  }

  function payloadSelections() {
    return selectedIds().map(function (id) { return { event_id: id, lot_ids: state.selected[id] }; });
  }

  function personPayload(form) {
    var data = new FormData(form), person = {};
    ['last_name', 'first_name', 'middle_name', 'email', 'phone', 'organization', 'position', 'category', 'city', 'source', 'comment'].forEach(function (name) {
      person[name] = String(data.get(name) || '').trim();
    });
    return person;
  }

  function validateSelection() {
    var ids = selectedIds();
    if (!ids.length) return 'Выберите хотя бы одно событие.';
    for (var i = 0; i < ids.length; i++) {
      var event = eventById(ids[i]);
      if (event.kind === 'exchange' && state.selected[ids[i]].length < event.min_lot_selections) return 'Выберите хотя бы один лот биржи.';
    }
    return '';
  }

  function submitRegistration(event) {
    event.preventDefault();
    var form = event.currentTarget;
    showError('[data-form-error]', '');
    var selectionError = validateSelection();
    if (selectionError) { showError('[data-form-error]', selectionError); return; }
    if (!form.reportValidity()) return;
    var button = $('[data-submit]');
    button.disabled = true;
    var person = personPayload(form);
    state.email = person.email;
    api('/registrations/submit/', {
      method: 'POST',
      body: JSON.stringify({
        forum: slug,
        person: person,
        selections: payloadSelections(),
        captcha_token: $('#captcha-token').value,
        consents: {
          pd: form.elements.pd.checked, policy: form.elements.policy.checked,
          media: form.elements.media.checked, news: form.elements.news.checked
        }
      })
    }).then(function (result) {
      form.hidden = true;
      $('[data-verify-email]').textContent = state.email;
      var debug = $('[data-debug-code]');
      debug.hidden = !result.debug_code;
      if (result.debug_code) debug.textContent = 'Локальный DEBUG-код: ' + result.debug_code;
      $('[data-verify]').hidden = false;
      $('#verification-code').focus();
    }).catch(function (error) {
      showError('[data-form-error]', error.message);
    }).finally(function () { button.disabled = false; });
  }

  function verifyEmail(event) {
    event.preventDefault();
    var button = $('button[type="submit"]', event.currentTarget);
    button.disabled = true;
    var code = $('#verification-code').value.trim();
    showError('[data-verify-error]', '');
    api('/registrations/verify/', {
      method: 'POST',
      body: JSON.stringify({ forum: slug, email: state.email, code: code })
    }).then(function (result) {
      state.token = result.token;
      history.replaceState(null, '', location.pathname + '?t=' + encodeURIComponent(result.token));
      $('[data-verify]').hidden = true;
      renderResult(result.registration);
      $('[data-result]').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }).catch(function (error) {
      showError('[data-verify-error]', error.message);
    }).finally(function () { button.disabled = false; });
  }

  function renderResult(registration) {
    $('[data-registration-form]').hidden = true;
    $('[data-verify]').hidden = true;
    $('[data-registration-status]').hidden = true;
    var personalLink = location.origin + location.pathname + '?t=' + encodeURIComponent(state.token);
    var ticket = registration.ticket;
    var ticketHtml = '';
    if (ticket) {
      ticketHtml = '<section class="promtour-ticket"><div><p class="eyebrow">Личный билет</p><h3>Электронный билет с QR</h3><p>Покажите QR на стойке. Он предназначен только для отметки прибытия сотрудником и не открывает редактирование заявки.</p>' +
        '<a class="btn btn-primary" href="' + esc(ticket.pdf_path + '?t=' + encodeURIComponent(state.token)) + '">Скачать билет в PDF</a>' +
        (ticket.checked_in_at ? '<p class="promtour-status promtour-status-confirmed">Прибытие отмечено: ' + esc(new Date(ticket.checked_in_at).toLocaleString('ru-RU')) + '</p>' : '') + '</div>' +
        '<img src="' + esc(ticket.qr_path + '?t=' + encodeURIComponent(state.token)) + '" alt="QR-код для стойки регистрации" width="220" height="220"></section>';
    } else {
      ticketHtml = '<section class="promtour-ticket-note"><p>Электронный билет с QR появится здесь после подтверждения хотя бы одного события.</p></section>';
    }
    var html = '<div class="promtour-result-head"><div><p class="eyebrow">Заявка ' + esc(registration.id) + '</p><h3>Вы зарегистрированы</h3></div><p><b>' + esc(registration.participant.full_name) + '</b><br>' + esc(registration.participant.organization) + '</p></div>' +
      '<p class="promtour-personal-link"><a href="' + esc(personalLink) + '">Личная ссылка на билет и статусы</a></p>' + ticketHtml +
      '<div class="promtour-result-items">' + registration.items.map(function (item) {
        var view = registrationView(item.event);
        var lots = item.lots.length ? '<p><b>Лоты:</b> ' + item.lots.map(function (lot) { return esc(lot.number + ' — ' + lot.title); }).join(', ') + '</p>' : '';
        var price = view.paid ? '<p class="promtour-result-price"><b>Стоимость: ' + esc(formatPrice(view.price)) + '.</b> ' + esc(view.payment_note) + '</p>' : '';
        return '<article class="promtour-result-item"><div><h4>' + esc(view.title) + '</h4><p>' + esc(view.day) + ' · ' + esc(view.time) + '</p></div>' +
          '<span class="promtour-status promtour-status-' + esc(item.status) + '">' + esc(STATUS[item.status] || item.status) + '</span>' + price + lots +
          (item.decision_note ? '<p>' + esc(item.decision_note) + '</p>' : '') + '</article>';
      }).join('') + '</div>';
    $('[data-result]').innerHTML = html;
    $('[data-result]').hidden = false;
    $$('[data-route-select]').forEach(function (button) { button.disabled = true; button.textContent = 'Заявка уже оформлена'; });
  }

  function loadBackend() {
    return Promise.all([api('/forums/' + encodeURIComponent(slug) + '/program/'), window.publicSubmissionsReady]).then(function (values) {
      var program = values[0];
      state.submissionsEnabled = values[1];
      state.program = program;
      state.speakers = program.speakers || [];
      state.routeEvents = {};
      state.exchangeEvents = [];
      var routeIndex = 0;
      program.days.forEach(function (day) {
        day.events.forEach(function (event) {
          if (event.kind === 'route') {
            routeIndex += 1;
            var number = routeNumberFor(event) || routeIndex;
            state.routeEvents[number] = event;
          }
          if (event.kind === 'exchange') state.exchangeEvents.push(event);
        });
      });
      renderProgram();
      renderRoutes();
      renderSpeakers();
      renderExchange();
      renderRegistration();
      if (state.token) {
        return api('/registration/?t=' + encodeURIComponent(state.token)).then(function (result) {
          renderResult(result.registration);
        }).catch(function (error) {
          state.token = '';
          history.replaceState(null, '', location.pathname);
          renderRegistration();
          showError('[data-api-error]', error.message + ' Можно отправить новую заявку.');
        });
      }
      return null;
    }).catch(function (error) {
      $('[data-registration-status]').hidden = true;
      $('[data-exchange-lots]').innerHTML = '<div class="promtour-dark-note"><p>Не удалось загрузить лоты. Попробуйте обновить страницу позже.</p></div>';
      showError('[data-api-error]', error.message);
      $$('[data-route-select]').forEach(function (button) { button.disabled = true; button.textContent = 'Сервис записи недоступен'; });
    });
  }

  function trapMobileMenu(event) {
    var menu = $('#mobile-menu');
    if (event.key !== 'Tab' || !menu.classList.contains('is-open')) return;
    var items = $$('a[href], button:not([disabled])', menu).filter(function (item) { return item.offsetParent !== null; });
    if (!items.length) return;
    var first = items[0], last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  document.addEventListener('DOMContentLoaded', function () {
    window.hydrateIcons();
    window.ForumCaptcha.init('smart-captcha', 'captcha-token');
    $('[data-menu-open]').addEventListener('click', function () {
      window.setTimeout(function () {
        if ($('#mobile-menu').classList.contains('is-open')) $('[data-menu-close]').focus();
      }, 280);
    });
    renderProgram();
    renderRoutes();
    renderSpeakers();
    renderNominations();

    $('[data-registration-events]').addEventListener('change', function (event) {
      if (event.target.matches('[data-event-select]')) toggleEvent(event.target.getAttribute('data-event-select'), event.target.checked);
      if (event.target.matches('[data-lot]')) toggleLot(event.target.getAttribute('data-event'), event.target.getAttribute('data-lot'), event.target.checked);
    });
    $('[data-registration-form]').addEventListener('submit', submitRegistration);
    $('[data-verify-form]').addEventListener('submit', verifyEmail);
    $('[data-speaker-search]').addEventListener('input', function (event) {
      var query = event.target.value.trim().toLowerCase();
      var visible = 0;
      $$('[data-speaker-card]').forEach(function (card) {
        var matches = !query || card.getAttribute('data-search').indexOf(query) !== -1;
        card.hidden = !matches;
        if (matches) visible += 1;
      });
      $('[data-speakers-empty]').hidden = visible > 0;
    });

    document.addEventListener('click', function (event) {
      var speakerButton = event.target.closest('[data-speaker-id]');
      if (speakerButton) openSpeaker(speakerButton.getAttribute('data-speaker-id'));
      var routeButton = event.target.closest('[data-route-select]');
      if (routeButton && !routeButton.disabled) {
        var routeEvent = state.routeEvents[routeButton.getAttribute('data-route-select')];
        if (routeEvent) {
          toggleEvent(routeEvent.id, true);
          $('#registration').scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
      var close = event.target.closest('[data-dialog-close]');
      if (close) close.closest('dialog').close();
      if (event.target.matches('dialog.promtour-dialog')) event.target.close();
    });
    $$('dialog.promtour-dialog').forEach(function (dialog) {
      dialog.addEventListener('close', function () {
        if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
      });
    });
    document.addEventListener('keydown', trapMobileMenu);
    window.loadPromtourNominations().then(function (contest) {
      content.nominations = contest.nominations.map(function (nomination, index) {
        return { number: index + 1, title: nomination.title, visualGroup: nomination.visual_group, nomineeCount: nomination.nominees.length };
      });
      var now = Date.now();
      var open = contest.is_open && (!contest.voting_opens_at || now >= new Date(contest.voting_opens_at).getTime()) && (!contest.voting_closes_at || now <= new Date(contest.voting_closes_at).getTime());
      $('[data-contest-state]').textContent = open ? 'Онлайн-голосование открыто. Подтвердите email, чтобы отправить бюллетень и защитить конкурс от повторных голосов.' : 'Голосование закрыто или ещё не началось. Актуальный статус доступен на странице конкурса.';
      renderNominations();
    }).catch(function () {
      $('[data-contest-state]').textContent = 'Не удалось проверить статус голосования. Обновите страницу позже.';
      $('[data-nominations]').innerHTML = '<p role="alert">Не удалось загрузить номинации. Попробуйте обновить страницу позже.</p>';
    });
    loadBackend();
  });
})();
