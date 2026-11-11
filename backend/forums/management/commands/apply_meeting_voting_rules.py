from django.core.management.base import BaseCommand
from django.db import transaction

from forums.models import ForumPage
from voting.models import Contest


class Command(BaseCommand):
    help = 'Однократно применить согласованные 11.11.2026 настройки простого голосования. Голоса не сбрасываются.'

    @transaction.atomic
    def handle(self, *args, **options):
        page = ForumPage.objects.select_for_update().get(forum__slug='promtour')
        if page.meeting_revision == 'telemost-2026-11-11':
            self.stdout.write('Правила встречи уже применены. Редакторские изменения сохранены.')
            return
        contest = Contest.objects.get(forum=page.forum)
        contest.voting_mode = 'simple'
        contest.is_open = True
        contest.max_ballots_per_network = 1
        contest.rules_text = 'Можно голосовать только в знакомых номинациях. Допустимое количество участников указано в каждой номинации. Повторное голосование с одной сети и браузера ограничено.'
        contest.save(update_fields=('voting_mode', 'is_open', 'max_ballots_per_network', 'rules_text', 'updated_at'))
        for nomination in contest.nominations.all():
            nomination.min_selections = 0
            nomination.max_selections = max(1, min(3, nomination.nominees.filter(is_active=True).count()))
            nomination.save(update_fields=('min_selections', 'max_selections', 'updated_at'))
        for speaker in page.forum.speakers.filter(short_position=''):
            speaker.short_position = speaker.credentials.split(';')[0].strip()[:240]
            speaker.save(update_fields=('short_position', 'updated_at'))
        page.meeting_revision = 'telemost-2026-11-11'
        page.save(update_fields=('meeting_revision', 'updated_at'))
        self.stdout.write(self.style.SUCCESS('Включён простой режим; лимит до трёх на номинацию. Ни один голос не удалён.'))
