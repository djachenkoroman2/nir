from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.help.content import GUIDES, validate_content
from apps.help.pdf import build_pdfs


class Command(BaseCommand):
    help = 'Собирает PDF-руководства из общего содержимого и реальных скриншотов справки.'

    def add_arguments(self, parser):
        parser.add_argument('--only', help='Роли через запятую: admin,editor,teacher,adjunct,student,reader')
        parser.add_argument('--work-dir', default='/tmp/opencode/nir-help-build')
        parser.add_argument('--soffice', help='Путь к LibreOffice/soffice (по умолчанию ищется в PATH)')

    def handle(self, *args, **options):
        errors = validate_content()
        if errors:
            raise CommandError('Ошибки содержимого:\n' + '\n'.join(errors))
        if options['only']:
            roles = [role.strip() for role in options['only'].split(',') if role.strip()]
            unknown = set(roles) - set(GUIDES)
            if unknown:
                raise CommandError(f'Неизвестные роли: {", ".join(sorted(unknown))}')
        else:
            roles = list(GUIDES)
        try:
            results = build_pdfs(roles, Path(options['work_dir']), options['soffice'])
        except (OSError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        for result in results:
            pages = f', {result.pages} стр.' if result.pages is not None else ''
            self.stdout.write(self.style.SUCCESS(
                f'{result.role}: {result.path} ({result.size} байт{pages}); '
                f'{result.scenarios} сценариев, {result.images} иллюстраций.'
            ))
        self.stdout.write(self.style.SUCCESS(f'Собрано руководств: {len(results)}.'))
