import csv
import io

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .models import ExportLog

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


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
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for column in ws.columns:
            letter = column[0].column_letter
            longest = max(len(str(cell.value or '')) for cell in column)
            ws.column_dimensions[letter].width = min(max(longest + 2, 12), 60)
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
