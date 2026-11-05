from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.views.generic import TemplateView, View

from .content import GUIDES, chapter_neighbours, chapters_for, get_chapter
from .roles import accessible_guides, can_view_role, role_for_user

GENERATED_DIR = Path(settings.BASE_DIR) / 'apps' / 'help' / 'generated'


class IndexView(LoginRequiredMixin, TemplateView):
    template_name = 'help/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        own_role = role_for_user(self.request.user)
        context.update(
            own_role=own_role,
            own_guide=GUIDES[own_role],
            guides=accessible_guides(self.request.user),
            chapters=chapters_for(own_role),
        )
        return context


class RoleAccessMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        role = kwargs.get('role', '')
        if role not in GUIDES:
            raise Http404('Раздел справки не найден')
        if not can_view_role(request.user, role):
            raise PermissionDenied('Это руководство относится к другой роли')
        self.guide = GUIDES[role]
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            guide=self.guide,
            role=self.guide.slug,
            chapters=chapters_for(self.guide.slug),
            own_role=role_for_user(self.request.user),
            available_guides=accessible_guides(self.request.user),
        )
        return context


class GuideView(RoleAccessMixin, TemplateView):
    template_name = 'help/guide.html'


class ChapterView(RoleAccessMixin, TemplateView):
    template_name = 'help/chapter.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current = get_chapter(self.guide.slug, kwargs['chapter'])
        previous, following = chapter_neighbours(self.guide.slug, current)
        context.update(chapter=current, previous_chapter=previous, next_chapter=following)
        return context


class PdfView(RoleAccessMixin, View):
    def get(self, request, *args, **kwargs):
        path = GENERATED_DIR / f'{self.guide.slug}.pdf'
        if not path.is_file():
            raise Http404('PDF ещё не собран: выполните python manage.py build_help')
        response = FileResponse(path.open('rb'), content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="{self.guide.slug}-guide.pdf"; '
            f"filename*=UTF-8''{quote(self.guide.pdf_filename)}"
        )
        return response
