from django.contrib.auth.management import create_permissions
from django.db import migrations

STUDENTS_GROUP = 'Курсанты'
ALL_ACTIONS = ['add', 'change', 'delete', 'view']


def codenames(app_label, models_actions):
    return [(app_label, f'{action}_{model}') for model, actions in models_actions.items() for action in actions]


# Курсант ведёт своё портфолио: публикации, доклады и достижения, где указан сам, и работает со своими задачами.
# Что именно «своё», проверяют код (apps/core/permissions.py, apps/adjuncts/access.py) и белый список страниц
# курсанта (apps/students/cabinet.py): чужие данные курсанту недоступны даже для просмотра.
PERMISSIONS = [
    *codenames('publications', {'publication': ALL_ACTIONS, 'publicationauthor': ALL_ACTIONS}),
    *codenames('conferences', {'conference': ['add', 'view'], 'report': ALL_ACTIONS, 'reportspeaker': ALL_ACTIONS}),
    *codenames('ip', {'intellectualproperty': ['view'], 'intellectualpropertyauthor': ['view']}),
    *codenames('students', {'student': ['view'], 'studentachievement': ALL_ACTIONS}),
    *codenames('adjuncts', {'task': ['view'], 'taskcomment': ['add', 'delete', 'view']}),
]


def add_group(apps, schema_editor):
    # Права создаются сигналом post_migrate, то есть после всех миграций; создаём их заранее.
    for app_label in {app_label for app_label, _ in PERMISSIONS}:
        app_config = apps.get_app_config(app_label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    group, _ = Group.objects.get_or_create(name=STUDENTS_GROUP)
    for app_label, codename in PERMISSIONS:
        group.permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))


def remove_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name=STUDENTS_GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0003_student_user'),
        ('adjuncts', '0002_groups'),
        ('conferences', '0004_speaker_adjunct'),
        ('ip', '0005_author_adjunct'),
        ('publications', '0005_author_adjunct'),
    ]

    operations = [
        migrations.RunPython(add_group, remove_group),
    ]
