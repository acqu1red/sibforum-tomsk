import csv
import io
from contextlib import contextmanager

from django.db import connection, transaction
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .models import ExportLog

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@contextmanager
def report_snapshot():
    # Multiple sheets must describe one consistent snapshot, even while people
    # register/vote. The audit log is written after this read-only transaction.
    nested = connection.in_atomic_block
    with transaction.atomic():
        if connection.vendor == 'postgresql' and not nested:
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        yield


def safe_value(value):
    if value is None:
        return ''
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(('=', '+', '-', '@')):
            return "'" + value
    return value


def csv_bytes(headers, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_value(value) for value in row])
    return ('﻿' + buffer.getvalue()).encode('utf-8')


def xlsx_bytes(sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet in sheets:
        ws = workbook.create_sheet(sheet['title'])
        ws.append(sheet['headers'])
        for cell in ws[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='3F4FB5')
        for row in sheet['rows']:
            ws.append([safe_value(value) for value in row])
        for row in ws:
            for cell in row:
                cell.alignment = Alignment(vertical='top', wrap_text=True)
        ws.row_dimensions[1].height = 36
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for column in ws.columns:
            letter = column[0].column_letter
            longest = max(max(map(len, str(cell.value or '').split('\n'))) for cell in column)
            ws.column_dimensions[letter].width = min(max(longest + 2, 16), 60)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def file_response(content, filename, content_type):
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store'
    return response


def log_export(user, kind, filters, filename, row_count, ip_address):
    return ExportLog.objects.create(
        actor_user=user,
        kind=kind,
        filters=filters,
        filename=filename,
        row_count=row_count,
        ip_address=ip_address,
    )


def timestamp(value=None):
    value = value or timezone.now()
    return timezone.localtime(value).strftime('%d.%m.%Y %H:%M')
