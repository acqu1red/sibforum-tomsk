from django.conf import settings
from django.db import connection
from django.db.models import Prefetch
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import ChoiceGroup, ChoiceGroupEvent, Event, EventSpeaker, Forum, Speaker


def json_payload(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False})


def forum_payload(forum):
    return {
        'id': str(forum.id),
        'slug': forum.slug,
        'title': forum.title,
        'short_title': forum.short_title,
        'number': forum.number,
        'series': forum.series,
        'description': forum.description,
        'starts_at': forum.starts_at.isoformat(),
        'ends_at': forum.ends_at.isoformat(),
        'timezone': forum.timezone,
        'is_featured': forum.is_featured,
    }


def venue_payload(venue):
    return {
        'id': str(venue.id),
        'name': venue.name,
        'address': venue.address,
        'map_url': venue.map_url,
    }


def speaker_payload(speaker):
    return {
        'id': str(speaker.id),
        'name': speaker.full_name,
        'position': speaker.credentials,
        'topic': speaker.topic,
        'photo': speaker.photo_url,
        'events': [
            {
                'id': str(link.event_id),
                'title': link.event.title,
                'role': link.role,
                'topic': link.topic,
            }
            for link in speaker.event_links.all() if link.event.is_published
        ],
    }


def event_payload(event):
    payload = {
        'id': str(event.id),
        'kind': event.kind,
        'slug': event.slug,
        'title': event.title,
        'annotation': event.annotation,
        'description': event.description,
        'start_time': event.start_time.strftime('%H:%M'),
        'end_time': event.end_time.strftime('%H:%M'),
        'registration_policy': event.registration_policy,
        'detail_mode': event.detail_mode,
        'has_details': event.has_details,
        'external_url': event.external_url,
        'capacity_target': event.capacity_target,
        'is_paid': event.is_paid,
        'venue': venue_payload(event.venue) if event.venue else None,
        'speakers': [
            {
                'id': str(link.speaker_id),
                'role': link.role,
                'topic': link.topic,
            }
            for link in event.speaker_links.all() if link.speaker.is_published
        ],
    }
    if event.kind == Event.Kind.ROUTE:
        payload['enterprises'] = [
            {'name': enterprise.name, 'description': enterprise.description}
            for enterprise in event.enterprises.all()
        ]
    if event.is_paid:
        payload['price'] = str(event.price)
        payload['payment_note'] = event.payment_note
    if event.kind == Event.Kind.EXCHANGE:
        payload['min_lot_selections'] = event.min_lot_selections
        payload['max_lot_selections'] = event.max_lot_selections
        payload['lots'] = [
            {
                'id': str(lot.id),
                'number': lot.number,
                'title': lot.title,
                'customer_name': lot.customer_name if lot.customer_visible else '',
                'technical_url': lot.technical_url,
            }
            for lot in event.lots.all() if lot.is_published
        ]
    return payload


@never_cache
@require_GET
def public_config(request):
    return json_payload({
        'captcha_enabled': bool(settings.YANDEX_SMARTCAPTCHA_SECRET and settings.YANDEX_SMARTCAPTCHA_CLIENT_ID),
        'client_id': settings.YANDEX_SMARTCAPTCHA_CLIENT_ID,
    })


@never_cache
@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        return json_payload({'ok': False, 'service': 'platform-backend'}, status=503)
    return json_payload({'ok': True, 'service': 'platform-backend', 'version': '0.1.0'})


@require_GET
def forum_list(request):
    forums = Forum.objects.filter(status=Forum.Status.PUBLISHED)
    return json_payload({'items': [forum_payload(forum) for forum in forums]})


@require_GET
def forum_program(request, slug):
    forum = Forum.objects.filter(slug=slug, status=Forum.Status.PUBLISHED).prefetch_related(
        'venues',
        Prefetch('days__events', queryset=Event.objects.select_related('venue').prefetch_related(
            'lots', 'enterprises',
            Prefetch('speaker_links', queryset=EventSpeaker.objects.select_related('speaker')),
        )),
        Prefetch('days__choice_groups', queryset=ChoiceGroup.objects.prefetch_related(
            Prefetch('event_links', queryset=ChoiceGroupEvent.objects.select_related('event')),
        )),
        Prefetch('speakers', queryset=Speaker.objects.filter(is_published=True).prefetch_related(
            Prefetch('event_links', queryset=EventSpeaker.objects.select_related('event')),
        ), to_attr='public_speakers'),
    ).first()
    if forum is None:
        return json_payload({'ok': False, 'error': 'not_found'}, status=404)

    days = []
    for day in forum.days.all():
        events = [event for event in day.events.all() if event.is_published]
        groups = []
        for group in day.choice_groups.all():
            event_ids = [
                str(link.event_id)
                for link in group.event_links.all()
                if link.event.is_published
            ]
            groups.append({
                'id': str(group.id),
                'title': group.title,
                'min_selections': group.min_selections,
                'max_selections': group.max_selections,
                'event_ids': event_ids,
            })
        days.append({
            'id': str(day.id),
            'date': day.date.isoformat(),
            'title': day.title,
            'position': day.position,
            'events': [event_payload(event) for event in events],
            'choice_groups': groups,
        })

    return json_payload({
        'forum': forum_payload(forum),
        'venues': [venue_payload(venue) for venue in forum.venues.all() if venue.is_published],
        'days': days,
        'speakers': [speaker_payload(speaker) for speaker in forum.public_speakers],
    })
