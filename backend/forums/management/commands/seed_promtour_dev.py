from datetime import datetime, time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from forums.models import ChoiceGroup, ChoiceGroupEvent, Event, EventDay, EventSpeaker, Forum, RouteEnterprise, Speaker, Venue
from registrations.models import Lot


ROUTES = (
    (
        ('«Неотехника»', 'Производство комплексных промышленных решений: блок-контейнерных систем, дизельных и газопоршневых электростанций, приборного оборудования.'),
        ('«Копыловский кирпичный завод»', 'Производство строительных и облицовочных материалов из керамики.'),
        ('«Межениновская птицефабрика»', 'Производство и переработка мяса цыплят-бройлеров и мясных полуфабрикатов.'),
        ('«Томские Мебельные Фасады»', 'Производство мебельных фасадов.'),
    ),
    (
        ('«Самусьский судостроительно-судоремонтный завод»', 'Судостроение.'),
        ('«Интергласс»', 'Производство стеклотары.'),
        ('«Кахети»', 'Производство натуральных виноградных вин и плодовой алкогольной продукции.'),
    ),
    (
        ('«ЛОРГЕ Медикал»', 'Производство медицинского оборудования и электрохирургических инструментов.'),
        ('«ПРОКВАНТ»', 'Проектирование и производство аппаратных платформ, электроники и решений в сфере квантовых коммуникаций и телекоммуникаций.'),
        ('«ИнженерПластСервис»', 'Производство композиционных материалов.'),
    ),
    (
        ('«Томлесдрев»', 'Производство ДСП и ЛДСП.'),
        ('«Томсккабель»', 'Производство кабельной продукции.'),
        ('«Территория тайги»', 'Глубокая переработка дикоросов.'),
    ),
    (
        ('«Микран»', 'Проектирование и производство СВЧ-радиоэлектроники, микроэлектроники и телекоммуникационного оборудования.'),
        ('«ТЭМЗ»', 'Производство горно-шахтного и общепромышленного оборудования, электроприводов, запорно-регулирующей трубопроводной арматуры.'),
        ('«Томское пиво»', 'Производство пива и безалкогольных напитков.'),
    ),
    (
        ('Завод закалённого стекла (ИП Смуткин А. Г.)', 'Производство закалённого стекла для фасадов, стеклопакетов, мебели и интерьерных решений, производство зеркал.'),
        ('«ПК ШИК»', 'Производство изделий из кожи.'),
        ('«Континент Сервис» / «Томский кондитер»', 'Производство кондитерских изделий.'),
    ),
)


SPEAKERS = (
    ('Беленок Ирина Александровна', 'Генеральный директор АНОО ДПО «Сибирская Академия Туризма»; руководитель проектного офиса по промышленному туризму Новосибирской области; генеральный директор туроператора «СибАкадемТур» (ООО «Мандарин»); председатель комитета по предпринимательству в сфере туризма Союза «Торгово-промышленная палата Новосибирской области».', 'Инновации, традиции, развитие кооперации в промышленном туризме Новосибирской области: опыт, масштабирование, перспективы.', 'belenok', (('seminar', 'Спикер'),)),
    ('Епихина Наталья Сергеевна', 'Руководитель Учебно-методического центра Союза промышленников Алтайского края; исполнительный директор Клуба молодых промышленников Алтайского края; руководитель региональной команды «Открытая промышленность» в Алтайском крае.', '«Открытая промышленность» в Алтайском крае.', 'epikhina', (('seminar', 'Спикер'),)),
    ('Ковалева Светлана Александровна', 'Президент Союза «Торгово-промышленная палата Орловской области».', 'Презентация проекта «Крылатые компетенции».', 'kovaleva', (('seminar', 'Спикер'),)),
    ('Лукьянова Наталья Александровна', 'Д. ф. н., профессор, директор Школы общественных наук (ШОН) ТПУ.', 'Подготовка кадров для промышленного туризма: образовательная модель ТПУ как инструмент реализации российского подхода с учётом международного опыта.', 'lukyanova', (('seminar', 'Спикер'), ('strategy', 'Модератор'))),
    ('Гефсиманская Лидия Михайловна', 'Заместитель директора, начальник управления организационной работы ГАУ «Агентство по туризму Кузбасса».', 'Об опыте развития промышленного туризма в Кемеровской области — Кузбассе.', 'gefsimanskaya', (('seminar', 'Спикер'),)),
    ('Горбулицкая Анастасия Сергеевна', 'Директор ООО «НЗСП», Новосибирск.', 'Промышленный туризм как драйвер развития бизнеса и корпоративной среды.', 'gorbulitskaya', (('seminar', 'Спикер'),)),
    ('Калюжная Юлия Юрьевна', 'Исполнительный директор Томского областного отделения Русского географического общества.', 'Межрегиональный маршрут «Открываем Сибирь».', 'kalyuzhnaya', (('seminar', 'Спикер'), ('strategy', 'Модератор'))),
    ('Жаркова Марина Алексеевна', 'Заведующая кафедрой, руководитель отделения социально-гуманитарных наук Школы общественных наук Томского политехнического университета.', '', 'zharkova', (('masterclass', 'Модератор'), ('quiz', 'Модератор'))),
    ('Кисельникова Наталья Владимировна', 'Лауреат премии Правительства РФ за проект «Развитие промышленного туризма в регионах Российской Федерации»; методолог, эксперт в сфере политики открытости предприятий; автор образовательных программ и «Методологии развития промышленного туризма в Российской Федерации».', 'Инструменты повышения туристической привлекательности региона.', 'kiselnikova', (('seminar', 'Модератор и спикер'), ('strategy', 'Модератор'))),
    ('Акимова Александра Константиновна', 'Куратор проекта «Открытая промышленность» в Алтайском крае.', 'Роль работодателей в ранней профориентации. Модель ранней профориентации «Инженеры с детского сада».', 'akimova', (('quiz', 'Модератор'),)),
    ('Особа Александр Юрьевич', 'Ассистент отделения социально-гуманитарных наук Школы общественных наук Томского политехнического университета.', '', 'osoba', (('masterclass', 'Эксперт'),)),
    ('Медведьев Иван Иванович', 'Директор детского технопарка «Кванториум» в Томске, директор фестиваля «Технопредки: код технологий».', '', 'medvedev', (('masterclass', 'Модератор'), ('quiz', 'Модератор'))),
    ('Черенков Константин Анатольевич', 'Управляющий креативным кластером «Пенаты», директор краеведческого проекта «Сибириада».', '', 'cherenkov', (('opening', 'Модератор'), ('awards', 'Модератор'))),
)


class Command(BaseCommand):
    help = 'Наполняет локальную БД актуальным промтуром. Только для DEBUG.'

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Команда доступна только при DEBUG=1.')
        forum, _ = Forum.objects.update_or_create(
            slug='promtour',
            defaults={
                'title': 'Сибирский форум по промышленному туризму',
                'short_title': '#ПРОМОТУРТОМСК–2026',
                'number': 'V',
                'series': Forum.Series.PROMTOUR,
                'description': 'Два дня о развитии промышленного туризма: посещение действующих предприятий, обмен региональным опытом, деловые переговоры и семейные мероприятия.',
                'starts_at': timezone.make_aware(datetime(2026, 11, 23, 9, 0)),
                'ends_at': timezone.make_aware(datetime(2026, 11, 24, 17, 0)),
                'status': Forum.Status.PUBLISHED,
                'is_featured': True,
            },
        )
        business, _ = Venue.objects.update_or_create(
            forum=forum,
            name='ОЭЗ ТВТ «Томск»',
            defaults={'address': 'г. Томск, пр. Развития, 3, 6 этаж', 'is_published': True},
        )
        tpp, _ = Venue.objects.update_or_create(
            forum=forum,
            name='Союз «ТПП Томской области»',
            defaults={'address': 'г. Томск, ул. Красноармейская, 71а', 'is_published': True},
        )
        boiling, _ = Venue.objects.update_or_create(
            forum=forum,
            name='Точка кипения — Томск',
            defaults={'address': 'г. Томск, пр. Ленина, 26', 'is_published': True},
        )
        day1, _ = EventDay.objects.update_or_create(
            forum=forum,
            position=1,
            defaults={'date': datetime(2026, 11, 23).date(), 'title': 'День 1 · Предприятия и практика'},
        )
        day2, _ = EventDay.objects.update_or_create(
            forum=forum,
            position=2,
            defaults={'date': datetime(2026, 11, 24).date(), 'title': 'День 2 · Деловая программа'},
        )

        aliases = {
            'opening': ['Открытие и пленарная часть'],
            'seminar': ['Практический семинар'],
            'masterclass': ['Мастер-класс в Точке кипения'],
        }
        events = {}

        def event(day, slug, title, start, end, kind, policy, position, venue=business, **extra):
            obj = Event.objects.filter(day=day, slug=slug).first()
            if obj is None:
                names = [title] + aliases.get(slug, [])
                if kind == Event.Kind.ROUTE:
                    names.append(f'Маршрут №{position}')
                obj = Event.objects.filter(day=day, title__in=names).order_by('position').first()
            if obj is None:
                obj = Event(day=day)
            values = {
                'slug': slug,
                'title': title,
                'venue': venue,
                'kind': kind,
                'start_time': start,
                'end_time': end,
                'registration_policy': policy,
                'position': position,
                'is_published': True,
            }
            values.update(extra)
            for field, value in values.items():
                setattr(obj, field, value)
            if obj.curator_email == 'curator@example.invalid':
                obj.curator_email = ''
            obj.save()
            events[slug] = obj
            return obj

        event(
            day1, 'routes', 'Экскурсии на промышленные предприятия Томска и Томской области',
            time(9), time(17), Event.Kind.OTHER, Event.RegistrationPolicy.NONE, 0, venue=tpp,
            annotation='Шесть маршрутов с отправлением от Союза «ТПП Томской области» в 09:15. Можно выбрать только один маршрут.',
        )
        for index, enterprises in enumerate(ROUTES, start=1):
            route = event(
                day1, f'route-{index}', f'Маршрут {index}', time(9, 15), time(17),
                Event.Kind.ROUTE, Event.RegistrationPolicy.MODERATED, index, venue=tpp,
                annotation='Предприятия: ' + ', '.join(name for name, _ in enterprises) + '. Платная экскурсия, заявка отправляется куратору на модерацию.',
                is_paid=True,
                price='2500.00',
                payment_note='Оплата после звонка куратора. Заявка не является оплатой.',
                capacity_target=15,
            )
            for position, (name, description) in enumerate(enterprises, start=1):
                RouteEnterprise.objects.update_or_create(
                    event=route,
                    position=position,
                    defaults={'name': name, 'description': description},
                )
        event(
            day1, 'masterclass', 'Мастер-класс «Город четырёх комфортов»',
            time(16), time(18), Event.Kind.MASTERCLASS, Event.RegistrationPolicy.EXTERNAL, 10, venue=boiling,
            external_url='https://leader-id.ru/',
            annotation='Практическое занятие для студентов и детей. Регистрация проводится отдельно на Leader ID; адрес страницы мастер-класса уточняется организатором.',
        )
        event(day2, 'video', 'Видеоролик о туристическом потенциале Томской области', time(10), time(10, 3), Event.Kind.OTHER, Event.RegistrationPolicy.NONE, 0, annotation='Открытие деловой программы.')
        event(day2, 'opening', 'Открытие форума «Промышленный туризм как драйвер развития бизнеса и региона»', time(10, 5), time(11), Event.Kind.PLENARY, Event.RegistrationPolicy.AUTO, 1, annotation='Приветствие участников и представителей делового сообщества.')
        event(day2, 'awards', 'Награждение участников конкурса «Индустриальный код»', time(11), time(11, 30), Event.Kind.OTHER, Event.RegistrationPolicy.NONE, 2, annotation='Награждение лучших проектов Томской области в сфере промышленного туризма.')
        event(day2, 'fashion', 'Шоу-дефиле спецодежды и выступление танцевальной группы', time(11, 30), time(12), Event.Kind.OTHER, Event.RegistrationPolicy.NONE, 3, annotation='Презентация спецодежды с участием «Техноавиа».')
        event(day2, 'coffee', 'Кофе-брейк', time(12), time(12, 30), Event.Kind.OTHER, Event.RegistrationPolicy.NONE, 4, annotation='Перерыв и неформальное общение.')
        event(
            day2, 'seminar', 'Семинар «Инструменты повышения туристической привлекательности региона»',
            time(12, 30), time(14), Event.Kind.SEMINAR, Event.RegistrationPolicy.AUTO, 5,
            annotation='Разбор маршрутов на промышленные предприятия, охраны труда и промышленной безопасности. Инструменты для анализа потенциала региона, формирования предложения и продвижения в цифровых каналах.',
        )
        exchange = event(
            day2, 'exchange', 'Биржа субконтрактов',
            time(12, 30), time(14), Event.Kind.EXCHANGE, Event.RegistrationPolicy.MODERATED, 6,
            min_lot_selections=1,
            max_lot_selections=None,
            annotation='Переговоры потенциальных исполнителей с заказчиками по техническим запросам. Участие и выбранные лоты проходят модерацию.',
            description='Исполнитель выбирает лоты для переговоров. Заявка проходит модерацию.',
        )
        event(day2, 'lunch', 'Обед', time(14), time(15), Event.Kind.OTHER, Event.RegistrationPolicy.NONE, 7, annotation='Перерыв.')
        event(day2, 'strategy', 'Стратегическая сессия «Открываем города Сибири»', time(15), time(17), Event.Kind.SESSION, Event.RegistrationPolicy.AUTO, 8, annotation='Межрегиональное взаимодействие как инструмент развития промышленного туризма.')
        event(day2, 'quiz', 'Семейный квиз', time(15), time(17), Event.Kind.SESSION, Event.RegistrationPolicy.AUTO, 9, annotation='Мероприятие для родительских комитетов образовательных школ Томска.')
        event(day2, 'roundtable', 'Круглый стол: семейный бизнес', time(15), time(17), Event.Kind.SESSION, Event.RegistrationPolicy.AUTO, 10, annotation='Обсуждение развития семейных предприятий. Ведущая по программе: Дыбова Е. Н. (ТПП РФ).')

        morning, _ = ChoiceGroup.objects.update_or_create(
            day=day2,
            title='До обеда — одно событие',
            defaults={'min_selections': 0, 'max_selections': 1, 'position': 1},
        )
        for position, slug in enumerate(('seminar', 'exchange'), start=1):
            ChoiceGroupEvent.objects.get_or_create(group=morning, event=events[slug], defaults={'position': position})
        afternoon, _ = ChoiceGroup.objects.update_or_create(
            day=day2,
            title='После обеда — одно событие',
            defaults={'min_selections': 0, 'max_selections': 1, 'position': 2},
        )
        for position, slug in enumerate(('strategy', 'quiz', 'roundtable'), start=1):
            ChoiceGroupEvent.objects.get_or_create(group=afternoon, event=events[slug], defaults={'position': position})

        for position, (full_name, position_text, topic, photo, links) in enumerate(SPEAKERS, start=1):
            speaker, _ = Speaker.objects.update_or_create(
                forum=forum,
                full_name=full_name,
                defaults={
                    'credentials': position_text,
                    'topic': topic,
                    'static_photo': f'/img/promtour/speakers/{photo}.webp',
                    'position': position,
                    'is_published': True,
                },
            )
            for link_position, (slug, role) in enumerate(links, start=1):
                EventSpeaker.objects.update_or_create(
                    event=events[slug],
                    speaker=speaker,
                    defaults={'role': role, 'topic': topic, 'position': link_position},
                )

        Lot.objects.filter(event=exchange, technical_url='https://disk.yandex.ru/').update(is_published=False)
        self.stdout.write(self.style.SUCCESS(
            f'Промтур готов: {len(ROUTES)} маршрутов, {len(SPEAKERS)} спикеров, {Event.objects.filter(day__forum=forum, is_published=True).count()} событий.'
        ))
