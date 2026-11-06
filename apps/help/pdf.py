"""Сборка самостоятельных PDF-руководств из единого содержимого справки."""
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import shutil
import subprocess

from django.conf import settings
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.image.image import Image as DocxImage
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .content import GUIDES, chapters_for
from .screenshots import SCREENSHOTS

BASE_DIR = Path(settings.BASE_DIR)
IMAGE_DIR = BASE_DIR / 'static' / 'help' / 'images'
GENERATED_DIR = BASE_DIR / 'apps' / 'help' / 'generated'


@dataclass
class BuildResult:
    role: str
    path: Path
    size: int
    scenarios: int
    images: int
    pages: int | None


def _font(style, size=None, bold=None, color=None):
    style.font.name = 'Times New Roman'
    style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color:
        style.font.color.rgb = RGBColor(*color)


def _document(guide):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(1.5), Cm(1.5)
    section.left_margin, section.right_margin = Cm(1.7), Cm(1.7)
    section.header_distance, section.footer_distance = Cm(.7), Cm(.7)
    styles = doc.styles
    _font(styles['Normal'], 11)
    styles['Normal'].paragraph_format.space_after = Pt(5)
    styles['Normal'].paragraph_format.line_spacing = 1.08
    for name, size, color in (
        ('Title', 24, (31, 78, 121)), ('Heading 1', 17, (31, 78, 121)),
        ('Heading 2', 14, (31, 78, 121)), ('Heading 3', 12, (47, 84, 120)),
    ):
        _font(styles[name], size, True, color)
        styles[name].paragraph_format.keep_with_next = True
        styles[name].paragraph_format.space_before = Pt(10)
        styles[name].paragraph_format.space_after = Pt(6)
    _font(styles['Caption'], 9)
    styles['Caption'].font.italic = False
    styles['Caption'].paragraph_format.keep_with_next = True
    doc.core_properties.title = guide.manual_title
    doc.core_properties.subject = 'Справочная система приложения «Учёт показателей НИР кафедры»'
    doc.core_properties.author = 'Учёт показателей НИР кафедры'
    header = section.header.paragraphs[0]
    header.text = guide.manual_title
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _font(header.style, 8)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run('Страница ')
    run.font.name = 'Times New Roman'
    run.font.size = Pt(9)
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    return doc


def _label(doc, label, text):
    p = doc.add_paragraph()
    p.paragraph_format.keep_with_next = True
    r = p.add_run(f'{label}. ')
    r.bold = True
    p.add_run(text)
    return p


def _page_break(doc):
    doc.add_page_break()


def build_document(role, output):
    """Создаёт промежуточный DOCX; пользовательский runtime этот метод не вызывает."""
    guide = GUIDES[role]
    chapters = chapters_for(role)
    doc = _document(guide)
    title = doc.add_paragraph(style='Title')
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run('Учёт показателей НИР кафедры')
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run(guide.manual_title)
    run.bold, run.font.size = True, Pt(20)
    description = doc.add_paragraph(guide.description)
    description.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    version = doc.add_paragraph(f'Дата сборки: {date.today():%d.%m.%Y}\nФормат: самостоятельное руководство с общими и ролевыми главами')
    version.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note = doc.add_paragraph('Демонстрационные имена и данные на иллюстрациях используются только для обучения.')
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _page_break(doc)

    doc.add_heading('Оглавление', level=1)
    for chapter_number, item in enumerate(chapters, 1):
        p = doc.add_paragraph()
        p.add_run(f'{chapter_number}. {item.title}').bold = True
        p.add_run(f' — {len(item.scenarios)} сценариев')
        doc.add_paragraph(item.intro)
    doc.add_paragraph('В HTML-справке те же главы доступны через пункт «Справка» в главном меню.')
    _page_break(doc)

    figure_number = 0
    scenario_count = 0
    for chapter_number, item in enumerate(chapters, 1):
        if chapter_number > 1:
            _page_break(doc)
        doc.add_heading(f'{chapter_number}. {item.title}', level=1)
        doc.add_paragraph(item.intro)
        for scenario_number, scenario in enumerate(item.scenarios, 1):
            scenario_count += 1
            doc.add_heading(f'{chapter_number}.{scenario_number}. {scenario.title}', level=2)
            doc.add_paragraph(scenario.goal)
            _label(doc, 'Предусловия', scenario.preconditions)
            p = doc.add_paragraph()
            p.paragraph_format.keep_with_next = True
            p.add_run('Порядок действий:').bold = True
            for step_number, step in enumerate(scenario.steps, 1):
                doc.add_paragraph(f'{step_number}. {step}')
            _label(doc, 'Пример', scenario.example)
            _label(doc, 'Результат', scenario.result)
            p = doc.add_paragraph()
            p.paragraph_format.keep_with_next = True
            p.add_run('Ошибки и ограничения:').bold = True
            for error in scenario.errors:
                doc.add_paragraph(f'• {error}')
            if scenario.related:
                _label(doc, 'Что дальше', scenario.related)
            shot = SCREENSHOTS[scenario.screenshot]
            image = IMAGE_DIR / shot.filename
            if not image.is_file() or image.stat().st_size == 0:
                raise FileNotFoundError(f'Не найдено изображение для {role}/{item.slug}/{scenario.slug}: {image}')
            figure_number += 1
            image_info = DocxImage.from_file(str(image))
            width_cm = 16.8
            height_cm = width_cm * image_info.px_height / image_info.px_width
            if height_cm > 17:
                width_cm = 17 * image_info.px_width / image_info.px_height
            picture_paragraph = doc.add_paragraph()
            picture_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            picture_paragraph.paragraph_format.keep_with_next = True
            picture_paragraph.add_run().add_picture(str(image), width=Cm(width_cm))
            caption = doc.add_paragraph(style='Caption')
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            caption.add_run(f'Рисунок {figure_number} — {shot.title}').bold = True
            for legend_number, legend in enumerate(shot.legend, 1):
                doc.add_paragraph(f'{legend_number}. {legend}', style='Caption')
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    return scenario_count, figure_number


def _run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, capture_output=True, timeout=180, **kwargs)


def pdf_pages(path):
    executable = shutil.which('pdfinfo')
    if not executable:
        return None
    try:
        result = _run([executable, str(path)])
    except (subprocess.SubprocessError, OSError):
        return None
    match = re.search(r'^Pages:\s+(\d+)', result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def pdf_text(path):
    """Нормализованный текст PDF или None, если Poppler не установлен."""
    executable = shutil.which('pdftotext')
    if not executable:
        return None
    result = _run([executable, str(path), '-'])
    return ' '.join(result.stdout.split())


def inspect_pdf(path, guide=None, chapters=()):
    """Проверяет реальный PDF и, при наличии Poppler, извлечение русского текста."""
    issues = []
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1000:
        return [f'PDF отсутствует или слишком мал: {path}']
    if path.read_bytes()[:5] != b'%PDF-':
        issues.append(f'Некорректная сигнатура PDF: {path}')
    if guide is not None and pdf_pages(path) == 0:
        issues.append(f'PDF не содержит страниц: {path}')
    if shutil.which('pdftotext') and guide is not None:
        try:
            normalized = pdf_text(path)
            expected = [guide.manual_title, *(item.title for item in chapters)]
            for title in expected:
                if ' '.join(title.split()) not in normalized:
                    issues.append(f'В PDF не найден обязательный заголовок «{title}»: {path}')
            for item in chapters:
                for scenario in item.scenarios:
                    example = ' '.join(scenario.example.split())
                    if example not in normalized:
                        issues.append(
                            f'В PDF не найден ролевой пример «{scenario.example}» '
                            f'({item.slug}/{scenario.slug}): {path}'
                        )
        except (subprocess.SubprocessError, OSError) as exc:
            issues.append(f'Не удалось извлечь текст PDF {path}: {exc}')
    return issues


def build_pdfs(roles, work_dir, soffice=None):
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    executable = soffice or shutil.which('libreoffice') or shutil.which('soffice')
    if not executable:
        raise RuntimeError('Для сборки PDF нужен LibreOffice (libreoffice/soffice в PATH)')
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for role in roles:
        guide = GUIDES[role]
        docx_path = work_dir / f'{role}.docx'
        pdf_dir = work_dir / 'pdf'
        pdf_dir.mkdir(parents=True, exist_ok=True)
        scenario_count, image_count = build_document(role, docx_path)
        profile = work_dir / 'lo-profile'
        profile.mkdir(exist_ok=True)
        command = [
            executable, '--headless', f'-env:UserInstallation={profile.as_uri()}',
            '--convert-to', 'pdf:writer_pdf_Export', '--outdir', str(pdf_dir), str(docx_path),
        ]
        try:
            _run(command)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f'LibreOffice не собрал {role}: {exc.stdout}\n{exc.stderr}') from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f'Превышено время сборки PDF {role}') from exc
        built = pdf_dir / f'{role}.pdf'
        chapters = chapters_for(role)
        issues = inspect_pdf(built, guide, chapters)
        if issues:
            raise RuntimeError('\n'.join(issues))
        destination = GENERATED_DIR / f'{role}.pdf'
        shutil.copy2(built, destination)
        results.append(BuildResult(role, destination, destination.stat().st_size, scenario_count, image_count,
                                   pdf_pages(destination)))
    return results
