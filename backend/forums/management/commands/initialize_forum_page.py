"""Add editorial records once; never overwrite subsequent administrator edits."""
from django.core.management.base import BaseCommand
from django.db import transaction

from forums.models import ContactCard, Forum, ForumPage, NavigationItem, OrganizationLogo, PageSection


SECTIONS = {
 'hero': dict(heading='#ПРОМОТУРТОМСК–2026', eyebrow='V Сибирский форум по промышленному туризму', body='Два дня о развитии промышленного туризма: посещение действующих предприятий, обмен региональным опытом, деловые переговоры и семейные мероприятия.', action_label='Онлайн-голосование', action_url='/contest/'),
 'speakers': dict(heading='Люди форума', body='Эксперты, участники и модераторы. Нажмите на фотографию, чтобы познакомиться.'),
 'program': dict(heading='Программа форума', body='В первый день — предприятия и практический мастер-класс. Во второй — общая деловая часть и мероприятия на выбор.'),
 'routes': dict(heading='Экскурсионные маршруты', body='Посещение действующих предприятий Томска и Томской области. Выберите маршрут и познакомьтесь с его программой.', note='Заявка не является оплатой и не гарантирует место. Куратор свяжется с вами и расскажет об условиях участия.', action_label='Выбрать маршрут'),
 'exchange': dict(heading='Биржа субконтрактации', body='Площадка для переговоров потенциальных исполнителей с заказчиками. Изучите технические запросы и выберите интересующие лоты.', note='Изучите лоты и технические материалы. Выберите биржу и нужные лоты в регистрации. Дождитесь решения куратора: заявка проходит модерацию.', action_label='Лоты и технические материалы'),
 'contest': dict(heading='«Индустриальный код»', body='Проекты Томской области в сфере промышленного туризма. Познакомьтесь с номинантами и поддержите тех, чей опыт вам близок.', note='Для голосования не нужно регистрироваться на форум. Можно выбрать кандидатов только в знакомых вам номинациях.', action_label='Перейти к голосованию', action_url='/contest/'),
 'registration': dict(heading='Регистрация и личный билет', eyebrow='Одна заявка на мероприятия форума', body='Выберите мероприятия и заполните контактные данные. Маршруты и биржа проходят модерацию. После подтверждения будут доступны личная ссылка, QR и PDF-билет.'),
 'contacts': dict(heading='Как найти форум'),
 'organizers': dict(heading='Организаторы форума'),
 'partners': dict(heading='Партнёры форума'),
 'enterprises': dict(heading='Промтуризм в Томске'),
}


class Command(BaseCommand):
 help = 'Создать недостающие тексты, меню и контакты сайта без перезаписи изменений организатора.'

 def add_arguments(self, parser):
  parser.add_argument('--slug', default='promtour')

 @transaction.atomic
 def handle(self, *args, **options):
  forum = Forum.objects.get(slug=options['slug'])
  venue = forum.venues.filter(name__icontains='ОЭЗ').first()
  page, created = ForumPage.objects.get_or_create(forum=forum, defaults={
   'main_venue':venue,'venue_note':'24 ноября · с 10:00','organizer_email':'mail@tomsktpp.ru',
   'footer_text':'© Союз «Торгово-промышленная палата Томской области», 2026',
   'hero_static_image':'/img/hero/tomsk-night-1280.webp',
  })
  if page.initialized:
   self.stdout.write('Страница уже подготовлена. Изменения организатора не затронуты.')
   return
  for key, values in SECTIONS.items():
   PageSection.objects.get_or_create(forum=forum,key=key,defaults=values)
  for i,(label,target) in enumerate([('Программа','/#program'),('Маршруты','/#routes'),('Биржа субконтрактации','/#exchange'),('Конкурс','/contest/'),('Контакты','/#contacts')]):
   NavigationItem.objects.get_or_create(forum=forum,position=i,defaults={'label':label,'target':target})
  contacts=[
   ('ОЭЗ ТВТ «Томск»','24 ноября · деловая программа','Томск, пр. Развития, 3, 6 этаж.','',''),
   ('Союз «ТПП Томской области»','23 ноября · отправление маршрутов','Томск, ул. Красноармейская, 71а. Сбор участников в 09:15.','',''),
   ('Точка кипения — Томск','23 ноября · мастер-класс','Томск, пр. Ленина, 26. Мастер-класс «Город четырёх комфортов».','',''),
   ('Союз «ТПП Томской области»','Организатор и связь','','mail@tomsktpp.ru','mailto:mail@tomsktpp.ru'),
  ]
  for i,(title,subtitle,body,label,url) in enumerate(contacts):
   venue_match = forum.venues.filter(name__icontains=['ОЭЗ', 'ТПП', 'Точка кипения'][i]).first() if i < 3 else None
   if venue_match:
    title = ''
    body = ['', 'Время отправления указано в выбранном маршруте.', ''][i]
   ContactCard.objects.get_or_create(forum=forum,position=i,defaults={'title':title,'venue':venue_match,'subtitle':subtitle,'body':body,'link_label':label,'link_url':url})
  organizers=[('Торгово-промышленная палата Российской Федерации',''),('Союз «ТПП Томской области»','/img/logos/organizers/02-tpp-tomskoy-oblasti.png'),('Администрация Томской области','/img/logos/organizers/01-administratsiya-tomskoy-oblasti.png'),('Томский политехнический университет','/img/logos/organizers/06-tomskiy-politeh.png')]
  for i,(name,image) in enumerate(organizers):
   OrganizationLogo.objects.get_or_create(forum=forum,group='organizers',name=name,defaults={'static_image':image,'position':i})
  names=[]
  for event in forum.days.all():
   for route in event.events.filter(kind='route').prefetch_related('enterprises'):
    for enterprise in route.enterprises.all():
     if enterprise.name not in names:names.append(enterprise.name)
  for i,name in enumerate(names):
   image = '/img/logos/partners/10-mikran.png' if 'микран' in name.lower() else '/img/logos/partners/03-tomskoe-pivo.png' if 'томское пиво' in name.lower() else ''
   OrganizationLogo.objects.get_or_create(forum=forum,group='enterprises',name=name,defaults={'static_image':image,'position':i})
  page.initialized = True
  page.save(update_fields=('initialized', 'updated_at'))
  self.stdout.write(self.style.SUCCESS('Созданы только отсутствовавшие записи страницы. Существующие тексты и программа сохранены.'))
