import datetime
from urllib.parse import unquote

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.adjuncts.models import PlanStage
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.publications.models import Publication
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_achievement, make_student, make_teacher_user

from .access import person_report_url
from .cards import account_card, person_card
from .docx_common import DOCX_TYPE
from .test_person_reports import docx_text, project
from .tests import publication

ACCOUNT = reverse('reports:account')


def info(document):
    return dict(document.info)


class PersonCardTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher(last_name='Руководителев', email='ruk@example.ru', phone='+7 900 000-00-00')
        self.teacher_user = make_teacher_user(self.teacher)
        self.student = make_student(last_name='Курсантов', supervisor=self.teacher, note='Победитель олимпиады')
        self.student_user = make_student_user(self.student)
        self.adjunct = make_adjunct(self.teacher, last_name='Адъюнктов', email='adj@example.ru')
        publication('Статья', 2024, authors=[{'teacher': self.teacher}, {'student': self.student}], vak='K2')
        publication('Пособие', 2025, Publication.Kind.STUDY_GUIDE, authors=[{'teacher': self.teacher}])
        project('НИОКР', datetime.date(2024, 1, 1), leader=self.teacher)
        make_achievement(self.student)
        PlanStage.objects.create(adjunct=self.adjunct, study_year=1, title='Экзамен', kind='exam',
                                 due_date=datetime.date(2020, 1, 1), status=PlanStage.Status.DONE)

    def test_teacher_card(self):
        document = person_card(self.teacher, show_account=True)
        fields = info(document)
        self.assertEqual(document.title, 'Карточка преподавателя')
        self.assertEqual(fields['E-mail'], 'ruk@example.ru')
        self.assertEqual(fields['Телефон'], '+7 900 000-00-00')
        self.assertEqual(fields['Учётная запись (логин)'], 'teacher')
        projects, supervised, summary = (section.table for section in document.sections)
        self.assertEqual(projects.rows[0].cells[:2], ['НИОКР', 'руководитель'])
        self.assertEqual([row.cells[0] for row in supervised.rows],
                         [self.adjunct.full_name, self.student.full_name])
        summary = {row.cells[0]: row.cells[1] for row in summary.rows}
        self.assertEqual(summary['Публикации — всего'], '2')
        self.assertEqual(summary['вид: учебное пособие'], '1')
        self.assertEqual(summary['из них ВАК'], '1')

    def test_student_and_adjunct_cards(self):
        fields = info(person_card(self.student, show_account=False))
        self.assertEqual(fields['Научный руководитель'], self.teacher.full_name)
        self.assertEqual(fields['Примечание'], 'Победитель олимпиады')
        self.assertNotIn('Учётная запись (логин)', fields)
        document = person_card(self.adjunct, show_account=False)
        self.assertEqual(info(document)['E-mail'], 'adj@example.ru')
        plan = {row.cells[0]: row.cells[1] for row in document.sections[0].table.rows}
        self.assertEqual(plan, {'Этапов плана всего': '1', 'Выполнено': '1', 'Просрочено': '0'})

    def test_login_is_shown_to_editor_and_self_only(self):
        url = person_report_url('card', self.student)
        for user, shown in ((make_editor(), True), (self.student_user, True), (self.teacher_user, False)):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                fields = info(self.client.get(url).context['document'])
                self.assertEqual('Учётная запись (логин)' in fields, shown)

    def test_page_and_docx(self):
        self.client.force_login(self.teacher_user)
        url = person_report_url('card', self.student)
        page = self.client.get(url)
        self.assertContains(page, 'Карточка курсанта')
        self.assertContains(page, 'Версия для печати')
        self.assertContains(page, self.student.get_absolute_url())  # назад к карточке
        response = self.client.get(url, {'format': 'docx'})
        self.assertEqual(response['Content-Type'], DOCX_TYPE)
        disposition = unquote(response['Content-Disposition'])
        self.assertIn(f'filename="card_student_{self.student.pk}.docx"', disposition)
        self.assertIn('Карточка_Курсантов_П_И.docx', disposition)
        text = docx_text(response)
        self.assertIn('Карточка курсанта', text)
        self.assertIn('Победитель олимпиады', text)


class AccountCardTests(TestCase):
    def setUp(self):
        self.editor = make_editor()
        self.editor.first_name, self.editor.last_name, self.editor.email = 'Ирина', 'Редакторова', 'ed@example.ru'
        self.editor.save()
        self.root = User.objects.create_superuser('root', password='secret')
        self.teacher = make_teacher()
        self.teacher_user = make_teacher_user(self.teacher)
        self.reader = User.objects.create_user('reader', password='secret')

    def test_content(self):
        fields = info(account_card(self.editor))
        self.assertEqual(fields['Логин'], 'editor')
        self.assertEqual(fields['ФИО'], 'Ирина Редакторова')
        self.assertEqual(fields['Роль'], 'редактор')
        self.assertEqual(fields['Группы'], 'Редакторы НИР')
        self.assertEqual(fields['Последний вход'], 'не входил')
        self.assertEqual(fields['Привязанная карточка человека'], '—')
        fields = info(account_card(self.teacher_user))
        self.assertEqual(fields['Роль'], 'преподаватель')
        self.assertEqual(fields['Привязанная карточка человека'], f'{self.teacher.full_name} (карточка преподавателя)')
        self.assertEqual(info(account_card(self.root))['Роль'], 'администратор (суперпользователь)')
        self.assertEqual(info(account_card(self.reader))['Роль'], 'пользователь без карточки человека')

    def test_own_card_for_everyone(self):
        student_user = make_student_user(make_student(supervisor=self.teacher))
        adjunct_user = make_adjunct_user(make_adjunct(self.teacher))
        for user in (self.editor, self.root, self.teacher_user, student_user, adjunct_user, self.reader):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                page = self.client.get(ACCOUNT)
                self.assertEqual(page.status_code, 200)
                self.assertEqual(info(page.context['document'])['Логин'], user.username)
                self.assertContains(page, f'href="{ACCOUNT}"')  # ссылка в шапке
                response = self.client.get(ACCOUNT, {'format': 'docx'})
                self.assertIn(f'filename="account_{user.pk}.docx"', response['Content-Disposition'])
        self.client.logout()
        self.assertRedirects(self.client.get(ACCOUNT), f'{reverse("login")}?next={ACCOUNT}')

    def test_other_account_only_for_superuser(self):
        url = reverse('reports:account_user', args=[self.editor.pk])
        self.client.force_login(self.root)
        self.assertEqual(info(self.client.get(url).context['document'])['Логин'], 'editor')
        self.assertEqual(self.client.get(reverse('reports:account_user', args=[9999])).status_code, 404)
        # Своя карточка по адресу с pk — та же своя; чужая — только суперпользователю (кабинету адрес закрыт).
        for user, status in ((self.editor, 200), (self.reader, 404), (self.teacher_user, 403)):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(url).status_code, status)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(reverse('reports:account_user', args=[self.root.pk])).status_code, 404)

    def test_groups_are_listed(self):
        self.reader.groups.add(Group.objects.get(name='Преподаватели'))
        self.assertEqual(info(account_card(self.reader))['Группы'], 'Преподаватели')
