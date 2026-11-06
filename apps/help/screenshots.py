"""Единый реестр иллюстраций справки: аудитория, HTML, PDF и пересъёмка используют эти ключи."""
from dataclasses import dataclass


ROLE_DEMO_USERS = {
    'admin': 'admin',
    'editor': 'editor',
    'teacher': 'ivanov',
    'adjunct': 'adjunct1',
    'student': 'student1',
    'reader': 'reader',
}
EDITORIAL_ROLES = ('admin', 'editor')


@dataclass(frozen=True)
class Screenshot:
    key: str
    title: str
    alt: str
    legend: tuple[str, ...]
    # Пустой roles означает действительно общую иллюстрацию без ролевого интерфейса.
    roles: tuple[str, ...] = ()
    captured_by: str = ''

    @property
    def filename(self):
        return f'{self.key}.png'

    @property
    def static_path(self):
        return f'help/images/{self.filename}'

    @property
    def is_shared(self):
        return len(self.roles) != 1


def _shot(key, title, *legend, roles=(), captured_by=''):
    return Screenshot(key, title, f'{title}. Пронумерованные стрелки показывают элементы интерфейса.',
                      tuple(legend), roles, captured_by)


_SHOTS = [
    _shot('common-login', 'Страница входа в систему', 'Поле «Имя пользователя»', 'Поле «Пароль»',
          'Кнопка «Войти»', roles=(), captured_by=''),

    _shot('admin-navigation', 'Главная страница администратора', 'Меню общих разделов и администрирования',
          'Сводные карточки кафедры', 'Переход к справке администратора', roles=('admin',), captured_by='admin'),
    _shot('editor-navigation', 'Главная страница редактора НИР', 'Меню разделов кафедры',
          'Сводные карточки кафедры', 'Переход к справке редактора', roles=('editor',), captured_by='editor'),
    _shot('teacher-navigation', 'Кабинет и меню преподавателя', 'Меню личного кабинета',
          'Собственные труды и подопечные', 'Переход к справке преподавателя', roles=('teacher',), captured_by='ivanov'),
    _shot('adjunct-navigation', 'Кабинет и меню адъюнкта', 'Меню личного кабинета',
          'Собственные труды и индивидуальный план', 'Переход к справке адъюнкта', roles=('adjunct',), captured_by='adjunct1'),
    _shot('student-navigation', 'Кабинет и меню курсанта', 'Меню личного кабинета',
          'Собственные труды и достижения', 'Переход к справке курсанта', roles=('student',), captured_by='student1'),
    _shot('reader-navigation', 'Главная страница пользователя без карточки', 'Меню общих разделов для чтения',
          'Сводные карточки кафедры', 'Переход к справке пользователя только для просмотра',
          roles=('reader',), captured_by='reader'),

    _shot('admin-help', 'Руководство администратора в справочной системе', 'Название руководства администратора',
          'Кнопка скачивания PDF администратора', 'Оглавление администратора', roles=('admin',), captured_by='admin'),
    _shot('editor-help', 'Руководство редактора в справочной системе', 'Название руководства редактора',
          'Кнопка скачивания PDF редактора', 'Оглавление редактора', roles=('editor',), captured_by='editor'),
    _shot('teacher-help', 'Руководство преподавателя в справочной системе', 'Название руководства преподавателя',
          'Кнопка скачивания PDF преподавателя', 'Оглавление преподавателя', roles=('teacher',), captured_by='ivanov'),
    _shot('adjunct-help', 'Руководство адъюнкта в справочной системе', 'Название руководства адъюнкта',
          'Кнопка скачивания PDF адъюнкта', 'Оглавление адъюнкта', roles=('adjunct',), captured_by='adjunct1'),
    _shot('student-help', 'Руководство курсанта в справочной системе', 'Название руководства курсанта',
          'Кнопка скачивания PDF курсанта', 'Оглавление курсанта', roles=('student',), captured_by='student1'),
    _shot('reader-help', 'Руководство пользователя только для просмотра', 'Название руководства пользователя без карточки',
          'Кнопка скачивания PDF пользователя без карточки', 'Оглавление пользователя только для просмотра',
          roles=('reader',), captured_by='reader'),

    _shot('admin-profile', 'Личные сведения администратора', 'ФИО и e-mail администратора',
          'Кнопка сохранения', roles=('admin',), captured_by='admin'),
    _shot('editor-profile', 'Личные сведения редактора НИР', 'ФИО и e-mail редактора',
          'Кнопка сохранения', roles=('editor',), captured_by='editor'),
    _shot('teacher-profile', 'Личные сведения преподавателя', 'ФИО, отчество, e-mail и телефон преподавателя',
          'Кнопка сохранения', roles=('teacher',), captured_by='ivanov'),
    _shot('adjunct-profile', 'Личные сведения адъюнкта', 'ФИО, отчество, e-mail и телефон адъюнкта',
          'Кнопка сохранения', roles=('adjunct',), captured_by='adjunct1'),
    _shot('student-profile', 'Личные сведения курсанта', 'ФИО, отчество и e-mail курсанта',
          'Кнопка сохранения', roles=('student',), captured_by='student1'),
    _shot('reader-profile', 'Личные сведения пользователя без карточки', 'ФИО и e-mail учётной записи без карточки',
          'Кнопка сохранения', roles=('reader',), captured_by='reader'),

    _shot('admin-report', 'Параметры отчёта кафедры администратора', 'Период и разделы отчёта кафедры',
          'Кнопка формирования', 'Печать и скачивание DOCX', roles=('admin',), captured_by='admin'),
    _shot('editor-report', 'Параметры отчёта кафедры редактора', 'Период и разделы отчёта кафедры',
          'Кнопка формирования', 'Печать и скачивание DOCX', roles=('editor',), captured_by='editor'),
    _shot('teacher-report', 'Форма 16 преподавателя', 'Период и разделы собственной формы 16',
          'Кнопка формирования', 'Печать и скачивание DOCX', roles=('teacher',), captured_by='ivanov'),
    _shot('adjunct-report', 'Форма 16 адъюнкта', 'Период и разделы собственной формы 16',
          'Кнопка формирования', 'Печать и скачивание DOCX', roles=('adjunct',), captured_by='adjunct1'),
    _shot('student-report', 'Форма 16 курсанта', 'Период и разделы собственной формы 16',
          'Кнопка формирования', 'Печать и скачивание DOCX', roles=('student',), captured_by='student1'),
    _shot('reader-report', 'Карточка учётной записи пользователя без карточки', 'Сведения собственной учётной записи',
          'Скачивание DOCX', 'Версия для печати', roles=('reader',), captured_by='reader'),
    _shot('admin-person-report', 'Персональная форма 16 администратора', 'Выбор человека и параметры формы 16',
          'Кнопка формирования', 'Печать и скачивание DOCX', roles=('admin',), captured_by='admin'),
    _shot('editor-person-report', 'Персональная форма 16 редактора', 'Выбор человека и параметры формы 16',
          'Кнопка формирования', 'Печать и скачивание DOCX', roles=('editor',), captured_by='editor'),
    _shot('admin-account', 'Учётная запись администратора для печати', 'Сведения учётной записи администратора',
          'Скачивание DOCX', 'Версия для печати', roles=('admin',), captured_by='admin'),
    _shot('editor-account', 'Учётная запись редактора для печати', 'Сведения учётной записи редактора',
          'Скачивание DOCX', 'Версия для печати', roles=('editor',), captured_by='editor'),

    _shot('editor-teachers', 'Список преподавателей', 'Поиск и фильтр', 'Добавление преподавателя',
          'Действия с записью', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-teacher-form', 'Форма преподавателя', 'Основные сведения', 'Контакты и статус работы',
          'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-research', 'Список НИОКР', 'Поиск и фильтр статуса', 'Добавление НИОКР',
          'Сроки и статусы проектов', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-research-form', 'Форма НИОКР и участников', 'Сведения и сроки проекта', 'Строки участников',
          'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-cooperation', 'Реестр договоров сотрудничества', 'Поиск и фильтр состояния', 'Добавление договора',
          'Срок действия и состояние', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-cooperation-form', 'Форма договора сотрудничества', 'Название, номер и организация',
          'Предмет и срок действия', 'Подсказка о бессрочном договоре', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-publications', 'Список публикаций', 'Поиск и фильтры', 'Добавление публикации',
          'Сведения об индексировании', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-publication-form', 'Форма публикации с авторами', 'Выходные данные и индексирование',
          'Динамические строки авторов', 'Добавление строки автора и сохранение', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-ip', 'Список результатов интеллектуальной деятельности', 'Поиск и фильтры', 'Добавление РИД',
          'Номер и даты регистрации', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-ip-form', 'Форма РИД с авторами', 'Вид, номер и даты', 'Правообладатель и связи',
          'Авторы и сохранение', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-conferences', 'Список конференций', 'Поиск и фильтры', 'Добавление конференции',
          'Переход к карточке', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-conference-form', 'Форма конференции', 'Название, уровень и место', 'Даты проведения',
          'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-report-form', 'Форма доклада и докладчиков', 'Название и форма доклада', 'Публикация тезисов',
          'Докладчики и сохранение', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-schools', 'Сводная таблица научных школ', 'Переключатель действующих и всех школ',
          'Показатели по годам', 'Добавление школы и печать', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-school-form', 'Форма научной школы', 'Название и направление', 'Ведущие учёные и признак действующей',
          'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-students', 'Список курсантов', 'Поиск и фильтры', 'Добавление курсанта',
          'Сводка по курсанту', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-student-form', 'Форма курсанта', 'ФИО, группа и курс', 'Руководитель и статус',
          'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-student-achievement-form', 'Форма достижения курсанта', 'Вид, уровень и мероприятие',
          'Результат, дата и документ', 'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-adjuncts', 'Список адъюнктов', 'Поиск и фильтры', 'Добавление адъюнкта',
          'Курс и статус обучения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-adjunct-form', 'Форма адъюнкта', 'Тема и специальность', 'Период обучения и руководитель',
          'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-plan-form', 'Форма этапа индивидуального плана', 'Вид и наименование этапа',
          'Год обучения, срок и статус', 'Отметка руководителя и сохранение', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-adjunct-achievement-form', 'Форма достижения адъюнкта', 'Сведения о мероприятии',
          'Результат и подтверждающий документ', 'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-tasks', 'Список задач кафедры', 'Фильтр по статусу', 'Исполнители и сроки',
          'Переход к задаче', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-task-form', 'Форма постановки задачи', 'Исполнитель, заголовок и описание',
          'Срок, приоритет и этап плана', 'Кнопка сохранения', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-task-detail', 'Карточка задачи с обсуждением', 'Статус и действия руководителя',
          'Описание и срок', 'Комментарии и форма ответа', roles=EDITORIAL_ROLES, captured_by='editor'),
    _shot('editor-department-report', 'Отчёт о НИР кафедры', 'Вид, период и разделы',
          'Категории и дополнительные параметры', 'Печать и скачивание DOCX', roles=EDITORIAL_ROLES, captured_by='editor'),

    _shot('admin-users', 'Список пользователей в админке', 'Поиск и фильтры пользователей',
          'Добавление пользователя', 'Переход к настройке учётной записи', roles=('admin',), captured_by='admin'),
    _shot('admin-user-form', 'Настройка пользователя в админке', 'Статус учётной записи и персонала',
          'Группы пользователя', 'Индивидуальные права', roles=('admin',), captured_by='admin'),
    _shot('admin-teacher-link', 'Привязка преподавателя к учётной записи в админке', 'Сведения карточки преподавателя',
          'Поле выбора учётной записи', 'Кнопки сохранения', roles=('admin',), captured_by='admin'),
    _shot('admin-activity', 'Отчёт об активности пользователей', 'Период и категории',
          'Показать пользователей без активности', 'Итоги и подробные журналы', roles=('admin',), captured_by='admin'),

    _shot('teacher-cabinet', 'Личный кабинет преподавателя', 'Добавление трудов', 'Свои показатели и записи',
          'Подопечные и отчёты', roles=('teacher',), captured_by='ivanov'),
    _shot('teacher-publication-form', 'Добавление публикации преподавателем', 'Сведения о публикации',
          'Авторская строка преподавателя', 'Добавление соавторов', roles=('teacher',), captured_by='ivanov'),
    _shot('teacher-ip-form', 'Добавление РИД преподавателем', 'Сведения о результате', 'Авторы и правообладатель',
          'Кнопка сохранения', roles=('teacher',), captured_by='ivanov'),
    _shot('teacher-report-choice', 'Выбор конференции преподавателем', 'Поле выбора конференции',
          'Добавление отсутствующей конференции', 'Переход к докладу', roles=('teacher',), captured_by='ivanov'),
    _shot('teacher-student', 'Карточка подопечного курсанта', 'Добавление достижения и задачи',
          'Труды и показатели курсанта', 'Отчёты курсанта', roles=('teacher',), captured_by='ivanov'),
    _shot('teacher-adjunct', 'Карточка подопечного адъюнкта и план', 'Добавление этапа плана',
          'Статусы и просроченные этапы', 'Этапы по годам и отметки руководителя', roles=('teacher',), captured_by='ivanov'),
    _shot('teacher-task', 'Задача подопечного в кабинете руководителя', 'Допустимые действия и приёмка',
          'История статусов', 'Добавление комментария', roles=('teacher',), captured_by='ivanov'),
    _shot('teacher-reports', 'Отчёты преподавателя и подопечных', 'Личные отчёты', 'Отчёт о работе с подопечными',
          'Печать и DOCX', roles=('teacher',), captured_by='ivanov'),

    _shot('adjunct-cabinet', 'Личный кабинет адъюнкта', 'Добавление трудов и достижения', 'Индивидуальный план',
          'Задачи и отчёты', roles=('adjunct',), captured_by='adjunct1'),
    _shot('adjunct-publication-form', 'Добавление публикации адъюнктом', 'Сведения о публикации',
          'Авторская строка адъюнкта', 'Соавторы и сохранение', roles=('adjunct',), captured_by='adjunct1'),
    _shot('adjunct-ip-form', 'Добавление РИД адъюнктом', 'Сведения о результате', 'Авторы и правообладатель',
          'Кнопка сохранения', roles=('adjunct',), captured_by='adjunct1'),
    _shot('adjunct-report-choice', 'Выбор конференции адъюнктом', 'Выбор существующей конференции',
          'Добавление новой конференции', 'Переход к докладу', roles=('adjunct',), captured_by='adjunct1'),
    _shot('adjunct-achievement-form', 'Форма достижения адъюнкта', 'Вид и уровень достижения',
          'Результат и документ', 'Кнопка сохранения', roles=('adjunct',), captured_by='adjunct1'),
    _shot('adjunct-plan', 'Индивидуальный план в кабинете адъюнкта', 'Запланированный этап и его статус',
          'Кнопка «Начать выполнение»', 'Срок и пояснение этапа', roles=('adjunct',), captured_by='adjunct1'),
    _shot('adjunct-task', 'Задача в кабинете адъюнкта', 'Доступные исполнителю статусы', 'Описание и срок',
          'Обсуждение задачи', roles=('adjunct',), captured_by='adjunct1'),
    _shot('adjunct-reports', 'Отчёты адъюнкта', 'Форма 16 и научная работа', 'Отчёт о плане',
          'Печать и DOCX', roles=('adjunct',), captured_by='adjunct1'),

    _shot('student-cabinet', 'Личный кабинет курсанта', 'Добавление публикации, доклада и достижения',
          'Сводка и список трудов', 'Задачи и отчёты', roles=('student',), captured_by='student1'),
    _shot('student-publication-form', 'Добавление публикации курсантом', 'Сведения о публикации',
          'Авторская строка курсанта', 'Соавторы и сохранение', roles=('student',), captured_by='student1'),
    _shot('student-report-choice', 'Выбор конференции курсантом', 'Выбор конференции',
          'Добавление новой конференции', 'Переход к докладу', roles=('student',), captured_by='student1'),
    _shot('student-achievement-form', 'Форма достижения курсантом', 'Вид и уровень достижения',
          'Результат и документ', 'Кнопка сохранения', roles=('student',), captured_by='student1'),
    _shot('student-task', 'Задача в кабинете курсанта', 'Доступные исполнителю статусы', 'Описание и срок',
          'Комментарии', roles=('student',), captured_by='student1'),
    _shot('student-reports', 'Отчёты курсанта', 'Форма 16 и научная работа', 'Карточка для печати',
          'Печать и DOCX', roles=('student',), captured_by='student1'),

    _shot('reader-list', 'Общий раздел в режиме только для просмотра', 'Поиск и фильтры',
          'Отсутствие кнопок изменения', 'Переход к карточке записи', roles=('reader',), captured_by='reader'),
    _shot('reader-detail', 'Карточка записи в режиме только для просмотра', 'Сведения записи', 'Связанные данные',
          'Отсутствие действий редактирования', roles=('reader',), captured_by='reader'),
    _shot('reader-reports', 'Доступные пользователю без карточки материалы', 'Отсутствие личных отчётов',
          'Моя учётная запись', 'Переход к профилю', roles=('reader',), captured_by='reader'),
]

SCREENSHOTS = {shot.key: shot for shot in _SHOTS}


def validate_screenshot_registry():
    """Проверяет явную аудиторию и демо-пользователя каждого снимка без обращения к БД."""
    errors = []
    if len(SCREENSHOTS) != len(_SHOTS):
        errors.append('Повторяются ключи снимков')
    for key, shot in SCREENSHOTS.items():
        unknown = set(shot.roles) - set(ROLE_DEMO_USERS)
        if unknown:
            errors.append(f'{key}: неизвестные роли {sorted(unknown)}')
        if not shot.roles:
            if shot.captured_by:
                errors.append(f'{key}: общий снимок не должен быть привязан к ролевому пользователю')
            continue
        expected_users = {ROLE_DEMO_USERS[role] for role in shot.roles if role in ROLE_DEMO_USERS}
        if shot.captured_by not in expected_users:
            errors.append(f'{key}: пользователь {shot.captured_by!r} не соответствует ролям {shot.roles}')
    return errors


def validate_capture_specs(specs):
    """Сверяет фактические спецификации WebDriver с реестром до изменения PNG."""
    errors = []
    by_key = {shot.key: shot for shot in specs}
    if len(by_key) != len(specs):
        errors.append('Повторяются ключи спецификаций снимков')
    missing = set(SCREENSHOTS) - set(by_key)
    extra = set(by_key) - set(SCREENSHOTS)
    if missing:
        errors.append(f'Нет спецификаций: {sorted(missing)}')
    if extra:
        errors.append(f'Лишние спецификации: {sorted(extra)}')
    for key, spec in by_key.items():
        if key in SCREENSHOTS and spec.user != SCREENSHOTS[key].captured_by:
            errors.append(
                f'{key}: снимок делается под {spec.user!r}, ожидается {SCREENSHOTS[key].captured_by!r}'
            )
    return errors
