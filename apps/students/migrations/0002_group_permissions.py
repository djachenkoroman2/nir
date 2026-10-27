from django.contrib.auth.management import create_permissions
from django.db import migrations

APP_LABEL = 'students'
# Редакторы ведут всех курсантов. Преподаватели видят всех, а изменяют карточки и ведут достижения
# только своих подопечных (это проверяется в apps.core.permissions); добавлять и удалять курсантов не могут.
GROUP_CODENAMES = {
    'Редакторы НИР': [
        f'{action}_{model}'
        for action in ('add', 'change', 'delete', 'view') for model in ('student', 'studentachievement')
    ],
    'Преподаватели': [
        'view_student', 'change_student',
        'add_studentachievement', 'change_studentachievement', 'delete_studentachievement',
        'view_studentachievement',
    ],
}


def add_permissions(apps, schema_editor):
    # Права создаются сигналом post_migrate, то есть после всех миграций; создаём их заранее.
    app_config = apps.get_app_config(APP_LABEL)
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for group_name, codenames in GROUP_CODENAMES.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(
            *Permission.objects.filter(content_type__app_label=APP_LABEL, codename__in=codenames)
        )


def remove_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    permissions = Permission.objects.filter(content_type__app_label=APP_LABEL)
    for group in Group.objects.filter(name__in=GROUP_CODENAMES):
        group.permissions.remove(*permissions)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0001_initial'),
        ('research', '0002_editors_group'),
        ('core', '0001_teachers_group'),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
