/* Общие операции с программой: поиск события, время, пересечения, файл календаря .ics, вёрстка для печати/PDF.
   Используются страницами программы, регистрации и «Моей программы». */
window.Schedule = (function () {
  'use strict';
  var SF = window.SF, PR = window.PROGRAM, esc = window.escapeHtml, plural = window.plural;
  var WEEKDAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница'];

  var index = {};
  PR.days.forEach(function (d) { d.items.forEach(function (it) { index[it.id] = { item: it, day: d }; }); });

  function mins(t) { var p = t.split(':'); return +p[0] * 60 + +p[1]; }
  function range(it) { return it.start + '–' + it.end; }
  function overlaps(a, b) { return mins(a.start) < mins(b.end) && mins(b.start) < mins(a.end); }
  function dateLabel(d) { return WEEKDAYS[d.id - 1] + ', ' + d.tab.split(', ')[1]; }
  function placeText(it) { var v = PR.venues[it.venue]; return v.name + (it.hall ? ' · ' + it.hall : ''); }
  function trackLabel(it) {
    if (it.type === 'plenary') return 'Пленарное';
    return 'Т' + it.track + ' · ' + SF.tracks[it.track - 1].short;
  }
  function trackColor(it) { return it.type === 'plenary' ? 'var(--esg-strong)' : 'var(--t' + it.track + ')'; }
  function peopleOf(it) {
    return (it.moderators || []).concat(it.speakers || []).map(function (k) { return PR.people[k]; });
  }

  // Записи {item, day} по списку id, по дням и времени
  function sorted(ids) {
    return ids.map(function (id) { return index[id]; }).filter(Boolean).sort(function (a, b) {
      return a.day.id - b.day.id || mins(a.item.start) - mins(b.item.start);
    });
  }

  // События из ids, которые идут в тот же день и пересекаются по времени с id
  function conflicts(id, ids) {
    var a = index[id];
    if (!a) return [];
    return ids.filter(function (m) {
      var b = index[m];
      return m !== id && b && b.day.id === a.day.id && overlaps(a.item, b.item);
    }).map(function (m) { return index[m].item; });
  }

  // ---------- Календарь .ics ----------
  function icsStamp(dateStr, time) {
    var d = dateStr.split('-'), t = time.split(':');
    // Томск: UTC+7
    return new Date(Date.UTC(+d[0], +d[1] - 1, +d[2], +t[0] - 7, +t[1])).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  }
  function icsText(s) { return String(s).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n'); }

  function downloadIcs(ids, fileName) {
    var now = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    var lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Siberian Forum//Program//RU', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH'];
    sorted(ids).forEach(function (r) {
      var it = r.item, v = PR.venues[it.venue];
      lines.push('BEGIN:VEVENT', 'UID:' + it.id + '@siberianforum.ru', 'DTSTAMP:' + now,
        'DTSTART:' + icsStamp(r.day.date, it.start), 'DTEND:' + icsStamp(r.day.date, it.end),
        'SUMMARY:' + icsText(it.title), 'LOCATION:' + icsText(placeText(it) + ', ' + v.address),
        'DESCRIPTION:' + icsText('V Сибирский форум «Производительность и устойчивое развитие». ' + (it.desc || it.lead || '')),
        'END:VEVENT');
    });
    lines.push('END:VCALENDAR');
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' }));
    a.download = fileName || (ids.length === 1 ? 'siberian-forum-' + ids[0] + '.ics' : 'siberian-forum-my-program.ics');
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.toast(ids.length === 1 ? 'Файл календаря скачан' : 'Скачан календарь: ' + ids.length + ' ' + plural(ids.length, ['событие', 'события', 'событий']));
  }

  // ---------- Печать / PDF ----------
  function printRow(it, note) {
    var names = peopleOf(it).map(function (p) { return p.name; });
    return '<tr><td class="t">' + range(it) + '</td><td class="k">' + esc(trackLabel(it)) + '</td><td><b>' + esc(it.title) + '</b>' +
      '<div class="sp">' + esc(placeText(it)) + (names.length ? ' · ' + esc(names.join(', ')) : '') +
      (it.closed ? ' · закрытое мероприятие' : '') + (note ? ' · ' + esc(note) : '') + '</div></td></tr>';
  }

  // ids = null — вся программа; иначе только эти события. notes — подписи к событиям (например, «лист ожидания»)
  function buildPrint(target, ids, opts) {
    opts = opts || {};
    var html = '<h1>' + esc(opts.title || 'Программа') + ' · V Сибирский форум «Производительность и устойчивое развитие»</h1>' +
      '<p class="p-meta">13–17 апреля 2026 · Томск · время томское (МСК+4) · siberianforum.ru' +
      (opts.subtitle ? ' · ' + esc(opts.subtitle) : ' · программа может дополняться и корректироваться') + '</p>';
    PR.days.forEach(function (d) {
      var rows = '';
      if (d.slots && !ids) {
        d.slots.forEach(function (s) {
          if (s.type === 'service') { rows += '<tr class="svc-row"><td class="t">' + s.start + '–' + s.end + '</td><td class="k"></td><td>' + esc(s.title) + '</td></tr>'; return; }
          d.items.filter(function (it) { return it.slot === s.key; }).forEach(function (it) { rows += printRow(it); });
        });
      } else {
        d.items.filter(function (it) { return !ids || ids.indexOf(it.id) !== -1; })
          .sort(function (a, b) { return mins(a.start) - mins(b.start); })
          .forEach(function (it) { rows += printRow(it, opts.notes && opts.notes[it.id]); });
      }
      if (rows) html += '<h2>' + esc(dateLabel(d)) + (d.main ? ' — главный день · ОЭЗ «Томск», пр. Развития, 3' : '') + '</h2><table>' + rows + '</table>';
    });
    target.innerHTML = html;
  }

  return {
    index: index, mins: mins, range: range, overlaps: overlaps, dateLabel: dateLabel, placeText: placeText,
    trackLabel: trackLabel, trackColor: trackColor, peopleOf: peopleOf, sorted: sorted, conflicts: conflicts,
    downloadIcs: downloadIcs, buildPrint: buildPrint
  };
})();
