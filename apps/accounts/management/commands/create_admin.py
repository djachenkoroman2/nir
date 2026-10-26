from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = 'Создаёт (или сбрасывает) суперпользователя без проверки сложности пароля.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')
        parser.add_argument('--password', default='123')
        parser.add_argument('--email', default='')

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(username=options['username'])
        user.email = options['email'] or user.email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(options['password'])
        user.save()
        action = 'создан' if created else 'обновлён'
        self.stdout.write(self.style.SUCCESS(f'Суперпользователь «{user.username}» {action}.'))
