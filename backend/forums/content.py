from django.utils import timezone

from .models import ContentRevision
from .media import public_asset


def revision_token():
    return str(ContentRevision.objects.values_list('token', flat=True).first() or '')


def page_payload(forum):
    try:
        page = forum.page
    except forum._meta.get_field('page').related_model.DoesNotExist:
        return None
    venue = page.main_venue if page.main_venue and page.main_venue.is_published else None
    starts = timezone.localtime(forum.starts_at)
    ends = timezone.localtime(forum.ends_at)
    month = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')
    date_label = f'{starts.day}–{ends.day} {month[ends.month-1]} {ends.year} · Томск' if starts.month == ends.month and starts.year == ends.year else f'{starts:%d.%m.%Y} – {ends:%d.%m.%Y}'
    sections = {s.key: ({k: getattr(s, k) for k in ('heading', 'eyebrow', 'body', 'note', 'action_label', 'action_url', 'is_published')} if s.is_published else {'is_published': False}) for s in forum.page_sections.all()}
    contest = getattr(forum, 'contest', None)
    if contest and 'contest' in sections and sections['contest']['is_published']:
        sections['contest']['heading'] = contest.title
        sections['contest']['body'] = contest.description
    return {
        'brand_name': page.brand_name, 'brand_subtitle': page.brand_subtitle,
        'brand_logo': page.brand_variants.get('400') or (page.brand_logo.url if page.brand_logo else public_asset(page.brand_static_logo)),
        'date_label': page.date_label or date_label,
        'venue_label': page.venue_label, 'venue_note': page.venue_note,
        'venue': {'name': venue.name, 'address': venue.address} if venue else None,
        'organizer_email': page.organizer_email, 'footer_text': page.footer_text,
        'hero_image': page.hero_variants.get('960') or (page.hero_image.url if page.hero_image else public_asset(page.hero_static_image)),
        'registration_notice': page.registration_notice,
        'sections': sections,
        'navigation': [{'id': str(n.pk), 'label': n.label, 'target': n.target} for n in forum.navigation.all() if n.is_published],
        'contacts': [{
            'id': str(c.pk),
            'title': c.title or (c.venue.name if c.venue else ''),
            'subtitle': c.subtitle,
            'body': ((c.venue.address + '\n') if c.venue else '') + c.body,
            'link_label': c.link_label, 'link_url': c.link_url,
        } for c in forum.contact_cards.all() if c.is_published and (not c.venue or c.venue.is_published)],
        'logos': [{'id': str(l.pk), 'group': l.group, 'name': l.name, 'background': l.image_background, 'website_url': l.website_url,
                   'image': l.variants.get('400') or (l.image.url if l.image else public_asset(l.static_image))}
                  for l in forum.organization_logos.all() if l.is_published],
    }


def speaker_photos(speaker):
    placements = {p.placement: p for p in speaker.photo_placements.all()}
    result = {}
    for name in ('circle', 'program', 'card', 'dialog'):
        placement = placements.get(name)
        own_image = bool(placement and placement.image)
        variants = placement.variants if own_image else speaker.photo_variants
        base = placement.image.url if own_image else speaker.photo_url
        # Only the bundled photographs have these pre-generated static derivatives.
        bundled = speaker.static_photo if not speaker.photo and not own_image else ''
        if not variants and bundled.startswith('/img/promtour/speakers/') and bundled.endswith('.webp'):
            variants = {'160': public_asset(bundled[:-5] + '-320.webp'), '400': public_asset(bundled[:-5] + '-640.webp'), '960': public_asset(bundled)}
        result[name] = {
            'url': variants.get('160' if name in ('circle', 'program') else '400') or base,
            'large': variants.get('960') or base,
            'fit': placement.fit if placement else ('contain' if name == 'dialog' else 'cover'),
            'x': placement.focal_x if placement else 50,
            'y': placement.focal_y if placement else 25,
        }
    return result
