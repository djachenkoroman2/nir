from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = 'Редакторы НИР'
MODELS = {
    'staff': ['teacher'],
    'research': ['researchproject', 'participant'],
}


def create_editors_group(apps, schema_editor):
    # Права создаются сигналом post_migrate, то есть после всех миграций; создаём их заранее.
    for app_label in MODELS:
        app_config = apps.get_app_config(app_label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    for app_label, models in MODELS.items():
        group.permissions.add(
            *Permission.objects.filter(content_type__app_label=app_label, content_type__model__in=models)
        )


def remove_editors_group(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('research', '0001_initial'),
        ('staff', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_editors_group, remove_editors_group),
    ]
