"""Машинная матрица покрытия: каждый сценарий связан с разделом, URL, рисунком и тестами."""
from dataclasses import dataclass

from .content import GUIDES, chapters_for
from .guide_editor import DOMAINS


@dataclass(frozen=True)
class CoverageRow:
    role: str
    section: str
    action: str
    url: str
    chapter: str
    scenario: str
    screenshot: str
    test: str


CHAPTER_URLS = {
    'getting-started': '/login/', 'interface': '/', 'account-and-documents': '/reports/account/',
    'tasks': '/tasks/', 'reports': '/reports/', 'administration': '/admin/',
    'teacher-cabinet': '/', 'teacher-publications': '/publications/add/', 'teacher-ip': '/ip/add/',
    'teacher-conferences': '/conferences/reports/add/', 'teacher-students': '/students/',
    'teacher-adjuncts': '/adjuncts/', 'teacher-tasks': '/tasks/', 'teacher-reporting': '/reports/',
    'adjunct-cabinet': '/', 'adjunct-publications': '/publications/add/', 'adjunct-ip': '/ip/add/',
    'adjunct-conferences': '/conferences/reports/add/', 'adjunct-achievements': '/adjuncts/',
    'adjunct-plan': '/adjuncts/', 'adjunct-tasks': '/tasks/', 'adjunct-reporting': '/reports/',
    'student-cabinet': '/', 'student-publications': '/publications/add/', 'student-ip': '/ip/',
    'student-conferences': '/conferences/reports/add/', 'student-achievements': '/students/',
    'student-tasks': '/tasks/', 'student-reporting': '/reports/', 'reader-account': '/reports/account/',
}
CHAPTER_URLS.update({item['slug']: f"/{item['slug']}/" for item in DOMAINS})
CHAPTER_URLS['ip'] = '/ip/'
CHAPTER_URLS.update({f"reader-{item['slug']}": f"/{item['slug']}/" for item in DOMAINS})
CHAPTER_URLS['reader-ip'] = '/ip/'

SCENARIO_URLS = {
    'login': '/login/', 'logout-and-access': '/logout/', 'navigation': '/', 'lists-and-forms': '/',
    'profile': '/profile/', 'reports-and-print': '/reports/', 'using-help': '/help/',
    'publication-authors': '/publications/add/', 'ip-authors': '/ip/add/',
    'report-create': '/conferences/reports/add/', 'school-indicators': '/schools/',
    'school-defenses': '/schools/<school_id>/defenses/add/',
    'student-achievements': '/students/<student_id>/achievements/add/',
    'adjunct-achievements': '/adjuncts/<adjunct_id>/achievements/add/',
    'adjunct-plan': '/adjuncts/<adjunct_id>/plan/add/',
    'task-list-create': '/tasks/', 'task-create-edit': '/tasks/', 'task-status': '/tasks/<id>/',
    'task-comments': '/tasks/<id>/', 'person-reports': '/reports/', 'cooperation-report': '/reports/cooperation/',
    'department-report': '/reports/department/', 'cards-and-account': '/reports/account/',
    'admin-create-user': '/admin/accounts/user/add/', 'admin-groups': '/admin/accounts/user/<id>/change/',
    'admin-link-person': '/admin/', 'admin-data-and-log': '/reports/activity/',
    'publication-create': '/publications/add/', 'publication-edit-delete': '/publications/<id>/edit/',
    'ip-create': '/ip/add/', 'ip-edit-delete': '/ip/<id>/edit/', 'ip-view': '/ip/',
    'report-edit-delete': '/conferences/reports/<id>/edit/',
    'cabinet-navigation': '/', 'cabinet-contacts': '/profile/', 'teacher-research-schools': '/',
    'student-card': '/students/<id>/', 'adjunct-card': '/adjuncts/<id>/',
    'plan-manage': '/adjuncts/<adjunct_id>/plan/add/', 'plan-delete-and-progress': '/adjuncts/plan/<id>/edit/',
    'task-review': '/tasks/<id>/', 'own-reports': '/reports/', 'supervised-reports': '/reports/',
    'achievement-create': '/students/<student_id>/achievements/add/',
    'achievement-edit-delete': '/students/achievements/<id>/edit/',
    'plan-progress': '/adjuncts/', 'plan-start': '/adjuncts/plan/<id>/start/',
    'work-reports': '/reports/', 'plan-report': '/reports/plan/', 'print-card': '/reports/card/<kind>/<id>/',
    'reader-reports': '/reports/',
}
for _domain in DOMAINS:
    SCENARIO_URLS[f"{_domain['slug']}-list"] = f"/{_domain['slug']}/"
    SCENARIO_URLS[f"{_domain['slug']}-manage"] = f"/{_domain['slug']}/add/"
    SCENARIO_URLS[f"reader-{_domain['slug']}-list"] = f"/{_domain['slug']}/"
    SCENARIO_URLS[f"reader-{_domain['slug']}-detail"] = f"/{_domain['slug']}/<id>/"
SCENARIO_URLS['ip-list'] = '/ip/'
SCENARIO_URLS['ip-manage'] = '/ip/add/'
SCENARIO_URLS['reader-ip-list'] = '/ip/'
SCENARIO_URLS['reader-ip-detail'] = '/ip/<id>/'


def coverage_rows():
    rows = []
    test = ('apps.help.tests.PageTests.test_all_chapters_render_all_scenarios; '
            'apps.help.tests.ContentTests.test_pdf_files_are_complete')
    for role in GUIDES:
        for item in chapters_for(role):
            for scenario in item.scenarios:
                url = SCENARIO_URLS.get(scenario.slug, CHAPTER_URLS.get(item.slug, '/help/'))
                rows.append(CoverageRow(role, item.title, scenario.title, url, item.slug, scenario.slug,
                                        scenario.screenshot, test))
    return tuple(rows)
