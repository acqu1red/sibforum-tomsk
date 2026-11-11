(function () {
  'use strict';
  var esc = window.escapeHtml;
  function safeLink(value) {
    if (!value) return '';
    if (/^(\/[^/]|\/$|#)/.test(value) && !/[\\\u0000-\u001f]/.test(value)) return value;
    try {
      var u = new URL(value);
      return /^(https:|mailto:|tel:)$/.test(u.protocol) ? u.href : '';
    } catch (e) {
      return '';
    }
  }
  function photo(speaker, context, className) {
    var p = speaker.photos && speaker.photos[context];
    if (!p) {
      p = {
        url: speaker.photo || '',
        fit: context === 'dialog' ? 'contain' : 'cover',
        x: 50,
        y: 25
      };
    }
    var url = safeLink(p.url),
      name = speaker.short_name || speaker.name;
    if (!url)
      return (
        '<span class="' +
        className +
        ' promtour-photo-placeholder" role="img" aria-label="Фотография не предоставлена"><b>' +
        esc(
          name
            .split(/\s+/)
            .slice(0, 2)
            .map(function (s) {
              return s[0];
            })
            .join('')
        ) +
        '</b></span>'
      );
    var style =
      'object-fit:' +
      (p.fit === 'contain' ? 'contain' : 'cover') +
      ';object-position:' +
      Math.max(0, Math.min(100, Number(p.x) || 0)) +
      '% ' +
      Math.max(0, Math.min(100, Number(p.y) || 0)) +
      '%';
    return (
      '<img class="' +
      className +
      '" src="' +
      esc(url) +
      '" alt="' +
      esc(name) +
      '" loading="lazy" decoding="async" width="' +
      (context === 'circle' ? 112 : context === 'program' ? 56 : 400) +
      '" height="' +
      (context === 'circle' ? 112 : context === 'program' ? 56 : 360) +
      '" style="' +
      style +
      '">'
    );
  }
  function apply(page) {
    if (!page) return;
    document.querySelectorAll('[data-page]').forEach(function (el) {
      var key = el.dataset.page;
      if (Object.prototype.hasOwnProperty.call(page, key)) {
        el.textContent = page[key] || '';
        el.hidden = !page[key];
      }
    });
    document.querySelectorAll('[data-copy]').forEach(function (el) {
      var a = el.dataset.copy.split('.'),
        s = page.sections[a[0]];
      if (s && Object.prototype.hasOwnProperty.call(s, a[1])) {
        el.textContent = s[a[1]] || '';
        el.hidden = !s[a[1]];
      }
    });
    document.querySelectorAll('[data-copy-link]').forEach(function (el) {
      var s = page.sections[el.dataset.copyLink];
      if (s) {
        var url = safeLink(s.action_url);
        if (url) el.href = url;
        el.hidden = !url || !s.action_label;
      }
    });
    Object.keys(page.sections).forEach(function (key) {
      var section = document.getElementById(key);
      if (section) section.hidden = !page.sections[key].is_published;
    });
    if (page.venue) {
      document.querySelectorAll('[data-main-venue-name]').forEach(function (el) {
        el.textContent = page.venue.name;
      });
      document.querySelectorAll('[data-main-venue-address]').forEach(function (el) {
        el.textContent = page.venue.address;
      });
    }
    document.querySelectorAll('.brand-logo').forEach(function (img) {
      var logo = safeLink(page.brand_logo);
      if (logo) { img.src = logo; img.alt = page.brand_name; }
      img.hidden = !logo;
    });
    if (!document.body.classList.contains('contest-page') && page.sections.hero && page.sections.hero.is_published) {
      document.title = [page.sections.hero.eyebrow, page.sections.hero.heading].filter(Boolean).join(' · ');
      var description = document.querySelector('meta[name="description"]');
      if (description) description.content = page.sections.hero.body;
    }
    var hero = document.querySelector('.promtour-hero');
    if (hero && safeLink(page.hero_image))
      hero.style.setProperty('--forum-hero-image', 'url(' + JSON.stringify(page.hero_image) + ')');
    var links = page.navigation
      .map(function (n) {
        var url = safeLink(n.target);
        return url ? '<li><a href="' + esc(url) + '">' + esc(n.label) + '</a></li>' : '';
      })
      .join('');
    document.querySelectorAll('[data-site-navigation]').forEach(function (el) {
      el.innerHTML = links;
    });
    document.querySelectorAll('[data-site-mobile-navigation]').forEach(function (el) {
      el.innerHTML =
        page.navigation
          .map(function (n) {
            var url = safeLink(n.target);
            return url ? '<a href="' + esc(url) + '">' + esc(n.label) + '</a>' : '';
          })
          .join('') + '<a href="/#registration">Регистрация</a>';
    });
    var contacts = document.querySelector('[data-site-contacts]');
    if (contacts)
      contacts.innerHTML = page.contacts
        .map(function (c) {
          var link = safeLink(c.link_url);
          return (
            '<article class="promtour-contact-card">' +
            (c.subtitle ? '<span>' + esc(c.subtitle) + '</span>' : '') +
            '<h3>' +
            esc(c.title) +
            '</h3><p>' +
            esc(c.body) +
            '</p>' +
            (link
              ? '<a href="' + esc(link) + '">' + esc(c.link_label || c.link_url) + '</a>'
              : '') +
            '</article>'
          );
        })
        .join('');
    var organizations = document.querySelector('[data-site-organizations]');
    if (organizations)
      organizations.innerHTML = ['organizers', 'partners', 'enterprises']
        .map(function (group) {
          var section = page.sections[group];
          var logos = page.logos.filter(function (l) {
            return l.group === group;
          });
          if (!logos.length || (section && !section.is_published)) return '';
          return (
            '<section class="promtour-logo-group"><h2>' +
            esc(section ? section.heading : group) +
            '</h2>' +
            (section && section.body ? '<p>' + esc(section.body) + '</p>' : '') +
            '<div class="promtour-logos">' +
            logos
              .map(function (l) {
                var image = safeLink(l.image),
                  url = safeLink(l.website_url);
                var content = image
                  ? '<img src="' +
                    esc(image) +
                    '" alt="' +
                    esc(l.name) +
                    '" loading="lazy" decoding="async" width="180" height="90">'
                  : '<span>' + esc(l.name) + '</span>';
                return url
                  ? '<a href="' +
                      esc(url) +
                      '" target="_blank" rel="noopener noreferrer">' +
                      content +
                      '</a>'
                  : '<div>' + content + '</div>';
              })
              .join('') +
            '</div></section>'
          );
        })
        .join('');
    document.querySelectorAll('[data-organizer-email]').forEach(function (el) {
      el.textContent = page.organizer_email;
      el.href = 'mailto:' + page.organizer_email;
      el.hidden = !page.organizer_email;
    });
  }
  var watching = false;
  function watch(callback, initialVersion) {
    if (watching) return;
    watching = true;
    var version = initialVersion || null,
      busy = false;
    function check() {
      if (document.hidden || busy) return;
      busy = true;
      fetch('/api/v1/content-revision/', {
        cache: 'no-store',
        headers: { Accept: 'application/json' }
      })
        .then(function (r) {
          if (!r.ok) throw Error('revision');
          return r.json();
        })
        .then(function (data) {
          if (version !== null && version !== data.revision)
            return Promise.resolve(callback()).then(function () {
              version = data.revision;
            });
          version = data.revision;
        })
        .catch(function () {})
        .finally(function () {
          busy = false;
        });
    }
    check();
    setInterval(check, 15000);
    document.addEventListener('visibilitychange', check);
  }
  window.forumContent = { apply: apply, photo: photo, safeLink: safeLink, watch: watch };
})();
