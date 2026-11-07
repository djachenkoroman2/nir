"""Редакционные правила пользовательского языка справки, не затрагивающие предметные поля."""
import re


NON_ADMIN_ROLES = ('editor', 'teacher', 'adjunct', 'student', 'reader')

# URL намеренно отсутствует: это реальное поле публикаций и РИД. DOI, PDF, DOCX и предметные
# аббревиатуры также не являются техническим жаргоном в пользовательских инструкциях.
TECHNICAL_PATTERNS = (
    (re.compile(r'\bPOST\b'), 'HTTP-метод POST'),
    (re.compile(r'\bGET\b'), 'HTTP-метод GET'),
    (re.compile(r'\bHTTP\b'), 'HTTP'),
    (re.compile(r'(?<!\d)403(?!\d)'), 'код ответа 403'),
    (re.compile(r'(?<!\d)404(?!\d)'), 'код ответа 404'),
    (re.compile(r'\b(?:is_staff|is_superuser|activity\.view_activity_report)\b'), 'внутренние флаги и коды прав'),
    (re.compile(r'\?then=report\b'), 'служебный параметр ?then=report'),
    (re.compile(r'\ball=1\b'), 'служебный параметр all=1'),
    (re.compile(r'/(?:add|edit|delete)/'), 'внутренние адреса форм'),
    (re.compile(r'\b(?:Django|ORM|middleware)\b', re.IGNORECASE), 'сведения о реализации Django'),
    (re.compile(r'числов\w*\s+(?:ID|идентификатор\w*)', re.IGNORECASE), 'числовые идентификаторы'),
    (re.compile(r'суперпользовател\w*', re.IGNORECASE), 'суперпользователь'),
    (re.compile(r'прям\w*\s+(?:URL|адрес\w*)', re.IGNORECASE), 'прямые адреса страниц'),
)


def technical_terms(text):
    """Возвращает названия запрещённых для неадминистратора классов сведений."""
    return [label for pattern, label in TECHNICAL_PATTERNS if pattern.search(text)]
