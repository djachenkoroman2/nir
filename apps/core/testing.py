"""Вспомогательные функции для тестов."""


def formset_data(prefix, rows, initial=0):
    """POST-данные формсета: management form и строки rows (словари поле → значение)."""
    data = {
        f'{prefix}-TOTAL_FORMS': str(len(rows)),
        f'{prefix}-INITIAL_FORMS': str(initial),
        f'{prefix}-MIN_NUM_FORMS': '0',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }
    for index, row in enumerate(rows):
        for key, value in row.items():
            data[f'{prefix}-{index}-{key}'] = value
    return data
