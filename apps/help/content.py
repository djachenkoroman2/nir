"""Структура и единый источник содержимого HTML-справки и PDF-руководств."""
from dataclasses import dataclass

from django.http import Http404

from .language import technical_terms
from .screenshots import SCREENSHOTS, validate_screenshot_registry


@dataclass(frozen=True)
class Scenario:
    slug: str
    title: str
    goal: str
    preconditions: str
    steps: tuple[str, ...]
    example: str
    result: str
    errors: tuple[str, ...]
    screenshot: str
    related: str = ''

    @property
    def image(self):
        return SCREENSHOTS[self.screenshot]


@dataclass(frozen=True)
class Chapter:
    slug: str
    title: str
    intro: str
    scenarios: tuple[Scenario, ...]


@dataclass(frozen=True)
class Guide:
    slug: str
    title: str
    manual_title: str
    description: str
    pdf_filename: str


def s(slug, title, goal, preconditions, steps, example, result, errors, screenshot, related=''):
    """Краткий конструктор сценария; списки в исходниках неизменяемы."""
    return Scenario(slug, title, goal, preconditions, tuple(steps), example, result, tuple(errors), screenshot, related)


def chapter(slug, title, intro, *scenarios):
    return Chapter(slug, title, intro, tuple(scenarios))


# Импорты размещены после конструкторов: модули глав используют chapter() и s().
from .guide_common import COMMON_CHAPTER_SLUGS as COMMON_CHAPTER_SLUGS
from .guide_common import ROLE_COMMON as ROLE_COMMON
from .guide_common import common_chapters
from .guide_editor import ADMIN_EXTRA_CHAPTERS, editorial_chapters
from .guide_cabinets import ADJUNCT_CHAPTERS, STUDENT_CHAPTERS, TEACHER_CHAPTERS
from .guide_reader import READER_CHAPTERS


GUIDES = {
    'admin': Guide('admin', 'Руководство администратора', 'Руководство администратора',
                   'Все возможности редактора, управление пользователями, правами, карточками и журналом активности.',
                   'Руководство_администратора.pdf'),
    'editor': Guide('editor', 'Руководство редактора НИР', 'Руководство редактора НИР',
                    'Ведение всех предметных разделов, задач и отчётов кафедры.',
                    'Руководство_редактора_НИР.pdf'),
    'teacher': Guide('teacher', 'Руководство преподавателя и научного руководителя',
                     'Руководство преподавателя и научного руководителя',
                     'Свои труды, подопечные, планы, задачи и персональные отчёты.',
                     'Руководство_преподавателя.pdf'),
    'adjunct': Guide('adjunct', 'Руководство адъюнкта', 'Руководство адъюнкта',
                     'Свои труды, достижения, индивидуальный план, задачи и отчёты.',
                     'Руководство_адъюнкта.pdf'),
    'student': Guide('student', 'Руководство курсанта', 'Руководство курсанта',
                     'Свои публикации, доклады, достижения, задачи и отчёты.',
                     'Руководство_курсанта.pdf'),
    'reader': Guide('reader', 'Руководство пользователя с доступом только для просмотра',
                    'Руководство пользователя с доступом только для просмотра',
                    'Общие разделы кафедры в режиме чтения и собственная учётная запись.',
                    'Руководство_только_просмотр.pdf'),
}

ROLE_CHAPTERS = {
    'admin': (*editorial_chapters('admin'), *ADMIN_EXTRA_CHAPTERS),
    'editor': editorial_chapters('editor'),
    'teacher': TEACHER_CHAPTERS,
    'adjunct': ADJUNCT_CHAPTERS,
    'student': STUDENT_CHAPTERS,
    'reader': READER_CHAPTERS,
}


def chapters_for(role):
    """Полное самостоятельное руководство: ролевые варианты общих глав, затем главы роли."""
    if role not in GUIDES:
        raise Http404('Раздел справки не найден')
    return (*common_chapters(role), *ROLE_CHAPTERS[role])


def get_chapter(role, slug):
    for item in chapters_for(role):
        if item.slug == slug:
            return item
    raise Http404('Глава справки не найдена')


def chapter_neighbours(role, current):
    chapters = chapters_for(role)
    index = chapters.index(current)
    previous = chapters[index - 1] if index else None
    following = chapters[index + 1] if index + 1 < len(chapters) else None
    return previous, following


def validate_content():
    """Ошибки авторской сборки и ролевой аудитории выявляются тестами и сборкой PDF."""
    errors = list(validate_screenshot_registry())
    if set(GUIDES) != set(ROLE_CHAPTERS):
        errors.append('Набор ролей и набор глав не совпадает')
    if set(GUIDES) != set(ROLE_COMMON):
        errors.append('Набор ролей и ролевых вариантов общих глав не совпадает')

    def check_language(role, location, values):
        if role == 'admin':
            return
        terms = technical_terms('\n'.join(values))
        if terms:
            errors.append(f'{location}: технические сведения для неадминистратора: {", ".join(terms)}')

    for role in GUIDES:
        guide = GUIDES[role]
        check_language(role, f'{role}: описание руководства', (guide.title, guide.manual_title, guide.description))
        chapters = chapters_for(role)
        slugs = [item.slug for item in chapters]
        if len(slugs) != len(set(slugs)):
            errors.append(f'{role}: повторяются slug глав')
        if tuple(slugs[:len(COMMON_CHAPTER_SLUGS)]) != COMMON_CHAPTER_SLUGS:
            errors.append(f'{role}: отсутствуют или изменён порядок обязательных общих глав')
        for item in chapters:
            check_language(role, f'{role}/{item.slug}: глава', (item.title, item.intro))
            if not item.scenarios:
                errors.append(f'{role}/{item.slug}: нет сценариев')
            scenario_slugs = [scenario.slug for scenario in item.scenarios]
            if len(scenario_slugs) != len(set(scenario_slugs)):
                errors.append(f'{role}/{item.slug}: повторяются slug сценариев')
            for scenario in item.scenarios:
                values = (scenario.goal, scenario.preconditions, scenario.example, scenario.result)
                check_language(
                    role, f'{role}/{item.slug}/{scenario.slug}',
                    (scenario.title, *values, *scenario.steps, *scenario.errors, scenario.related),
                )
                if not all(values) or len(scenario.steps) < 2 or not scenario.errors:
                    errors.append(f'{role}/{item.slug}/{scenario.slug}: неполный сценарий')
                if not all(scenario.steps) or not all(scenario.errors):
                    errors.append(f'{role}/{item.slug}/{scenario.slug}: пустой шаг или ограничение')
                if scenario.screenshot not in SCREENSHOTS:
                    errors.append(f'{role}/{item.slug}/{scenario.slug}: неизвестный скриншот')
                    continue
                shot = SCREENSHOTS[scenario.screenshot]
                check_language(
                    role, f'{role}/{item.slug}/{scenario.slug}: подпись снимка',
                    (shot.title, shot.alt, *shot.legend),
                )
                audience = shot.roles
                if audience and role not in audience:
                    errors.append(
                        f'{role}/{item.slug}/{scenario.slug}: снимок {scenario.screenshot} '
                        f'предназначен для {audience}'
                    )
    return errors
