from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = 'Редакторы НИР'
APP_LABEL = 'ip'
MODELS = ['intellectualproperty', 'intellectualpropertyauthor']


def add_permissions(apps, schema_editor):
    # Права создаются сигналом post_migrate, то есть после всех миграций; создаём их заранее.
    app_config = apps.get_app_config(APP_LABEL)
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(
        *Permission.objects.filter(content_type__app_label=APP_LABEL, content_type__model__in=MODELS)
    )


def remove_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for group in Group.objects.filter(name=GROUP_NAME):
        group.permissions.remove(
            *Permission.objects.filter(content_type__app_label=APP_LABEL, content_type__model__in=MODELS)
        )


class Migration(migrations.Migration):

    dependencies = [
        ('ip', '0001_initial'),
        ('research', '0002_editors_group'),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
