from functools import reduce
from operator import and_, or_

from django.db.models import Q
from django.db.models.functions import Lower


def search(queryset, fields, text):
    """Ищет каждое слово из text хотя бы в одном из полей, без учёта регистра (в том числе кириллицы)."""
    words = text.lower().split()
    if not words:
        return queryset
    queryset = queryset.alias(**{f'{field}_lower': Lower(field) for field in fields})
    conditions = [reduce(or_, (Q(**{f'{field}_lower__contains': word}) for field in fields)) for word in words]
    return queryset.filter(reduce(and_, conditions))
