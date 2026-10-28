import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.activity.models import ActivityLog


class Command(BaseCommand):
    help = 'Удаляет записи журнала активности старше срока хранения (ACTIVITY_LOG_DAYS).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=None,
                            help='Срок хранения в днях (по умолчанию — настройка ACTIVITY_LOG_DAYS).')

    def handle(self, *args, **options):
        days = options['days'] if options['days'] is not None else settings.ACTIVITY_LOG_DAYS
        border = timezone.now() - datetime.timedelta(days=days)
        deleted, _ = ActivityLog.objects.filter(created_at__lt=border).delete()
        self.stdout.write(f'Удалено записей журнала старше {days} дн.: {deleted}')
