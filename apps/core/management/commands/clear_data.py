from django.db import transaction

from apps.accounts.models import User

from ._base import DOMAIN_MODELS, DevOnlyCommand, domain_counts


def clear_data(keep_username):
    """Удаляет предметные данные и пользователей, кроме keep_username. Возвращает [(название, число)]."""
    deleted = []
    with transaction.atomic():
        for model in DOMAIN_MODELS:
            count = model.objects.count()
            model.objects.all().delete()
            deleted.append((model._meta.verbose_name_plural, count))
        users = User.objects.exclude(username=keep_username)
        deleted.append((User._meta.verbose_name_plural, users.count()))
        users.delete()
    return deleted


class Command(DevOnlyCommand):
    help = 'Очищает базу: удаляет все предметные данные и пользователей, кроме admin. Группы и права сохраняются.'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--username', default='admin', help='Пользователь, которого нужно сохранить.')
        parser.add_argument('--noinput', '--no-input', action='store_true', help='Не спрашивать подтверждения.')

    def handle(self, *args, **options):
        self.check_environment(options)
        keep = options['username']
        if not User.objects.filter(username=keep).exists():
            self.stderr.write(self.style.WARNING(
                f'Пользователь «{keep}» не найден — ничего не удалено, чтобы не остаться без доступа к системе. '
                'Создайте его командой create_admin или укажите другого через --username.'
            ))
            return

        counts = domain_counts() + [
            (User._meta.verbose_name_plural, User.objects.exclude(username=keep).count())
        ]
        if not any(count for _, count in counts):
            self.stdout.write('База уже пуста — удалять нечего.')
            return

        self.print_counts(f'Будет удалено (пользователь «{keep}», группы и права сохранятся):', counts)
        if not options['noinput']:
            answer = input('Введите «yes», чтобы продолжить: ')
            if answer.strip().lower() != 'yes':
                self.stdout.write('Отменено.')
                return

        deleted = clear_data(keep)
        self.print_counts('Удалено:', deleted)
        self.stdout.write(self.style.SUCCESS('База очищена.'))
