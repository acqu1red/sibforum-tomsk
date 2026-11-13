# Сибирский форум

Витрина, программа промтура, регистрация участников, конкурс и панель организатора.

- Сайт: https://sibforum-tomsk.ru/
- Панель: https://admin.sibforum-tomsk.ru/admin/
- Django 5.2 / PostgreSQL 16 / Gunicorn / Nginx, статический HTML/CSS/JS.
- Пароли, SSH-ключи, базы и пользовательские загрузки в репозиторий не входят.

## Локальная разработка

Нужны Docker Compose и Node.js 20+ для подготовки статического HTML и версий CSS/JS. В клиентской части нет npm-зависимостей.

```sh
npm run build
docker compose -f docker-compose.backend.yml up -d --build db mail backend worker
docker compose up -d --build
```

Сайт: http://localhost:8095/. Панель: http://admin.localhost:8100/admin/. Письма разработки: http://localhost:8026/.

Создание руководителя для новой локальной базы:

```sh
docker compose -f docker-compose.backend.yml exec backend python manage.py createsuperuser --username director
```

Руководитель создаёт сотрудников в разделе **Сотрудники** и выбирает роль. Управлять аккаунтами и ролями может только `director`, включая случай наличия другого superuser. TOTP в текущем размещении отключён по запросу владельца; включается через `ADMIN_TOTP_REQUIRED=1`.

## Размещение и обновления

1. Заполнить `deploy/production.env.example` вне проекта: `/etc/sibforum/production.env`, права 600.
2. Установить SSH-ключ оператора и настроить DNS основного и административного домена.
3. Передать исходники: `bash deploy/upload.sh root@server [путь-к-ключу]`.
4. Первый запуск: `bash deploy/production.sh bootstrap`, затем `bash deploy/production.sh https` на сервере.
5. Обновления: `bash deploy/production.sh update`. Скрипт создаёт резервную копию перед заменой контейнеров.

Каталог из `deploy/catalog.json` импортируется один раз в новую базу. Повторный импорт при обычных обновлениях не выполняется. Личные данные и аккаунты разработки в нём отсутствуют.

Текущая публикация использует `PUBLIC_SUBMISSIONS_ENABLED=0`: программа и конкурс доступны для просмотра, отправка заявок и голосов закрыта до подключения почты и SmartCaptcha. Открытие форм проходит проверку конфигурации в `deploy/production.sh`.

## Проверки

```sh
docker build -t siberianforum-backend:deploycheck backend
docker run --rm -e DEBUG=0 -e SECRET_KEY=test-only-not-a-production-key -e SQLITE_PATH=/tmp/test.sqlite3 \
  -v "$PWD/backend:/app:ro" siberianforum-backend:deploycheck \
  python manage.py test accounts forums voting
```

Проверки создают отдельную тестовую БД. Сценарии тестируют управление аккаунтами, отключаемый TOTP, права ролей, закрытые API, фильтрацию скрытого контента, SQL-запросы и ошибки SmartCaptcha.

- [Работа с сайтом через панель организатора](docs/content-editor-guide.md).
- [Требования и ответы от 13 ноября](docs/requirements-and-answers-2026-11-13.md).
- [Аудит выпуска 13 ноября](docs/release-audit-2026-11-13.md).
- [Аудит производительности, методика и результаты](docs/performance-audit-2026-11-11.md).
- [Порядок размещения, резервного копирования и восстановления](docs/production-runbook.md).
- [Первичный анализ проекта](docs/deployment-audit-2026-11-11.md).

Лицензии локальных шрифтов Onest и Montserrat находятся в `site/fonts/`.
