"""Server-side export of an already saved summary; never executes AI."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
import re

from clean_urls import supplied_url


def markdown_document(data: dict) -> str:
    summary = data['summary']
    lines = [f"# {summary['query_text']}", '', f"Generated: {summary['created_at']}",
             f"Provider: {summary.get('provider') or 'Not recorded'} | Model: {summary.get('summarizer') or 'Not recorded'}", '',
             summary['summary_text'], '', '## Grounded sources', '']
    for source in data['sources']:
        if supplied_url(source['url']):
            # Escape title syntax; preserve the actual URI without rewriting.
            label = (source.get('title') or 'Source').replace('[', r'\[').replace(']', r'\]')
            lines.append(f"- [{label}](<{source['url']}>)")
    if not data['sources']:
        lines.append('No grounded sources were recorded.')
    lines.append('\nSources originate in provider metadata; publisher destinations were not independently verified.')
    return '\n'.join(lines) + '\n'


def pdf_document(data: dict) -> bytes:
    """Wrap paragraphs across pages, escaping all untrusted text and URLs."""
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    # Fonts bundled with ReportLab avoid a platform-specific font dependency.
    font_dir = Path(reportlab.__file__).parent / 'fonts'
    if 'ResearchVera' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('ResearchVera', str(font_dir / 'Vera.ttf')))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = 'ResearchVera'
        style.textColor = colors.black
        style.alignment = TA_LEFT
        style.wordWrap = 'LTR'
    styles['BodyText'].fontSize = 10
    styles['BodyText'].leading = 15
    styles['BodyText'].spaceAfter = 8
    styles['Title'].fontSize = 18
    styles['Title'].leading = 24
    styles['Heading1'].fontSize = 15
    styles['Heading1'].leading = 20
    styles['Heading2'].fontSize = 12
    styles['Heading2'].leading = 17
    story = []
    summary = data['summary']
    story.append(Paragraph(escape(summary['query_text']), styles['Title']))
    story.append(Paragraph(escape(f"Generated: {summary['created_at']} | {summary.get('provider') or 'Not recorded'} | {summary.get('summarizer') or 'Model not recorded'}"), styles['BodyText']))
    for block in re.split(r'\n\s*\n', summary['summary_text']):
        # Preserve saved text; render a small safe subset of Markdown headings/lists.
        for line in block.splitlines():
            heading = re.match(r'^(#{1,6})\s+(.*)', line)
            if heading:
                story.append(Paragraph(escape(heading[2]), styles['Heading1' if len(heading[1]) == 1 else 'Heading2']))
            elif line.strip():
                story.append(Paragraph(escape(line), styles['BodyText']))
        story.append(Spacer(1, 5))
    story.append(Paragraph('Grounded sources', styles['Heading2']))
    for source in data['sources']:
        url = source['url']
        if supplied_url(url):
            title = source.get('title') or 'Source'
            escaped_url = escape(url, {'"': '&quot;', "'": '&apos;'})
            story.append(Paragraph(f'<link href="{escaped_url}"><u>{escape(title)}</u></link>', styles['BodyText']))
    if not data['sources']:
        story.append(Paragraph('No grounded sources were recorded.', styles['BodyText']))
    story.append(Paragraph('Sources originate in provider metadata; publisher destinations were not independently verified.', styles['BodyText']))
    buffer = BytesIO()
    def page_number(canvas, document):
        canvas.setFont('ResearchVera', 8)
        canvas.drawRightString(document.pagesize[0]-48, 25, str(document.page))
    SimpleDocTemplate(buffer, rightMargin=48, leftMargin=48, topMargin=45, bottomMargin=45,
                      title=summary['query_text'], author='MY_CUSTOM_BOT').build(story, onFirstPage=page_number, onLaterPages=page_number)
    return buffer.getvalue()
