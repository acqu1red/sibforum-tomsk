# Production runbook — Сибирский форум

> Обновление от 11.11.2026: руководитель — `director`; TOTP временно отключён по запросу владельца. Текущее состояние производительности и интерфейса описано в [аудите оптимизации](performance-audit-2026-11-11.md). Пароль хранится вне репозитория.
Документ описывает запуск production-конфигурации без секретов в репозитории. `docker-compose.prod.yml` использует отдельный проект `siberianforum-production` и не заменяет development-контейнеры.

## Размещённый сервер — 11 ноября 2026

- IPv4: `179.252.220.7`, Ubuntu 24.04.5 LTS.
- Исходники: `/opt/sibforum`; env: `/etc/sibforum/production.env` (600).
- С Mac подключение: `ssh sibforum-timeweb`. Алиас использует существующий ключ и направляет только это SSH-соединение через Wi-Fi `en0`, обходя VPN. При смене сетевого интерфейса proxy потребует корректировки; глобальные маршруты не менялись.
- Загрузка исходников: `bash deploy/upload.sh root@sibforum-timeweb`.
- Обновление: `ssh sibforum-timeweb 'cd /opt/sibforum && bash deploy/production.sh update'`.
- Единственный руководитель: `director`; пароль сохранён вне исходников в `~/.codex/credentials/sibforum-admin.txt`, TOTP нужно настроить при первом входе.
- Первая копия данных вне VPS: `~/.codex/backups/sibforum/initial-2026-11-11.tar.gz` (600). Автоматический backup раз в сутки хранит последние 14 комплектов на VPS; регулярную внешнюю репликацию ещё нужно подключить.
- HTTPS для обоих доменов выпущен; проверены dry-run продления и systemd service с reload.
- Старый сервер `201.51.28.86` не удалён.

## 1. Что подготовить заказчику

- Домен и admin-поддомен: DNS A/AAAA-записи `${DOMAIN}` и `${ADMIN_DOMAIN}` на production-сервер.
- Сервер в РФ с Docker и открытыми портами 80/443.
- Для первого этапа сайт и админка могут работать с `PUBLIC_SUBMISSIONS_ENABLED=0`: новые заявки и подтверждения голосов возвращают 503 с понятным сообщением. Для открытия форм нужны действующие SMTP и SmartCaptcha.
- SMTP: хост, порт, логин/пароль, `DEFAULT_FROM_EMAIL`, SPF/DKIM/DMARC.
- Yandex SmartCaptcha: `YANDEX_SMARTCAPTCHA_SECRET` и `YANDEX_SMARTCAPTCHA_CLIENT_ID`.
- Юридическое утверждение документов в `site/legal/`.
- Три индивидуальных администратора и TOTP-приложение для каждого.
- Политика хранения ПДн и резервных копий, канал удаления/восстановления доступа.
- Реальные телефоны стойки и тестовая площадка для QR.
- Правильная итоговая программа промтура. PDF с именем итоговой программы 09.11 при рендере оказался другим форумом РЦИС на 11.11; использовать его для промтура нельзя. Подробности — `docs/frontend-acceptance.md`.
- Конкретная страница мастер-класса на Leader ID, реальные лоты, https-ссылки на ТЗ и email кураторов. Фотография Горбулицкой уже добавлена из `контент/gorbulitscaya.jpg`.

## 2. Переменные окружения

Создайте защищённый файл **вне репозитория**, например `/etc/sibforum/production.env`. Не помещайте его в каталог проекта и не прикладывайте в чат/репозиторий.

```bash
SECRET_KEY=replace_with_long_random_value
POSTGRES_PASSWORD=replace_with_strong_database_password
DOMAIN=sibforum-tomsk.ru
ADMIN_DOMAIN=admin.sibforum-tomsk.ru
BIND_IP=0.0.0.0
PUBLIC_SUBMISSIONS_ENABLED=0
EMAIL_HOST=smtp.example.ru
EMAIL_PORT=587
EMAIL_HOST_USER=forum@example.ru
EMAIL_HOST_PASSWORD=replace_with_smtp_password
DEFAULT_FROM_EMAIL=forum@example.ru
YANDEX_SMARTCAPTCHA_SECRET=replace_with_server_secret
YANDEX_SMARTCAPTCHA_CLIENT_ID=replace_with_public_client_id
TLS_EMAIL=admin@example.ru
```

`SECRET_KEY` сгенерируйте отдельно: `python -c "import secrets; print(secrets.token_urlsafe(50))"`. Не используйте development key.

Перед запуском:

```bash
docker compose --env-file /etc/sibforum/production.env -f docker-compose.prod.yml config --quiet
docker compose --env-file /etc/sibforum/production.env -f docker-compose.prod.yml build
bash deploy/production.sh bootstrap /etc/sibforum/production.env
```

Compose требует `SECRET_KEY`, `POSTGRES_PASSWORD` и `DOMAIN`. `TLS_EMAIL` необязателен: без него Certbot регистрирует ACME-аккаунт без контактной почты; продление выполняет systemd-таймер. SMTP и SmartCaptcha можно оставить пустыми только на этапе закрытых форм (`PUBLIC_SUBMISSIONS_ENABLED=0`, значение по умолчанию). Этот же флаг управляет отображением закрытых форм через `/deployment-config.json` (без кеширования); при открытии не нужно отдельно править HTML. `deploy/production.sh` проверяет наличие этих параметров перед запуском с открытыми формами. `ADMIN_DOMAIN` по умолчанию задан как `admin.sibforum-tomsk.ru` (без `https://` и пути). Секреты не выводите через обычный `docker compose config`: используйте `config --quiet`.

Полный путь для Timeweb: `/opt/sibforum`, защищённый env-файл: `/etc/sibforum/production.env`, права 600. Исходники загружаются с локального компьютера командой `bash deploy/upload.sh root@201.51.28.86`. Скрипт передаёт только backend, сайт и deploy-конфигурацию; базы разработки, SSH-ключи, профили браузера и документы заказчика не передаются.

## 3. HTTPS и certbot

1. Убедитесь, что `${DOMAIN}` и `${ADMIN_DOMAIN}` указывают на сервер и порт 80 доступен снаружи. Нужны DNS A/AAAA-записи для обоих имён; admin-поддомен не добавляется в sitemap.
2. Команда `bootstrap` из предыдущего раздела поднимает HTTP-конфигурацию: ACME-файлы доступны, остальные URL временно возвращают 503. Получите общий SAN-сертификат и переключите Nginx на HTTPS:

   ```bash
   bash deploy/production.sh https /etc/sibforum/production.env
   ```

3. Certbot вызывается с `-d ${DOMAIN} -d ${ADMIN_DOMAIN}`. Один сертификат `/etc/letsencrypt/live/${DOMAIN}/` используется обоими HTTPS virtual hosts; отдельный каталог `live/${ADMIN_DOMAIN}` не требуется.
4. Проверьте `https://${DOMAIN}/api/v1/health/` и `https://${ADMIN_DOMAIN}/admin/`. На основном домене `/admin/` должен возвращать 404, на admin-домене — страницу входа.
5. Certbot использует webroot `/var/lib/letsencrypt`, общий с Nginx. Порт 80 не требуется освобождать. Для продления используйте `bash deploy/production.sh renew /etc/sibforum/production.env`: скрипт также проверяет и перезагружает Nginx.
6. На сервере с проектом в `/opt/sibforum` установите таймер:

   ```bash
   install -m 644 deploy/sibforum-certbot.service deploy/sibforum-certbot.timer /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now sibforum-certbot.timer
   systemctl list-timers sibforum-certbot.timer
   ```

`bootstrap` предназначен только для первого запуска без сертификата. Для обновлений используйте `bash deploy/production.sh update /etc/sibforum/production.env`: сначала сборка и backup, затем остановка worker/backup на время смены backend и перезагрузка Nginx.

### Первичное наполнение

`deploy/catalog.json` содержит только публичный каталог: 1 форум, 19 событий, 13 спикеров, 19 предприятий, 8 номинаций и 79 кандидатов. Он подготовлен из `seed_promtour_dev` и исходного DOCX номинаций в отдельной локальной БД. Участники, заявки, бюллетени, пользователи, TOTP и письма в него не входят. Текущая редакция программы по-прежнему требует проверки организатором, описанной в `docs/frontend-acceptance.md`.

Импортировать только один раз в новую production-БД, после `bootstrap`:

```bash
docker compose --env-file /etc/sibforum/production.env -f docker-compose.prod.yml cp deploy/catalog.json backend-prod:/tmp/catalog.json
docker compose --env-file /etc/sibforum/production.env -f docker-compose.prod.yml exec -T backend-prod python manage.py loaddata /tmp/catalog.json
```

Повторный импорт перезаписывает каталог; не включайте его в обычное обновление. После импорта создайте индивидуальные учётные записи через `createsuperuser` и настройте TOTP при входе. Не переносите администраторов из БД разработки.

## 4. Проверка после запуска

- `https://${DOMAIN}/api/v1/health/` возвращает 200.
- `https://${DOMAIN}/admin/` и `https://${DOMAIN}/api/v1/admin/` возвращают 404.
- `https://${ADMIN_DOMAIN}/admin/` требует пароль и TOTP; создайте администраторов отдельными командами `createsuperuser`.
- `https://${ADMIN_DOMAIN}/admin/check-in/` работает по HTTPS на телефонах сотрудников.
- `https://${ADMIN_DOMAIN}/robots.txt` возвращает `Disallow: /`, `sitemap.xml` на admin-домене — 404, заголовок `X-Robots-Tag` — `noindex`.
- `/contest/` загружает номинации и SmartCaptcha.
- При `PUBLIC_SUBMISSIONS_ENABLED=0` отправка заявок/голосов и проверка email-кодов закрыты на обоих доменах. После настройки почты и капчи установите `PUBLIC_SUBMISSIONS_ENABLED=1`, примените `update` и проверьте реальную доставку кодов.
- `/esg2026/register.html` и `/esg2026/my.html` в production закрыты: эти страницы используют демонстрационную модель с localStorage. Витрина и программа ESG доступны для просмотра.
- `https://${ADMIN_DOMAIN}/admin/exports/` доступен только после staff + TOTP.
- Письмо с кодом реально доходит в Gmail, Яндекс Почту и Mail.ru.
- PDF и QR открываются на телефоне, ссылка в QR ведёт на `ADMIN_SITE_URL`.
- Старый `/api/export.csv` не используется; если нужен, задайте отдельный `LEGACY_EXPORT_TOKEN` вне репозитория.

## 5. Backup и restore

Сервис `backup` ежедневно создаёт `backup-<timestamp>.json` и `backup-<timestamp>-media.tar.gz` и хранит последние 14 комплектов в volume `production-backups`. База и фотографии спикеров сохраняются вместе; `production-media` подключён к сервису backup в read-only режиме. Системные `contenttypes` и `auth.permission` исключены из дампа, чтобы восстановление не конфликтовало с миграциями.

Проверка восстановления обязательна на отдельной БД перед реальными ПДн и затем регулярно:

```bash
docker compose --env-file /etc/sibforum/production.env -f docker-compose.prod.yml exec backend-prod python manage.py backup_data --dir /app/backups
```

Для восстановления используйте отдельную staging-БД. Не выполняйте `restore_data` на рабочей БД без окна обслуживания и нового backup.

```bash
docker compose --env-file /etc/sibforum/production.env -f docker-compose.prod.yml exec -e RESTORE_CONFIRM=1 backend-prod python manage.py restore_data /app/backups/backup-YYYYMMDD-HHMMSS.json
```

При наличии одноимённого `backup-<timestamp>-media.tar.gz` команда также восстанавливает media в `MEDIA_ROOT`. Распаковка использует защищённый фильтр tar-файлов. Зафиксируйте фактическое время восстановления и проверьте не только число записей, но и доступность фотографий. Требование: не более 4 часов.

## 6. Приёмка перед открытием

- Программа и шесть маршрутов совпадают с актуальными источниками.
- Двойной выбор маршрута невозможен и в UI, и через API.
- Заявки на маршруты и биржу идут на модерацию, обычные подтверждаются.
- Письма, PDF, QR, личная ссылка и статусы работают в одном цикле.
- Повторный голос с того же email не засчитывается, пропуск номинаций разрешён, статистика только агрегированная.
- Нет демо-данных, debug_code, открытых exports, `href="#"` и старой публичной уязвимости повторной регистрации.
- Все обязательные поля и документы юридически утверждены, согласия имеют версию.
- 360/768/1280/1920 px, клавиатура, контраст и последние браузеры проверены.
- 500 одновременных запросов проходят без ошибок и без дублей.
- Restore drill завершён успешно, мониторинг и дежурный назначены.

## 7. Rollback

- Перед релизом сохраните прежний образ, backup и список DNS-изменений.
- Остановите приём новых форм через конфигурацию, не удаляя уже принятые заявки.
- Выполните откат на прежний образ/контейнеры, сохранив PostgreSQL volume.
- Верните прежний static-контент, если это требуется, и проверьте health/личные ссылки.
- Не удаляйте volumes `production-postgres`, `production-backups` и `production-media` во время rollback. Откат базы без соответствующего media может оставить битые ссылки на фотографии.

## 8. Что нельзя сделать без заказчика

- Реальные DNS, внешний SMTP, production SmartCaptcha, юридическое утверждение и финальное наполнение.
- Полевой тест камер и сети на площадке.
- Проверка доставки писем в реальные почтовые системы и окончательная оценка спам-фильтров.
