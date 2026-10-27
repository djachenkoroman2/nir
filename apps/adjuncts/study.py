"""Учебный год адъюнктуры: курс вычисляется по году поступления, а не хранится в базе."""
from django.utils import timezone

# Учебный год начинается 1 сентября (месяц, день).
ACADEMIC_YEAR_START = (9, 1)


def academic_course(admission_year, today=None):
    """Курс в текущем учебном году: в октябре 2026 года поступивший в 2025 году учится на 2 курсе."""
    today = today or timezone.localdate()
    started = (today.month, today.day) >= ACADEMIC_YEAR_START
    return max(today.year - admission_year + (1 if started else 0), 1)
