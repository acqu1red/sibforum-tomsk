"""Локальный сервер прототипа «Сибирский форум»: раздаёт сайт из ../site и принимает регистрации.

Только стандартная библиотека Python 3.9+. Данные — в server/data (или в DATA_DIR):
  registrations.json  — заявки (участник, выбранные события, согласия, статус подтверждения)
  crm_outbox.jsonl    — очередь передачи в Битрикс24 (в прототипе — имитация)

/api/v1/* проксируется на новый Django backend (PLATFORM_BACKEND_URL, по умолчанию http://127.0.0.1:8100).

Запуск:  python server/server.py [--port 8095] [--host 127.0.0.1] [--open]
"""
import argparse
import csv
import io
import json
import os
import re
import secrets
import sys
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urllib_error, request as urllib_request
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
SITE = Path(os.environ.get('SITE_DIR', ROOT.parent / 'site'))
DATA = Path(os.environ.get('DATA_DIR', ROOT / 'data'))
REG_FILE = DATA / 'registrations.json'
OUTBOX = DATA / 'crm_outbox.jsonl'
PLATFORM_BACKEND_URL = os.environ.get('PLATFORM_BACKEND_URL', 'http://127.0.0.1:8100').rstrip('/')

FORUM = 'esg2026'  # форум по умолчанию; сайт каждого форума присылает свой id (data/forum.js)
FORUM_ID = re.compile(r'^[a-z0-9-]{2,40}$')
CONSENT_VERSION = '1.0 от 01.03.2026'  # заглушка: текст и версию согласия даёт юрист заказчика
MAX_BODY = 64 * 1024

# Экскурсии: лимит мест и сколько занято до запуска прототипа (как в site/js/program-data.js)
EXCURSIONS = {
    'd4-x1': {'limit': 20, 'taken': 16},
    'd4-x2': {'limit': 25, 'taken': 13},
    'd4-x3': {'limit': 15, 'taken': 15},
    'd4-x4': {'limit': 30, 'taken': 12},
}
CATEGORY_NAMES = {'business': 'Бизнес', 'plant': 'Промышленное предприятие', 'university': 'Вуз', 'school': 'Школа, колледж',
                  'government': 'Орган власти', 'media': 'СМИ', 'other': 'Другое'}
CATEGORIES = set(CATEGORY_NAMES)
TOMSK = timezone(timedelta(hours=7))
FORMATS = {'offline', 'online'}
EVENT_ID = re.compile(r'^d[1-5]-[a-z0-9-]{1,20}$')
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$')

lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def load():
    if not REG_FILE.exists():
        return []
    return json.loads(REG_FILE.read_text(encoding='utf-8'))


def save(regs):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = REG_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(regs, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, REG_FILE)


def crm_queue(reg, action):
    """Имитация передачи в Битрикс24: запись в очередь; при сбое CRM заявка досылается из очереди."""
    DATA.mkdir(parents=True, exist_ok=True)
    with OUTBOX.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'at': now(), 'reg': reg['id'], 'action': action, 'status': 'queued'}, ensure_ascii=False) + '\n')


def clean_str(v, limit):
    return re.sub(r'\s+', ' ', str(v or '')).strip()[:limit]


def validate(payload):
    """Возвращает (данные, ошибки). Правила совпадают с проверкой в форме (site/js/register.js)."""
    p = payload.get('person') or {}
    events = payload.get('events') or []
    consents = payload.get('consents') or {}
    e = {}
    person = {
        'name': clean_str(p.get('name'), 120),
        'email': clean_str(p.get('email'), 120).lower(),
        'phone': re.sub(r'\D', '', str(p.get('phone') or '')),
        'org': clean_str(p.get('org'), 200),
        'position': clean_str(p.get('position'), 200),
        'category': clean_str(p.get('category'), 20),
        'format': clean_str(p.get('format'), 20),
        'city': clean_str(p.get('city'), 100),
        'inn': re.sub(r'\D', '', str(p.get('inn') or '')),
        'source': clean_str(p.get('source'), 100),
        'comment': clean_str(p.get('comment'), 1000),
        'birth_date': clean_str(p.get('birth_date'), 10),
        'citizenship': clean_str(p.get('citizenship'), 40),
    }
    if len(person['name'].split(' ')) < 2:
        e['name'] = 'Укажите фамилию и имя'
    if not EMAIL.match(person['email']):
        e['email'] = 'Проверьте адрес почты'
    if person['phone'].startswith('8') and len(person['phone']) == 11:
        person['phone'] = '7' + person['phone'][1:]
    if not (len(person['phone']) == 11 and person['phone'].startswith('7')):
        e['phone'] = 'Нужен номер из 11 цифр, например +7 (999) 123-45-67'
    if not person['org']:
        e['org'] = 'Укажите организацию'
    if not person['position']:
        e['position'] = 'Укажите должность'
    if person['category'] not in CATEGORIES:
        e['category'] = 'Выберите категорию'
    if person['format'] not in FORMATS:
        e['format'] = 'Выберите формат участия'
    if person['inn'] and len(person['inn']) not in (10, 12):
        e['inn'] = 'ИНН — 10 или 12 цифр'
    if not isinstance(events, list) or not events or len(events) > 60:
        e['events'] = 'Выберите хотя бы одно событие'
        events = []
    events = list(dict.fromkeys(ev for ev in events if isinstance(ev, str) and EVENT_ID.match(ev)))
    if any(ev in EXCURSIONS for ev in events):
        if person['format'] == 'online':
            e['format'] = 'Экскурсии доступны только при очном участии'
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', person['birth_date']):
            e['birth_date'] = 'Для прохода на предприятие нужна дата рождения'
        if not person['citizenship']:
            e['citizenship'] = 'Укажите гражданство'
    if consents.get('pd') is not True:
        e['pd'] = 'Без согласия на обработку персональных данных регистрация невозможна'
    if consents.get('policy') is not True:
        e['policy'] = 'Подтвердите, что ознакомились с политикой'
    return person, events, consents, e


def seat_state(regs, exclude_id=None):
    """Свободные места и очередь по каждой экскурсии."""
    state = {}
    for ex, cfg in EXCURSIONS.items():
        confirmed = sum(1 for r in regs if r['id'] != exclude_id and r['events'].get(ex, {}).get('status') == 'confirmed')
        waiting = sum(1 for r in regs if r['id'] != exclude_id and r['events'].get(ex, {}).get('status') == 'waitlist')
        state[ex] = {'limit': cfg['limit'], 'left': max(0, cfg['limit'] - cfg['taken'] - confirmed), 'waitlist': waiting}
    return state


def apply_events(regs, reg, wanted):
    """Обновляет выбор событий; места на экскурсиях выдаются по порядку, остальные — в лист ожидания."""
    seats = seat_state(regs, exclude_id=reg['id'])
    old = reg.get('events', {})
    new = {}
    for ev in wanted:
        if ev in EXCURSIONS:
            prev = old.get(ev)
            if prev and prev['status'] == 'confirmed':
                new[ev] = prev
            elif seats[ev]['left'] > 0:
                new[ev] = {'status': 'confirmed', 'at': now()}
                seats[ev]['left'] -= 1
            else:
                new[ev] = prev if prev else {'status': 'waitlist', 'at': now(), 'queue': seats[ev]['waitlist'] + 1}
        else:
            new[ev] = old.get(ev) or {'status': 'confirmed', 'at': now()}
    reg['events'] = new


def by_token(regs, token):
    """Поиск по личной ссылке; сравнение за постоянное время (compare_digest принимает только ASCII)."""
    if not token or not token.isascii():
        return None
    return next((r for r in regs if secrets.compare_digest(r['token'], token)), None)


def public(reg):
    return {
        'id': reg['id'], 'token': reg['token'], 'forum': reg['forum'],
        'person': {k: reg['person'][k] for k in ('name', 'email', 'phone', 'org', 'position', 'category', 'format', 'city')},
        'events': reg['events'], 'confirmed': bool(reg.get('confirmed_at')),
        'created_at': reg['created_at'], 'updated_at': reg['updated_at'],
    }


class Server(ThreadingHTTPServer):
    # На Windows SO_REUSEADDR позволяет второму процессу занять уже занятый порт без ошибки —
    # два сервера начинают отвечать на одном адресе вперемешку. Без него занятый порт обнаруживается сразу.
    allow_reuse_address = os.name != 'nt'
    daemon_threads = True


def mask_email(email):
    name, _, domain = email.partition('@')
    return (name[:2] + '•' * max(1, len(name) - 2)) + '@' + domain


class Handler(SimpleHTTPRequestHandler):
    server_version = 'SiberianForumProto/1.0'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def log_message(self, fmt, *args):
        if self.path.startswith('/api/'):
            sys.stdout.write('[%s] %s\n' % (self.log_date_time_string(), fmt % args))

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        if self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    # ----- помощники -----
    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return None

    def proxy_platform(self, method):
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY:
            return self.send_json({'ok': False, 'error': 'payload_too_large'}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        body = self.rfile.read(length) if length else None
        headers = {'Accept': self.headers.get('Accept', 'application/json')}
        if self.headers.get('Content-Type'):
            headers['Content-Type'] = self.headers['Content-Type']
        request = urllib_request.Request(PLATFORM_BACKEND_URL + self.path, data=body, headers=headers, method=method)
        try:
            response = urllib_request.urlopen(request, timeout=30)
        except urllib_error.HTTPError as error:
            response = error
        except (urllib_error.URLError, TimeoutError, OSError):
            return self.send_json({'ok': False, 'error': 'platform_unavailable', 'message': 'Новый backend временно недоступен.'}, HTTPStatus.BAD_GATEWAY)
        with response:
            response_body = response.read()
            status = response.code
            content_type = response.headers.get('Content-Type', 'application/json; charset=utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(response_body)))
        self.end_headers()
        if response_body:
            self.wfile.write(response_body)

    # ----- маршруты -----
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/promtour/contest.html':
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header('Location', '/contest/' + ('?' + url.query if url.query else ''))
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if url.path.startswith('/api/v1/') or url.path.startswith('/media/'):
            return self.proxy_platform('GET')
        if url.path == '/api/ping':
            return self.send_json({'ok': True, 'mode': 'server', 'forum': FORUM})
        if url.path == '/api/seats':
            with lock:
                return self.send_json(seat_state(load()))
        if url.path == '/api/registration':
            token = (parse_qs(url.query).get('t') or [''])[0]
            with lock:
                reg = by_token(load(), token)
            return self.send_json({'ok': True, 'registration': public(reg)}) if reg and reg.get('confirmed_at') else self.send_json({'ok': False, 'error': 'not_found'}, HTTPStatus.NOT_FOUND)
        if url.path == '/api/export.csv':
            return self.export_csv()
        if url.path.startswith('/api/'):
            return self.send_json({'ok': False, 'error': 'not_found'}, HTTPStatus.NOT_FOUND)
        return super().do_GET()

    def do_POST(self):
        url = urlparse(self.path)
        if url.path.startswith('/api/v1/'):
            return self.proxy_platform('POST')
        payload = self.read_json()
        if payload is None:
            return self.send_json({'ok': False, 'error': 'bad_request'}, HTTPStatus.BAD_REQUEST)
        if url.path == '/api/register':
            return self.register(payload)
        if url.path == '/api/confirm':
            return self.confirm(payload)
        if url.path == '/api/registration/events':
            return self.update_events(payload)
        return self.send_json({'ok': False, 'error': 'not_found'}, HTTPStatus.NOT_FOUND)

    def register(self, payload):
        person, events, consents, errors = validate(payload)
        if errors:
            return self.send_json({'ok': False, 'errors': errors}, HTTPStatus.UNPROCESSABLE_ENTITY)
        consent_record = {
            'at': now(), 'ip': self.client_address[0], 'user_agent': clean_str(self.headers.get('User-Agent'), 300),
            'version': CONSENT_VERSION, 'pd': True, 'policy': True,
            'media': consents.get('media') is True, 'news': consents.get('news') is True,
        }
        forum = str(payload.get('forum') or FORUM)
        if not FORUM_ID.match(forum):
            return self.send_json({'ok': False, 'errors': {'forum': 'Неизвестный форум'}}, HTTPStatus.UNPROCESSABLE_ENTITY)
        with lock:
            regs = load()
            # Повторная регистрация меняет существующую заявку только после подтверждения email.
            reg = next((r for r in regs if r['person']['email'] == person['email'] and r['forum'] == forum), None)
            updated = reg is not None
            if not reg:
                reg = {'id': 'R-%04d' % (len(regs) + 1), 'forum': forum, 'token': secrets.token_urlsafe(16),
                       'created_at': now(), 'events': {}, 'consents': []}
                regs.append(reg)
                reg['person'] = person
                apply_events(regs, reg, events)
            else:
                reg['pending_person'] = person
                reg['pending_events'] = events
                reg['confirmed_at'] = None
            reg['updated_at'] = now()
            reg['consents'].append(consent_record)
            reg['code'] = '%04d' % secrets.randbelow(10000)
            save(regs)
            crm_queue(reg, 'update' if updated else 'contact+deal')
        print('Регистрация %s %s: код подтверждения %s' % (reg['id'], person['email'], reg.get('code', '—')))
        return self.send_json({
            'ok': True, 'id': reg['id'], 'token': reg['token'] if not updated or reg.get('confirmed_at') else None,
            'updated': updated, 'confirmed': bool(reg.get('confirmed_at')),
            'email_masked': mask_email(person['email']), 'events': reg['events'],
            # писем прототип не отправляет — код возвращаем, чтобы его можно было ввести
            'demo_code': None if reg.get('confirmed_at') else reg['code'],
        })

    def confirm(self, payload):
        token, code = str(payload.get('token') or ''), str(payload.get('code') or '')
        registration_id = str(payload.get('id') or '')
        with lock:
            regs = load()
            reg = next((r for r in regs if r['id'] == registration_id), None) if registration_id else by_token(regs, token)
            if not reg:
                return self.send_json({'ok': False, 'error': 'not_found'}, HTTPStatus.NOT_FOUND)
            if not reg.get('confirmed_at'):
                if not code.isascii() or not secrets.compare_digest(reg.get('code', ''), code):
                    return self.send_json({'ok': False, 'error': 'wrong_code'}, HTTPStatus.UNPROCESSABLE_ENTITY)
                if reg.get('pending_person'):
                    reg['person'] = reg.pop('pending_person')
                if reg.get('pending_events') is not None:
                    apply_events(regs, reg, reg.pop('pending_events'))
                reg['confirmed_at'] = now()
                reg.pop('code', None)
                save(regs)
                crm_queue(reg, 'confirmed')
        return self.send_json({'ok': True, 'registration': public(reg)})

    def update_events(self, payload):
        token, events = str(payload.get('token') or ''), payload.get('events')
        if not isinstance(events, list):
            return self.send_json({'ok': False, 'error': 'bad_request'}, HTTPStatus.BAD_REQUEST)
        events = list(dict.fromkeys(ev for ev in events if isinstance(ev, str) and EVENT_ID.match(ev)))[:60]
        with lock:
            regs = load()
            reg = by_token(regs, token)
            if not reg or not reg.get('confirmed_at'):
                return self.send_json({'ok': False, 'error': 'not_found'}, HTTPStatus.NOT_FOUND)
            apply_events(regs, reg, events)
            reg['updated_at'] = now()
            save(regs)
            crm_queue(reg, 'update')
        return self.send_json({'ok': True, 'registration': public(reg)})

    def export_csv(self):
        """Выгрузка для организатора: открывается в Excel (UTF-8 с BOM, разделитель «;»), время — томское."""
        expected = os.environ.get('LEGACY_EXPORT_TOKEN', '')
        supplied = self.headers.get('X-Export-Token', '')
        if not expected or not secrets.compare_digest(expected, supplied):
            return self.send_json({'ok': False, 'error': 'authentication_required', 'message': 'Выгрузка доступна только сотрудникам через новую админку.'}, HTTPStatus.UNAUTHORIZED)

        def tomsk(ts):
            if not ts:
                return ''
            return datetime.fromisoformat(ts).astimezone(TOMSK).strftime('%d.%m.%Y %H:%M')
        with lock:
            regs = load()
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=';')
        w.writerow(['ID', 'Форум', 'Создана', 'Подтверждена', 'ФИО', 'E-mail', 'Телефон', 'Организация', 'Должность',
                    'Категория', 'Формат', 'Город', 'ИНН', 'События', 'Лист ожидания', 'Согласие: версия', 'Фото/видео', 'Рассылка'])
        for r in regs:
            p, c = r['person'], r['consents'][-1] if r['consents'] else {}
            ok = [k for k, v in r['events'].items() if v['status'] == 'confirmed']
            wait = [k for k, v in r['events'].items() if v['status'] == 'waitlist']
            w.writerow([r['id'], r['forum'], tomsk(r['created_at']), tomsk(r.get('confirmed_at')), p['name'], p['email'], '+' + p['phone'], p['org'],
                        p['position'], CATEGORY_NAMES.get(p['category'], p['category']), 'онлайн' if p['format'] == 'online' else 'очно',
                        p['city'], p['inn'], ', '.join(ok), ', '.join(wait),
                        c.get('version', ''), 'да' if c.get('media') else 'нет', 'да' if c.get('news') else 'нет'])
        body = ('﻿' + buf.getvalue()).encode('utf-8')
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', 'attachment; filename="registrations.csv"')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            # построчный вывод — сообщения сразу видны в окне .bat и в docker logs
            stream.reconfigure(errors='replace', line_buffering=True)
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description='Локальный сервер прототипа «Сибирский форум»')
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8095)))
    ap.add_argument('--host', default=os.environ.get('HOST', '127.0.0.1'))
    ap.add_argument('--open', action='store_true', help='открыть сайт в браузере после запуска')
    args = ap.parse_args()
    if not (SITE / 'index.html').exists():
        sys.exit('Не найдена папка сайта: %s' % SITE)
    httpd = None
    for port in range(args.port, args.port + 10):
        try:
            httpd = Server((args.host, port), Handler)
            break
        except OSError:
            print('Порт %d занят, пробую следующий…' % port)
    if not httpd:
        sys.exit('Не удалось занять порт %d–%d. Возможно, сайт уже запущен в другом окне.' % (args.port, args.port + 9))
    url = 'http://localhost:%d/' % httpd.server_address[1]
    print('Сайт запущен: %s' % url)
    print('Регистрации сохраняются в %s' % REG_FILE)
    print('Выгрузка заявок для Excel: %sapi/export.csv' % url)
    print('Остановить сервер — Ctrl+C или закрыть это окно.')
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nСервер остановлен.')


if __name__ == '__main__':
    main()
