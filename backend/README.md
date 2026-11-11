# Backend платформы «Сибирский форум»

Django 5.2 LTS + PostgreSQL 16. Реализованы форумы, программа, площадки, события, choice groups, лоты, участники, заявки, email challenge, личные ссылки, модерация, история решений, согласия и notification outbox.

Действующий ESG-прототип сохранён. Новый frontend промтура находится в `site/promtour/` и работает через этот backend.

## Запуск через Docker

Из корня проекта:

```bash
docker compose -f docker-compose.backend.yml up -d --build
docker compose -f docker-compose.yml up -d --build
```

Адреса:

- текущая витрина: http://localhost:8095/;
- промтур: http://localhost:8095/promtour/;
- backend API: http://localhost:8100/api/v1/health/;
- админка: http://admin.localhost:8100/admin/. На основном хосте `/admin/` и `/api/v1/admin/` возвращают 404; отдельный вход на сайте форума не нужен.

Проекты `siberianforum-platform` и `siberianforum-proto` не удаляют и не останавливают контейнеры друг друга. `server/server.py` проксирует `/api/v1/*` и `/media/*` с порта 8095 на backend 8100. Старые `/api/register`, `/api/confirm` и остальные демо-endpoints остаются для ESG.

## Локальный тестовый контент

Только при `DEBUG=1` можно создать или обновить программу промтура:

```bash
docker compose -f docker-compose.backend.yml exec backend python manage.py seed_promtour_dev
```

Seed создаёт два дня 23–24.11.2026, шесть платных маршрутов с 19 предприятиями, 19 событий, 13 спикеров, площадки и группы выбора. Тестовые лоты с общей ссылкой на Яндекс Диск скрыты. Реальные лоты, ссылки на технические материалы и email кураторов нужно добавить через админку. Конкретная страница мастер-класса на Leader ID в источниках пока отсутствует.

## Администраторы

```bash
docker compose -f docker-compose.backend.yml exec backend python manage.py createsuperuser
```

Для каждого сотрудника создаётся отдельная учётная запись. Общий логин и пароль не используются.

После первого входа с паролем администратор настраивает TOTP в приложении-аутентификаторе. Страница `/admin/2fa/setup/` показывает QR и ключ для ручного ввода. Последующие входы требуют код на `/admin/2fa/verify/`.

QR и Base32-ключ совместимы с Google Authenticator, Microsoft Authenticator и Яндекс.Ключом. Отдельный OAuth или IP-whitelist не требуется.

Доступ к `/admin/` и `/api/v1/admin/` разрешён только с `ADMIN_HOSTS`; на основном домене возвращается 404. Попытки входа ограничены 20 на IP за 10 минут, admin-сессия — 30 минут с продлением при активности. `sitemap.xml` на admin-хосте отсутствует, `robots.txt` запрещает индексацию, `X-Robots-Tag` содержит `noindex`. Это дополнение к авторизации, а не её замена.

- TOTP — шесть цифр, период 30 секунд, допустимый сдвиг один период.
- Повторное использование одного кода запрещено.
- После пяти ошибок ввод блокируется на пять минут.
- Staff API без подтверждённого второго фактора возвращает `401 two_factor_required`.
- Секрет хранится в подписанном виде и не отображается в админке после настройки.

В админке доступны форумы, события, предприятия маршрутов, спикеры и их участие в событиях, фотографии, лоты, заявки и решения модерации. Подтверждение, отказ и отмена доступны действиями. Перевод выполняется действием «Перевести выбранную заявку на другой маршрут» с экраном выбора цели и комментария; staff API с целевым событием также сохранён.

## API

Публичные read-only:

```text
GET /api/v1/health/
GET /api/v1/forums/
GET /api/v1/forums/<slug>/program/
```

Регистрация:

```text
POST /api/v1/registrations/submit/
POST /api/v1/registrations/verify/
GET  /api/v1/registration/?t=<personal-token>
```

Staff-only:

```text
GET  /api/v1/admin/registrations/
POST /api/v1/admin/registration-items/<uuid>/decision/
```

Staff API использует Django session и CSRF. Неавторизованный запрос получает 401, недостаточно прав — 403.

## Правила регистрации

- Обычное событие после подтверждения email становится `confirmed`.
- Маршрут и биржа становятся `pending_review`, затем администратор меняет статус.
- До подтверждения email личный token не выдаётся и существующая заявка не изменяется.
- Token хранится только как SHA-256 hash; исходное значение выдаётся один раз после проверки кода.
- Пересекающиеся события и превышение choice group отклоняются сервером.
- Лоты должны принадлежать выбранной бирже и проходить min/max.
- Решения модератора и переводы сохраняются в истории.
- Формата участия и ИНН в модели нет.

## Доставка писем

Worker запускается вместе с `docker-compose.backend.yml` и обрабатывает `NotificationOutbox` через SMTP. Для локальной проверки используется Mailpit:

- интерфейс писем: http://localhost:8026/;
- SMTP внутри Docker-сети: `mail:1025`;
- SMTP с хоста: `localhost:1026`.

Ручная обработка одной партии:

```bash
docker compose -f docker-compose.backend.yml exec backend python manage.py process_notifications --once
```

Worker использует PostgreSQL `SKIP LOCKED`, повторяет ошибки до пяти раз с backoff и восстанавливает зависшие отправки. После доставки код подтверждения и личный URL удаляются из payload. Ошибочные письма можно вернуть в очередь действием в админке.

Для production задаются `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` или `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL`, `PUBLIC_SITE_URL`. `DEBUG=0` отключает `debug_code`. До production-запуска нужны SPF, DKIM и DMARC для домена отправителя.

## Электронный билет и чек-ин

После подтверждения хотя бы одного обычного или одобренного модерируемого события создаётся `Ticket` с отдельным UUID. Личный token и QR — разные идентификаторы: QR открывает только staff-страницу чек-ина и не даёт изменить заявку.

- Личная страница `/promtour/?t=...` показывает QR и кнопку скачивания PDF.
- `GET /api/v1/tickets/<uuid>/qr.png?t=<personal-token>` возвращает PNG.
- `GET /api/v1/tickets/<uuid>/ticket.pdf?t=<personal-token>` возвращает PDF A4 с кириллицей, событиями и QR.
- Письма `registration_summary` и `moderation_decision` содержат PDF и PNG во вложении.
- До одобрения модерируемой заявки билета нет. При отмене всех допустимых событий билет отзывается, а его endpoints перестают работать.
- При повторном выпуске создаётся новый UUID, прежний QR остаётся недействительным.

Сканер: http://admin.localhost:8100/admin/check-in/. Требуется staff-вход и TOTP. Можно сканировать камерой через `BarcodeDetector` или ввести UUID/содержимое QR вручную. Прибытие записывается в `CheckIn`; уникальное ограничение БД не даёт создать повторную отметку.

`ADMIN_SITE_URL` определяет адрес, зашитый в QR. В production это `https://admin.sibforum-tomsk.ru`, доступный телефонам стойки; публичная личная ссылка остаётся на `PUBLIC_SITE_URL`. `PDF_FONT_PATH` указывает на DejaVu Sans, который уже установлен в Docker-образ. Реальные камеры и браузеры на площадке нужно проверить отдельным полевым тестом.

## Конкурс и голосование

Страница: http://localhost:8095/contest/

Реализованы:

- восемь номинаций и кандидаты с описаниями из `контент/Номинации  03.11.2026.docx`;
- один подтверждённый email = один бюллетень;
- пропуск любой номинации и настраиваемые min/max;
- email verification с пятью попытками и кодом на 20 минут;
- rate limit по IP и необязательная Yandex SmartCaptcha (`YANDEX_SMARTCAPTCHA_SECRET`);
- публикация итогов отдельным действием в админке;
- staff-only статистика и CSV только с агрегатами, без email и ответов «кто за кого»;
- SMTP-письма с кодом и подтверждением голосования.

Импорт номинаций из DOCX:

```bash
docker compose -f docker-compose.backend.yml exec backend python manage.py import_contest_docx "/content/Номинации  03.11.2026.docx"
```

В Git Bash при необходимости добавьте `MSYS_NO_PATHCONV=1` перед командой. Папка `контент/` монтируется в контейнер read-only в `/content`.

Staff endpoints:

```text
GET /api/v1/admin/contests/<slug>/stats/
GET /api/v1/admin/contests/<slug>/export.csv
```

Публичные результаты доступны только после `results_published=True`. До этого они скрыты. Полная anti-fraud защита зависит от выбранной модели: сейчас email + rate limit, внешняя SmartCaptcha требует реального ключа и отдельной проверки.

## Защищённые выгрузки XLSX/CSV

Страница для сотрудника: http://admin.localhost:8100/admin/exports/ — требуется staff-вход и TOTP.

Доступны:

- общая выгрузка регистраций;
- фильтры по событию и статусу;
- режим `items`: строка на событие участника;
- режим `summary`: строка на человека со всеми его событиями;
- XLSX с листами участников, статистики событий и метаданных;
- агрегированная статистика голосования в CSV и XLSX;
- журнал `ExportLog` с администратором, фильтрами, именем файла, числом строк и временем;
- защита от Excel-формул в пользовательских значениях;
- `Cache-Control: no-store` и обязательная авторизация.

API:

```text
GET /api/v1/admin/registrations/export.csv
GET /api/v1/admin/registrations/export.xlsx
GET /api/v1/admin/contests/<slug>/export.csv
GET /api/v1/admin/contests/<slug>/export.xlsx
```

Параметры регистраций: `forum`, `event`, `status`, `mode=items|summary`. Все выгрузки строятся из PostgreSQL и не требуют внешней CRM.

## Production-like режим и защита форм

Дополнительный сервис `backend-prod` работает на http://localhost:8101/ через Gunicorn и WhiteNoise. Он использует PostgreSQL, статические файлы через `collectstatic`, 4 workers × 8 threads и `DEBUG=0`.

- `backend` на 8100 — development runserver.
- `backend-prod` на 8101 — production-like проверка нагрузки и безопасности.
- Публичные submit/verify регистрации имеют rate limit по IP и опциональную Yandex SmartCaptcha.
- Голосование имеет отдельный rate limit.
- Старый `/api/export.csv` требует `LEGACY_EXPORT_TOKEN` в `X-Export-Token`; без него возвращает 401. Основной путь — защищённый `/admin/exports/` и staff API.
- Повторная заявка по существующему email не выдаёт token до подтверждения. Изменения применяются только после кода; подтверждение поддерживает `id` или `token`.

Проверено: 500 одновременных API-запросов при 100 клиентах с keep-alive, все успешны, p95 = 3,828 с. Для production обязательны настоящие `SECRET_KEY`, HTTPS, SMTP, SmartCaptcha, SPF/DKIM/DMARC и отдельный restore drill.

## Backup и production

Ежедневный сервис `backup` создаёт комплект `backup-<timestamp>.json` и `backup-<timestamp>-media.tar.gz` и хранит последние 14 комплектов. В архив включаются загруженные фотографии из `MEDIA_ROOT`, volume `platform-media` доступен сервису backup в read-only режиме. Системные `contenttypes` и `auth.permission` исключены из дампа, чтобы не конфликтовать с миграциями.

```bash
docker compose -f docker-compose.backend.yml exec backend python manage.py backup_data --dir /app/backups
```

Восстановление требует явного подтверждения и должно выполняться только после отдельного restore drill:

```bash
RESTORE_CONFIRM=1 docker compose -f docker-compose.backend.yml exec backend python manage.py restore_data /app/backups/backup-YYYYMMDD-HHMMSS.json
```

При наличии одноимённого TAR.GZ восстанавливаются и media-файлы с безопасной распаковкой. Проверено восстановление на отдельной временной БД: 8 номинаций, 79 кандидатов, 6 маршрутов, 13 спикеров и media-файл. Не запускайте `restore_data` на рабочей БД без окна обслуживания и нового backup.

Production-конфигурация находится в `docker-compose.prod.yml`, Nginx — в `deploy/nginx.conf`, инструкция — `docs/production-runbook.md`. Она требует обязательные секреты вне репозитория, DNS, SMTP и SmartCaptcha.

## Остановка

```bash
docker compose -f docker-compose.backend.yml down
docker compose -f docker-compose.yml down
```

PostgreSQL сохраняется в именованном volume `siberianforum-platform_platform-postgres`. Команда `down` его не удаляет. Не используйте `down -v`, если данные нужны.

## Запуск вне Docker

Требуется Python 3.12+:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DEBUG=1
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 8100
```

На Windows используйте `.venv/Scripts/python`; в cmd перед командами Django выполните `set DEBUG=1`. Без `POSTGRES_HOST` применяется SQLite только для локальной разработки. Docker-сценарий использует PostgreSQL.

## Что ещё не готово

Полная миграция ESG, production-деплой и подключение production SmartCaptcha с реальным ключом. Текущий compose предназначен для разработки, а не для production. По решению заказчика внешняя CRM-интеграция не требуется: заявки обрабатываются в админке и через XLSX/CSV-выгрузки.
