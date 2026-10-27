import datetime
import random

from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.adjuncts.models import Adjunct, AdjunctAchievement, PlanStage, Task, TaskComment
from apps.adjuncts.study import ACADEMIC_YEAR_START
from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.publications.models import Publication, PublicationAuthor
from apps.research.models import Participant, ResearchProject
from apps.schools.models import DissertationDefense, ScientificSchool
from apps.schools.period import report_period
from apps.staff.models import Teacher, author_lookup
from apps.students.models import Student, StudentAchievement

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
# Фамилия, имя, отчество курсанта. Курс, группа, статус и руководитель задаются в DemoData.create_students.
STUDENTS = [
    ('Алексеев', 'Никита', 'Романович'), ('Белова', 'Дарья', 'Андреевна'), ('Васильев', 'Кирилл', 'Олегович'),
    ('Гусева', 'Полина', 'Сергеевна'), ('Демидов', 'Егор', 'Максимович'), ('Ершова', 'Виктория', 'Игоревна'),
    ('Жуков', 'Арсений', 'Дмитриевич'), ('Зуева', 'Алина', 'Павловна'), ('Ильин', 'Матвей', 'Александрович'),
    ('Карпова', 'Софья', 'Евгеньевна'), ('Лаптев', 'Георгий', 'Витальевич'), ('Медведева', 'Ева', 'Романовна'),
    ('Никитин', 'Тимур', 'Ильдарович'), ('Осипова', 'Ульяна', 'Константиновна'), ('Прохоров', 'Данила', 'Юрьевич'),
    ('Родионова', 'Вероника', 'Михайловна'), ('Савельев', 'Иван', 'Борисович'), ('Титова', 'Злата', 'Олеговна'),
    ('Уткин', 'Роман', 'Сергеевич'), ('Филиппова', 'Арина', 'Владимировна'), ('Хохлов', 'Ярослав', 'Петрович'),
    ('Цветкова', 'Мирослава', 'Андреевна'), ('Шаров', 'Лев', 'Николаевич'), ('Юдина', 'Маргарита', ''),
]
ACHIEVEMENT_TITLES = {
    StudentAchievement.Kind.OLYMPIAD: ['Олимпиада по информационной безопасности', 'Олимпиада по программированию'],
    StudentAchievement.Kind.CONTEST: ['Конкурс научных работ курсантов и студентов', 'Конкурс «Молодой учёный»'],
    StudentAchievement.Kind.GRANT: ['Грант «Студенческий стартап»', 'Грант на проведение НИР молодыми учёными'],
    StudentAchievement.Kind.SCHOLARSHIP: ['Именная стипендия учёного совета', 'Стипендия Правительства РФ'],
    StudentAchievement.Kind.EXHIBITION: ['Выставка научно-технического творчества молодёжи', 'Выставка «Архимед»'],
    StudentAchievement.Kind.OTHER: ['Хакатон по анализу данных', 'Соревнования CTF по защите информации'],
}
ACHIEVEMENT_RESULTS = ['диплом I степени', 'диплом II степени', 'диплом III степени', 'победитель', 'призёр',
                       'участник', 'лауреат']

A = Adjunct.Status
# Фамилия, имя, отчество, курс в текущем учебном году (по нему вычисляется год поступления), срок обучения,
# статус, индекс руководителя в TEACHERS, логин демо-пользователя (или None).
ADJUNCTS = [
    ('Кравцов', 'Антон', 'Сергеевич', 3, 3, A.STUDYING, 0, 'adjunct1'),
    ('Мельникова', 'Ирина', 'Олеговна', 2, 3, A.STUDYING, 0, 'adjunct2'),
    ('Борисов', 'Денис', 'Алексеевич', 1, 4, A.STUDYING, 1, None),
    ('Голубев', 'Станислав', 'Игоревич', 4, 3, A.STUDYING, 2, None),  # срок обучения истёк
    ('Ефимова', 'Юлия', 'Викторовна', 2, 3, A.ACADEMIC_LEAVE, 1, None),
    ('Сафонова', 'Елизавета', 'Романовна', 6, 3, A.GRADUATED, 3, None),
    ('Рябов', 'Константин', 'Евгеньевич', 7, 3, A.DEFENDED, 0, None),  # связан с защитой диссертации
]
SPECIALTIES = ['2.3.6. Методы и системы защиты информации, информационная безопасность',
               '2.3.5. Математическое и программное обеспечение вычислительных систем',
               '1.2.2. Математическое моделирование, численные методы и комплексы программ']
# Этапы индивидуального плана по годам обучения: вид, наименование, месяц и день срока в учебном году.
PLAN_TEMPLATE = {
    1: [(PlanStage.Kind.EXAM, 'Кандидатский экзамен по истории и философии науки', 1, 25),
        (PlanStage.Kind.EXAM, 'Кандидатский экзамен по иностранному языку', 6, 20),
        (PlanStage.Kind.PUBLICATION, 'Статья в журнале из перечня ВАК', 6, 30)],
    2: [(PlanStage.Kind.EXAM, 'Кандидатский экзамен по научной специальности', 1, 30),
        (PlanStage.Kind.CHAPTER, 'Глава 1: обзор и постановка задачи', 3, 31),
        (PlanStage.Kind.APPROBATION, 'Доклад на всероссийской конференции', 5, 15)],
    3: [(PlanStage.Kind.CHAPTER, 'Главы 2–3: методы и экспериментальные исследования', 12, 20),
        (PlanStage.Kind.PUBLICATION, 'Статья в издании, индексируемом в Scopus', 3, 1),
        (PlanStage.Kind.PRE_DEFENSE, 'Предзащита на заседании кафедры', 6, 10)],
    4: [(PlanStage.Kind.OTHER, 'Подготовка документов к защите', 4, 30)],
}
TASK_TITLES = [
    'Подготовить обзор литературы по теме диссертации', 'Оформить статью по требованиям журнала',
    'Провести серию экспериментов на тестовом наборе данных', 'Подготовить презентацию к докладу',
    'Исправить замечания к главе 1', 'Составить план второй главы', 'Подать тезисы на конференцию',
    'Сравнить результаты с базовыми методами',
]
SUPERVISOR_COMMENTS = ['Посмотрите свежие работы за последние два года.', 'Срок можно сдвинуть на неделю.',
                       'Хорошо, но добавьте сравнение с аналогами.', 'Жду черновик к следующей встрече.']
ADJUNCT_COMMENTS = ['Начал(а) работу, черновик будет к пятнице.', 'Есть вопрос по структуре, обсудим на встрече?',
                    'Загрузил(а) исправленную версию, прошу проверить.']


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
        for login, adjunct in DemoData.adjunct_logins():
            self.stdout.write(f'  {login} — адъюнкт {adjunct} (группа «Адъюнкты»), руководитель — ivanov')


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

    @staticmethod
    def adjunct_logins():
        return [(login, f'{last} {first[0]}. {middle[0]}.') for last, first, middle, *_, login in ADJUNCTS if login]

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

    def with_student(self, teachers):
        """Добавляет к авторам курсанта — подопечного кого-то из них, а если таких нет — любого."""
        own = [s for s in self.author_students if s.supervisor in teachers]
        return [*teachers, self.rnd.choice(own or self.author_students)]

    def with_adjunct(self, teachers):
        """Добавляет к авторам адъюнкта — подопечного кого-то из них, а если таких нет — любого."""
        own = [a for a in self.author_adjuncts if a.supervisor in teachers]
        return [*teachers, self.rnd.choice(own or self.author_adjuncts)]

    def demo_user(self, username, group_name, **fields):
        user, _ = User.objects.update_or_create(username=username, defaults=fields)
        user.set_password(DEMO_PASSWORD)
        user.save()
        user.groups.add(Group.objects.get(name=group_name))
        return user

    def add_authors(self, model, link_field, record, people, external_chance=0.3):
        """people — преподаватели, курсанты и адъюнкты в порядке авторов; иногда добавляется внешний автор."""
        rows = [author_lookup(person) for person in people]
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
        self.create_students()
        self.create_adjuncts()
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
        self.demo_user('editor', 'Редакторы НИР', first_name='Редактор', last_name='', is_staff=True)
        for teacher, row in zip(self.teachers, TEACHERS):
            if row[6]:
                teacher.user = self.demo_user(row[6], 'Преподаватели', first_name=teacher.first_name,
                                              last_name=teacher.last_name, is_staff=False)
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

    def create_students(self):
        self.students = []
        for index, (last, first, middle) in enumerate(STUDENTS):
            course = 1 + index % 5
            status = Student.Status.STUDYING
            if index >= len(STUDENTS) - 3:
                course, status = 5, Student.Status.GRADUATED
            elif index == len(STUDENTS) - 4:
                status = Student.Status.EXPELLED
            # Первые курсанты — подопечные демо-преподавателя ivanov; у части первокурсников руководителя нет.
            if index < 5:
                supervisor = self.demo_teachers[0]
            elif course == 1 and index % 2:
                supervisor = None
            else:
                supervisor = self.rnd.choice(self.active[:10])
            self.students.append(save(Student(
                last_name=last, first_name=first, middle_name=middle, course=course, status=status,
                group=f'{"ИБ" if index % 2 else "ПИ"}-{course}{1 + index % 3}', supervisor=supervisor,
            )))
        self.author_students = [s for s in self.students if s.status != Student.Status.EXPELLED]

        kinds = list(StudentAchievement.Kind) + self.rnd.choices(list(StudentAchievement.Kind), k=14)
        levels = list(StudentAchievement.Level)
        for index, kind in enumerate(kinds):
            # Первые достижения — у подопечных ivanov, чтобы демо-преподавателю было что вести.
            student = self.students[index % 5] if index < 5 else self.rnd.choice(self.author_students)
            level = levels[index % len(levels)] if index < len(levels) * 2 else self.rnd.choice(levels)
            save(StudentAchievement(
                student=student, kind=kind, level=level,
                title=self.rnd.choice(ACHIEVEMENT_TITLES[kind]), result=self.rnd.choice(ACHIEVEMENT_RESULTS),
                date=self.date_in(self.year(recent_share=0.9)), supervisor=student.supervisor,
                document=f'Диплом № {self.rnd.randint(100, 999)}' if self.rnd.random() < 0.5 else '',
            ))

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
            if index % 4 == 1:
                teachers = self.with_student(teachers)
            if index % 5 == 2:
                teachers = self.with_adjunct(teachers)
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
            authors = self.pick_teachers(1, 3)
            if index in (1, 6):
                authors = self.with_student(authors)
            if index == 3:
                authors = self.with_adjunct(authors)
            self.add_authors(IntellectualPropertyAuthor, 'intellectual_property', item, authors, external_chance=0.15)
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
                if publication:
                    speakers = [a.person for a in publication.authors.all() if not a.external_name]
                else:
                    speakers = self.pick_teachers(1, 2)
                    if self.rnd.random() < 0.3:
                        speakers = self.with_student(speakers)
                    elif self.rnd.random() < 0.3:
                        speakers = self.with_adjunct(speakers)
                self.add_authors(ReportSpeaker, 'report', report, speakers, external_chance=0.2)

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
            adjunct = self.defended_adjunct if full_name == self.defended_adjunct.full_name else None
            save(DissertationDefense(
                full_name=full_name, teacher=teacher, adjunct=adjunct, kind=kind,
                title=adjunct.dissertation_topic if adjunct else f'{self.rnd.choice(TITLE_PREFIXES)} — '
                f'{self.rnd.choice(TOPICS)}', defense_date=self.date_in(year), school=school,
                supervisor=adjunct.supervisor if adjunct else self.rnd.choice(list(school.leaders.all())),
            ))

    def create_adjuncts(self):
        # Год поступления нынешнего первого курса: учебный год начинается 1 сентября.
        started = (self.today.month, self.today.day) >= ACADEMIC_YEAR_START
        first_course_year = self.today.year if started else self.today.year - 1
        self.adjuncts = []
        for index, (last, first, middle, course, years, status, supervisor_index, login) in enumerate(ADJUNCTS):
            admission_year = first_course_year - (course - 1)
            adjunct = save(Adjunct(
                last_name=last, first_name=first, middle_name=middle, admission_year=admission_year,
                dissertation_topic=f'{self.rnd.choice(TITLE_PREFIXES)} — {self.rnd.choice(TOPICS)}',
                specialty=SPECIALTIES[index % len(SPECIALTIES)], study_years=years, status=status,
                study_form=Adjunct.StudyForm.PART_TIME if years == 4 else Adjunct.StudyForm.FULL_TIME,
                supervisor=self.teachers[supervisor_index], planned_defense_year=admission_year + years,
                school=self.active_schools[0] if index in (0, 6) else self.rnd.choice(self.active_schools),
                email=f'{login or "adjunct"}{index + 1}@demo-university.ru',
            ))
            if login:
                adjunct.user = self.demo_user(login, 'Адъюнкты', first_name=first, last_name=last, is_staff=False)
                adjunct.save()
            self.adjuncts.append(adjunct)
            if status == Adjunct.Status.STUDYING:
                stages = self.create_plan(adjunct)
                self.create_tasks(adjunct, stages, count=6 if index == 0 else self.rnd.randint(3, 5))
                for _ in range(self.rnd.randint(1, 3)):
                    kind = self.rnd.choice(list(AdjunctAchievement.Kind))
                    save(AdjunctAchievement(
                        adjunct=adjunct, kind=kind, level=self.rnd.choice(list(AdjunctAchievement.Level)),
                        title=self.rnd.choice(ACHIEVEMENT_TITLES[kind]), result=self.rnd.choice(ACHIEVEMENT_RESULTS),
                        date=self.date_in(self.rnd.randint(admission_year, self.today.year)),
                    ))
        self.defended_adjunct = self.adjuncts[-1]
        self.author_adjuncts = [a for a in self.adjuncts if a.status != Adjunct.Status.EXPELLED]

    def create_plan(self, adjunct):
        """План на все годы обучения: прошедшие этапы чаще выполнены, будущие — запланированы."""
        stages = []
        for study_year in range(1, adjunct.study_years + 1):
            for kind, title, month, day in PLAN_TEMPLATE[study_year]:
                # Учебный год N идёт с сентября года «поступление + N − 1» по август следующего.
                year = adjunct.admission_year + study_year - 1 + (0 if month >= 9 else 1)
                due = datetime.date(year, month, day)
                if due < self.today:
                    status = PlanStage.Status.FAILED if self.rnd.random() < 0.1 else PlanStage.Status.DONE
                elif due < self.today + datetime.timedelta(days=120):
                    status = PlanStage.Status.IN_PROGRESS
                else:
                    status = PlanStage.Status.PLANNED
                done = status == PlanStage.Status.DONE
                stages.append(save(PlanStage(
                    adjunct=adjunct, study_year=study_year, kind=kind, title=title, due_date=due, status=status,
                    completed_date=due - datetime.timedelta(days=self.rnd.randint(0, 20)) if done else None,
                    supervisor_note='Выполнено в срок.' if done and self.rnd.random() < 0.4 else '',
                )))
        return stages

    def create_tasks(self, adjunct, stages, count):
        """Задачи во всех статусах (часть просрочена) с обсуждением руководителя и адъюнкта."""
        supervisor_user, adjunct_user = adjunct.supervisor.user, adjunct.user
        statuses = [Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVIEW, Task.Status.DONE,
                    Task.Status.CANCELLED, Task.Status.IN_PROGRESS]
        now = timezone.now()
        for index, (status, title) in enumerate(zip(statuses[:count], self.rnd.sample(TASK_TITLES, count))):
            created = now - datetime.timedelta(days=self.rnd.randint(10, 60))
            # Каждая вторая открытая задача — со сроком в прошлом (просрочена).
            overdue = status in Task.OPEN_STATUSES and index % 2 == 1
            shift = -self.rnd.randint(3, 15) if overdue else self.rnd.randint(5, 40)
            due = self.today + datetime.timedelta(days=shift)
            task = Task(
                adjunct=adjunct, title=title, created_by=supervisor_user, created_at=created, due_date=due,
                priority=self.rnd.choice(list(Task.Priority)),
                description=f'{title}. Результат обсудить на встрече.',
                plan_stage=self.rnd.choice(stages) if self.rnd.random() < 0.5 else None,
            )
            task.set_status(status)
            save(task)
            moment = created
            for author, texts in [(supervisor_user, SUPERVISOR_COMMENTS), (adjunct_user, ADJUNCT_COMMENTS)]:
                if author is not None and self.rnd.random() < 0.8:
                    moment += datetime.timedelta(hours=self.rnd.randint(2, 48))
                    save(TaskComment(task=task, author=author, text=self.rnd.choice(texts), created_at=moment))
            if status != Task.Status.NEW:
                # Принимает и отменяет задачу руководитель, двигает по цепочке — адъюнкт (если у него есть вход).
                by_supervisor = status in (Task.Status.DONE, Task.Status.CANCELLED) or adjunct_user is None
                moment += datetime.timedelta(hours=self.rnd.randint(1, 24))
                save(TaskComment(
                    task=task, author=supervisor_user if by_supervisor else adjunct_user, is_system=True,
                    created_at=moment, text=f'Смена статуса: {Task.Status.NEW.label} → {task.get_status_display()}',
                ))
