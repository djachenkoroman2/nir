from django.contrib.auth.management import create_permissions
from django.db import migrations

ADJUNCTS_GROUP = 'Адъюнкты'
MODELS = ['adjunct', 'adjunctachievement', 'planstage', 'task', 'taskcomment']
ALL_ACTIONS = ['add', 'change', 'delete', 'view']


def codenames(app_label, models_actions):
    return [(app_label, f'{action}_{model}') for model, actions in models_actions.items() for action in actions]


# Что именно «своё» (свои публикации, подопечные адъюнкты, свои задачи), проверяет код:
# apps/core/permissions.py и apps/adjuncts/access.py.
GROUP_PERMISSIONS = {
    'Редакторы НИР': codenames('adjuncts', {model: ALL_ACTIONS for model in MODELS}),
    # Научный руководитель изменяет карточки, план, достижения и задачи своих адъюнктов.
    'Преподаватели': codenames('adjuncts', {
        'adjunct': ['change', 'view'],
        'adjunctachievement': ALL_ACTIONS,
        'planstage': ALL_ACTIONS,
        'task': ALL_ACTIONS,
        'taskcomment': ['add', 'delete', 'view'],
    }),
    # Адъюнкт ведёт свои труды, как преподаватель, свои достижения и работает со своими задачами.
    ADJUNCTS_GROUP: [
        *codenames('publications', {'publication': ALL_ACTIONS, 'publicationauthor': ALL_ACTIONS}),
        *codenames('ip', {'intellectualproperty': ALL_ACTIONS, 'intellectualpropertyauthor': ALL_ACTIONS}),
        *codenames('conferences', {
            'conference': ['add', 'view'], 'report': ALL_ACTIONS, 'reportspeaker': ALL_ACTIONS,
        }),
        *codenames('staff', {'teacher': ['view']}),
        *codenames('research', {'researchproject': ['view'], 'participant': ['view']}),
        *codenames('schools', {'scientificschool': ['view'], 'dissertationdefense': ['view']}),
        *codenames('students', {'student': ['view'], 'studentachievement': ['view']}),
        *codenames('adjuncts', {
            'adjunct': ['view'],
            'adjunctachievement': ALL_ACTIONS,
            'planstage': ['view'],
            'task': ['view'],
            'taskcomment': ['add', 'delete', 'view'],
        }),
    ],
}


def add_groups(apps, schema_editor):
    # Права создаются сигналом post_migrate, то есть после всех миграций; создаём их заранее.
    for app_label in {app_label for perms in GROUP_PERMISSIONS.values() for app_label, _ in perms}:
        app_config = apps.get_app_config(app_label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for group_name, perms in GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        for app_label, codename in perms:
            group.permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))


def remove_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    Group.objects.filter(name=ADJUNCTS_GROUP).delete()
    permissions = Permission.objects.filter(content_type__app_label='adjuncts')
    for group in Group.objects.filter(name__in=GROUP_PERMISSIONS):
        group.permissions.remove(*permissions)


class Migration(migrations.Migration):

    dependencies = [
        ('adjuncts', '0001_initial'),
        ('core', '0001_teachers_group'),
        ('research', '0002_editors_group'),
        ('schools', '0002_group_permissions'),
        ('students', '0002_group_permissions'),
    ]

    operations = [
        migrations.RunPython(add_groups, remove_groups),
    ]
