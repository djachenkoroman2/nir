import datetime
import random

from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.publications.models import Publication, PublicationAuthor
from apps.research.models import Participant, ResearchProject
from apps.schools.models import DissertationDefense, ScientificSchool
from apps.schools.period import report_period
from apps.staff.models import Teacher

from ._base import DevOnlyCommand, domain_counts, has_domain_data
from .clear_data import clear_data

DEMO_PASSWORD = 'demo12345'
UNIVERSITY = 'ФГБОУ ВО «Демонстрационный государственный технический университет»'

P, D, T = Teacher.Position, Teacher.Degree, Teacher.AcademicTitle
# Фамилия, имя, отчество, должность, степень, звание, логин демо-пользователя (или None), работает ли.
TEACHERS = [
    ('Иванов', 'Сергей', 'Петрович', P.HEAD, D.DOCTOR, T.PROFESSOR, 'ivanov', True),
    ('Петрова', 'Елена', 'Викторовна', P.PROFESSOR, D.DOCTOR, T.PROFESSOR, 'petrova', True),
    ('Смирнов', 'Алексей', 'Игоревич', P.ASSOCIATE_PROFESSOR, D.CANDIDATE, T.DOCENT, 'smirnov', True),
    ('Кузнецова', 'Ольга', 'Николаевна', P.PROFESSOR, D.DOCTOR, T.DOCENT, None, True),
    ('Соколов', 'Дмитрий', 'Андреевич', P.ASSOCIATE_PROFESSOR, D.CANDIDATE, T.DOCENT, None, True),
    ('Морозова', 'Анна', 'Сергеевна', P.ASSOCIATE_PROFESSOR, D.CANDIDATE, T.NONE, None, True),
    ('Волков', 'Михаил', 'Юрьевич', P.ASSOCIATE_PROFESSOR, D.CANDIDATE, T.DOCENT, None, True),
    ('Лебедева', 'Татьяна', 'Александровна', P.SENIOR_LECTURER, D.CANDIDATE, T.NONE, None, True),
    ('Новиков', 'Артём', 'Владимирович', P.SENIOR_LECTURER, D.NONE, T.NONE, None, True),
    ('Фёдорова', 'Мария', 'Олеговна', P.LECTURER, D.NONE, T.NONE, None, True),
    ('Егоров', 'Илья', 'Сергеевич', P.ASSISTANT, D.NONE, T.NONE, None, True),
    ('Павлова', 'Ксения', 'Дмитриевна', P.ASSISTANT, D.NONE, T.NONE, None, True),
    ('Григорьев', 'Виктор', 'Павлович', P.PROFESSOR, D.DOCTOR, T.PROFESSOR, None, False),
    ('Орлова', 'Наталья', 'Ивановна', P.ASSOCIATE_PROFESSOR, D.CANDIDATE, T.DOCENT, None, False),
]

# Название школы, индексы ведущих учёных в TEACHERS, действующая ли.
SCHOOLS = [
    ('Интеллектуальный анализ данных и машинное обучение', [0, 4], True),
    ('Распределённые вычислительные системы', [1, 6], True),
    ('Информационная безопасность киберфизических систем', [3, 2], True),
    ('Математическое моделирование технологических процессов', [12], False),
]

TOPICS = [
    'методы машинного обучения для прогнозирования отказов оборудования',
    'распределённая обработка потоковых данных',
    'обнаружение аномалий в сетевом трафике',
    'нейросетевые модели классификации изображений',
    'оптимизация расписаний в облачных вычислениях',
    'защита промышленных систем управления',
    'анализ временных рядов с пропусками',
    'интеллектуальные системы поддержки принятия решений',
    'модели консенсуса в распределённых реестрах',
    'цифровые двойники производственных линий',
    'обработка естественного языка для технической документации',
    'криптографические протоколы для интернета вещей',
    'визуальная аналитика больших данных',
    'математические модели теплопереноса',
    'рекомендательные системы для образовательных платформ',
]
TITLE_PREFIXES = [
    'Исследование', 'Разработка', 'Применение', 'Анализ', 'Метод', 'Модель', 'Алгоритмы',
    'Сравнительная оценка', 'Об одном подходе к задаче', 'Повышение эффективности',
]
JOURNALS = [
    'Вестник компьютерных и информационных технологий', 'Информационные технологии',
    'Программная инженерия', 'Вопросы кибербезопасности', 'Системы управления, связь и безопасность',
    'Прикладная информатика', 'Известия вузов. Приборостроение', 'Journal of Physics: Conference Series',
    'IEEE Access', 'Mathematics',
]
PUBLISHERS = ['Лань', 'Юрайт', 'Издательство вуза', 'Инфра-М', 'Наука']
EXTERNAL_AUTHORS = [
    'Белов А. А.', 'Захарова И. В.', 'Тихонов Р. С.', 'Чернова Л. М.', 'Kim J.', 'Müller T.',
    'Комаров Е. Н.', 'Семёнова Д. А.',
]
CONFERENCES = [
    ('Международная научная конференция «Информационные технологии и системы»', Conference.Level.INTERNATIONAL,
     'Москва'),
    ('International Conference on Data Science and Applications', Conference.Level.INTERNATIONAL, 'онлайн'),
    ('Всероссийская конференция «Математическое моделирование и информационные технологии»',
     Conference.Level.NATIONAL, 'Санкт-Петербург'),
    ('Всероссийская научно-техническая конференция «Безопасность информационных систем»',
     Conference.Level.NATIONAL, 'Казань'),
    ('Региональная конференция молодых учёных «Наука и инновации»', Conference.Level.REGIONAL, 'Самара'),
    ('Научная конференция профессорско-преподавательского состава университета', Conference.Level.UNIVERSITY,
     'Самара'),
    ('Научно-практический семинар «Цифровая трансформация промышленности»', Conference.Level.REGIONAL, 'Тольятти'),
]
PROJECTS = [
    ('Разработка платформы прогнозной аналитики для предприятий машиностроения', ResearchProject.Status.IN_PROGRESS),
    ('Методы защиты промышленных сетей от целевых атак', ResearchProject.Status.COMPLETED),
    ('Цифровой двойник линии механической обработки', ResearchProject.Status.IN_PROGRESS),
    ('Распределённая система обработки телеметрии', ResearchProject.Status.PLANNED),
    ('Интеллектуальная система мониторинга энергопотребления', ResearchProject.Status.COMPLETED),
    ('Модели теплопереноса в многослойных материалах', ResearchProject.Status.SUSPENDED),
    ('Сервис автоматической проверки технической документации', ResearchProject.Status.CANCELLED),
]


class Command(DevOnlyCommand):
    help = 'Заполняет базу демонстрационными данными (все разделы) и создаёт демо-пользователей.'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--seed', type=int, default=2026, help='Зерно генератора: одинаковое зерно — одинаковые данные.'
        )
        parser.add_argument(
            '--clear', action='store_true', help='Сначала очистить базу (как clear_data, admin сохраняется).'
        )

    def handle(self, *args, **options):
        self.check_environment(options)
        if options['clear']:
            clear_data('admin')
        elif has_domain_data():
            self.stderr.write(self.style.WARNING(
                'В базе уже есть данные — демонстрационные данные не добавлены, чтобы не было дублей. '
                'Запустите с --clear, чтобы очистить базу перед заполнением (admin сохранится).'
            ))
            return

        with transaction.atomic():
            DemoData(random.Random(options['seed'])).create()

        self.print_counts('Создано:', domain_counts())
        self.stdout.write(self.style.SUCCESS('Демонстрационные данные созданы.'))
        self.stdout.write(f'Демо-пользователи (пароль у всех — {DEMO_PASSWORD}):')
        self.stdout.write('  editor — редактор (группа «Редакторы НИР»)')
        for login, teacher in DemoData.demo_logins():
            self.stdout.write(f'  {login} — преподаватель {teacher} (группа «Преподаватели»)')


def save(obj):
    obj.full_clean()
    obj.save()
    return obj


class DemoData:
    def __init__(self, rnd):
        self.rnd = rnd
        self.today = timezone.localdate()
        self.first_year, self.last_year = report_period(self.today)
        self.title_counter = 0

    @staticmethod
    def demo_logins():
        return [(login, f'{last} {first[0]}. {middle[0]}.') for last, first, middle, *_, login, _ in TEACHERS if login]

    # --- вспомогательное ---

    def year(self, recent_share=0.8):
        """Год: чаще — внутри отчётного периода, иногда — до него (такие записи не попадают в показатели)."""
        if self.rnd.random() < recent_share:
            return self.rnd.randint(self.first_year, self.last_year)
        return self.rnd.randint(self.first_year - 4, self.first_year - 1)

    def date_in(self, year):
        start = datetime.date(year, 1, 1)
        end = min(datetime.date(year, 12, 31), self.today)
        return start + datetime.timedelta(days=self.rnd.randint(0, (end - start).days))

    def title(self):
        self.title_counter += 1
        prefix = self.rnd.choice(TITLE_PREFIXES)
        return f'{prefix}: {self.rnd.choice(TOPICS)}' if prefix.startswith('Об') else \
            f'{prefix} — {self.rnd.choice(TOPICS)} (№ {self.title_counter})'

    def pick_teachers(self, low=1, high=3, pool=None):
        return self.rnd.sample(pool or self.active, self.rnd.randint(low, high))

    def add_authors(self, model, link_field, record, teachers, external_chance=0.3):
        rows = [{'teacher': teacher} for teacher in teachers]
        if self.rnd.random() < external_chance:
            rows.insert(self.rnd.randint(0, len(rows)), {'external_name': self.rnd.choice(EXTERNAL_AUTHORS)})
        for order, row in enumerate(rows, start=1):
            save(model(**{link_field: record}, order=order, **row))

    # --- разделы ---

    def create(self):
        self.create_teachers()
        self.create_users()
        self.create_schools()
        self.create_projects()
        self.create_publications()
        self.create_intellectual_properties()
        self.create_conferences()
        self.create_defenses()

    def create_teachers(self):
        self.teachers = []
        for last, first, middle, position, degree, title, login, is_active in TEACHERS:
            slug = login or 'teacher'
            self.teachers.append(save(Teacher(
                last_name=last, first_name=first, middle_name=middle, position=position, degree=degree,
                academic_title=title, is_active=is_active,
                email=f'{slug}{len(self.teachers) + 1}@demo-university.ru',
                phone=f'+7 (846) 200-{len(self.teachers) + 10:02d}-00',
            )))
        self.active = [teacher for teacher in self.teachers if teacher.is_active]
        # Преподаватели с демо-учётными записями — среди авторов чаще остальных.
        self.demo_teachers = [teacher for teacher, row in zip(self.teachers, TEACHERS) if row[6]]

    def create_users(self):
        def demo_user(username, **fields):
            user, _ = User.objects.update_or_create(username=username, defaults=fields)
            user.set_password(DEMO_PASSWORD)
            user.save()
            return user

        editor = demo_user('editor', first_name='Редактор', last_name='', is_staff=True)
        editor.groups.add(Group.objects.get(name='Редакторы НИР'))
        teachers_group = Group.objects.get(name='Преподаватели')
        for teacher, row in zip(self.teachers, TEACHERS):
            if row[6]:
                user = demo_user(row[6], first_name=teacher.first_name, last_name=teacher.last_name, is_staff=False)
                user.groups.add(teachers_group)
                teacher.user = user
                teacher.save()

    def create_schools(self):
        self.schools = []
        for name, leader_indexes, is_active in SCHOOLS:
            school = save(ScientificSchool(name=name, is_active=is_active,
                                           description=f'Научное направление кафедры: {name.lower()}.'))
            school.leaders.set(self.teachers[i] for i in leader_indexes)
            self.schools.append(school)
        self.active_schools = [school for school in self.schools if school.is_active]

    def create_projects(self):
        self.projects = []
        for title, status in PROJECTS:
            start_year = self.year(recent_share=0.7)
            start = self.date_in(start_year)
            end = None
            finished = status in (ResearchProject.Status.COMPLETED, ResearchProject.Status.CANCELLED)
            if finished or self.rnd.random() < 0.4:
                duration = datetime.timedelta(days=self.rnd.randint(300, 1100))
                end = min(start + duration, datetime.date(self.last_year, 12, 31))
            project = save(ResearchProject(title=title, start_date=start, end_date=end, status=status))
            leader, *members = self.pick_teachers(3, 5)
            save(Participant(project=project, teacher=leader, role=Participant.Role.LEADER))
            for member in members:
                save(Participant(project=project, teacher=member, role=Participant.Role.MEMBER))
            self.projects.append(project)

    def create_publications(self):
        kinds = list(Publication.Kind)  # первые записи — по одной каждого вида
        kinds += self.rnd.choices(
            [Publication.Kind.ARTICLE, Publication.Kind.THESES, Publication.Kind.MONOGRAPH,
             Publication.Kind.MONOGRAPH_CHAPTER, Publication.Kind.TEXTBOOK, Publication.Kind.STUDY_GUIDE],
            weights=[62, 16, 6, 5, 3, 8], k=44,
        )
        self.theses = []
        for index, kind in enumerate(kinds):
            # Первые монографии — в периоде, чтобы показатели школ были ненулевыми.
            year = self.last_year - index % 3 if index < len(Publication.Kind) else self.year()
            publication = Publication(kind=kind, title=self.title(), year=year)
            self.fill_imprint(publication)
            save(publication)
            teachers = self.pick_teachers(1, 3)
            demo = self.demo_teachers[index % len(self.demo_teachers)]
            if index % 3 == 0 and demo not in teachers:
                teachers[0] = demo
            self.add_authors(PublicationAuthor, 'publication', publication, teachers)
            self.link_schools(publication, index)
            if kind == Publication.Kind.THESES:
                self.theses.append(publication)

    def fill_imprint(self, publication):
        rnd, kind = self.rnd, publication.kind
        if kind == Publication.Kind.ARTICLE:
            publication.source = rnd.choice(JOURNALS)
            publication.volume = str(rnd.randint(5, 30))
            publication.issue = str(rnd.randint(1, 12))
            first_page = rnd.randint(3, 180)
            publication.pages = f'{first_page}–{first_page + rnd.randint(6, 18)}'
            publication.vak = rnd.choices(['', 'K1', 'K2', 'K3'], weights=[20, 25, 35, 20])[0]
            publication.rinc = rnd.random() < 0.85
            publication.rinc_core = publication.rinc and rnd.random() < 0.25
            publication.scopus = rnd.random() < 0.3
            publication.wos = publication.scopus and rnd.random() < 0.4
            if publication.scopus:
                publication.quartile = rnd.choice(['Q1', 'Q2', 'Q3', 'Q4'])
                publication.doi = f'10.{rnd.randint(1000, 9999)}/demo.{publication.year}.{self.title_counter:03d}'
        elif kind == Publication.Kind.THESES:
            publication.source = 'Сборник трудов конференции'
            publication.pages = f'{rnd.randint(10, 300)}–{rnd.randint(301, 320)}'
            publication.rinc = rnd.random() < 0.6
        elif kind == Publication.Kind.MONOGRAPH_CHAPTER:
            publication.source = f'Коллективная монография. — {rnd.choice(PUBLISHERS)}'
            publication.pages = f'{rnd.randint(10, 100)}–{rnd.randint(101, 150)}'
            publication.rinc = True
        else:
            publication.source = rnd.choice(PUBLISHERS)
            publication.pages = f'{rnd.randint(120, 420)} с.'
            publication.rinc = rnd.random() < 0.7
        if rnd.random() < 0.3:
            publication.project = rnd.choice(self.projects)

    def link_schools(self, record, index):
        roll = self.rnd.random()
        if index < len(Publication.Kind) or roll < 0.75:
            record.schools.add(self.active_schools[index % len(self.active_schools)])
        if roll > 0.9:  # иногда — сразу к двум школам
            record.schools.add(*self.rnd.sample(self.active_schools, 2))
        if roll < 0.05:
            record.schools.add(self.schools[-1])  # недействующая школа

    def create_intellectual_properties(self):
        kinds = list(IntellectualProperty.Kind) * 2
        for index, kind in enumerate(kinds):
            registration = self.date_in(self.year(recent_share=0.85))
            item = save(IntellectualProperty(
                kind=kind, title=self.title(), number=str(2_020_610_000 + index * 37),
                application_date=registration - datetime.timedelta(days=self.rnd.randint(40, 300)),
                registration_date=registration, holder=UNIVERSITY,
                project=self.rnd.choice(self.projects) if self.rnd.random() < 0.4 else None,
            ))
            self.add_authors(IntellectualPropertyAuthor, 'intellectual_property', item, self.pick_teachers(1, 3),
                             external_chance=0.15)
            self.link_schools(item, index)

    def create_conferences(self):
        unused_theses = list(self.theses)
        for title, level, location in CONFERENCES:
            start = self.date_in(self.year(recent_share=0.85))
            conference = save(Conference(
                title=title, level=level, location=location, start_date=start,
                end_date=start + datetime.timedelta(days=self.rnd.randint(0, 3)),
                url='https://conf.demo-university.ru/' if self.rnd.random() < 0.5 else '',
            ))
            for _ in range(self.rnd.randint(2, 4)):
                matching = [p for p in unused_theses if p.year == start.year]
                publication = matching[0] if matching and self.rnd.random() < 0.7 else None
                if publication:
                    unused_theses.remove(publication)
                report = save(Report(
                    conference=conference, title=publication.title if publication else self.title(),
                    form=self.rnd.choices(list(Report.Form), weights=[15, 70, 15])[0], publication=publication,
                ))
                speakers = [a.teacher for a in publication.authors.all() if a.teacher_id] if publication else []
                self.add_authors(ReportSpeaker, 'report', report, speakers or self.pick_teachers(1, 2),
                                 external_chance=0.2)

    def create_defenses(self):
        # Защитившиеся сотрудники — те, чья степень в карточке соответствует виду защиты.
        candidates = [
            ('Морозова Анна Сергеевна', self.teachers[5]), ('Лебедева Татьяна Александровна', self.teachers[7]),
            ('Рябов Константин Евгеньевич', None), ('Ахмедова Лейла Руслановна', None),
            ('Зайцев Павел Олегович', None), ('Ли Вэй', None), ('Тарасов Глеб Ильич', None),
        ]
        doctors = [('Кузнецова Ольга Николаевна', self.teachers[3]), ('Белов Андрей Андреевич', None)]
        defenses = [(n, t, DissertationDefense.Kind.CANDIDATE) for n, t in candidates]
        for position, (name, teacher) in zip([1, 4], doctors):  # докторские — среди первых, то есть в периоде
            defenses.insert(position, (name, teacher, DissertationDefense.Kind.DOCTOR))
        for index, (full_name, teacher, kind) in enumerate(defenses):
            school = self.active_schools[index % len(self.active_schools)]
            year = self.last_year - index % 4 if index < 6 else self.year(recent_share=0.3)
            save(DissertationDefense(
                full_name=full_name, teacher=teacher, kind=kind, title=f'{self.rnd.choice(TITLE_PREFIXES)} — '
                f'{self.rnd.choice(TOPICS)}', defense_date=self.date_in(year), school=school,
                supervisor=self.rnd.choice(list(school.leaders.all())),
            ))
