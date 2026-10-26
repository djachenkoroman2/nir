from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = 'Преподаватели'

# Преподаватель ведёт свои публикации, РИД и доклады (что именно «свои» — проверяет код,
# см. apps/core/permissions.py), может добавить конференцию для своего доклада и всё просматривает.
PERMISSIONS = {
    'publications': {
        'publication': ['add', 'change', 'delete', 'view'],
        'publicationauthor': ['add', 'change', 'delete', 'view'],
    },
    'ip': {
        'intellectualproperty': ['add', 'change', 'delete', 'view'],
        'intellectualpropertyauthor': ['add', 'change', 'delete', 'view'],
    },
    'conferences': {
        'conference': ['add', 'view'],
        'report': ['add', 'change', 'delete', 'view'],
        'reportspeaker': ['add', 'change', 'delete', 'view'],
    },
    'staff': {'teacher': ['view']},
    'research': {'researchproject': ['view'], 'participant': ['view']},
}


def create_teachers_group(apps, schema_editor):
    # Права создаются сигналом post_migrate, то есть после всех миграций; создаём их заранее.
    for app_label in PERMISSIONS:
        app_config = apps.get_app_config(app_label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    for app_label, models in PERMISSIONS.items():
        for model, actions in models.items():
            group.permissions.add(*Permission.objects.filter(
                content_type__app_label=app_label,
                codename__in=[f'{action}_{model}' for action in actions],
            ))


def remove_teachers_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('staff', '0001_initial'),
        ('research', '0002_editors_group'),
        ('publications', '0002_editors_group_permissions'),
        ('ip', '0002_editors_group_permissions'),
        ('conferences', '0002_editors_group_permissions'),
    ]

    operations = [
        migrations.RunPython(create_teachers_group, remove_teachers_group),
    ]
