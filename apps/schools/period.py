from django.utils import timezone

PERIOD_YEARS = 5


def report_period(today=None):
    """Отчётный период «за последние 5 лет»: текущий календарный год и четыре предыдущих.

    Возвращает пару (первый год, последний год), например (2022, 2026).
    """
    year = (today or timezone.localdate()).year
    return year - PERIOD_YEARS + 1, year


def period_label(period):
    return f'{period[0]}–{period[1]}'
