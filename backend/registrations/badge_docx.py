from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.lib.units import mm


DOCX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
DOCUMENT_PART_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
WORD_NAMESPACE = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def build_badge_docx(lines, page_size, line_height):
    # Word page geometry and paragraph spacing use twips (20 per point).
    width, height = (round(points * 20) for points in page_size)
    margin = round(3 * mm * 20)
    paragraphs = []
    for line in lines:
        half_points = max(2, int(line.size * 2))
        before = round(line.space_before * 20)
        leading = round(line.size * line_height * 20)
        weight = '<w:b/>' if line.bold else ''
        # Filter characters forbidden in XML 1.0 before escaping registration text.
        text = escape(''.join(char for char in line.text if ord(char) >= 32 and char not in '\ufffe\uffff'))
        paragraphs.append(
            '<w:p><w:pPr><w:keepLines/>'
            f'<w:spacing w:before="{before}" w:after="0" w:line="{leading}" w:lineRule="exact"/>'
            '<w:jc w:val="center"/></w:pPr>'
            '<w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
            f'{weight}<w:sz w:val="{half_points}"/></w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
        )

    document = (
        f'<w:document xmlns:w="{WORD_NAMESPACE}"><w:body>'
        + ''.join(paragraphs)
        + f'<w:sectPr><w:pgSz w:w="{width}" w:h="{height}" w:orient="landscape"/>'
        f'<w:pgMar w:top="{margin}" w:right="{margin}" w:bottom="{margin}" w:left="{margin}" '
        'w:header="0" w:footer="0" w:gutter="0"/><w:vAlign w:val="center"/></w:sectPr></w:body></w:document>'
    )
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        f'<Override PartName="/word/document.xml" ContentType="{DOCUMENT_PART_TYPE}"/>'
        '</Types>'
    )
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', relationships)
        archive.writestr('word/document.xml', document)
    return buffer.getvalue()
