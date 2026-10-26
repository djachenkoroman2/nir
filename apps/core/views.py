from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import render

from apps.research.models import ResearchProject
from apps.staff.models import Teacher


@login_required
def home(request):
    context = {
        'teacher_count': Teacher.objects.filter(is_active=True).count(),
        'project_count': ResearchProject.objects.count(),
        'active_project_count': ResearchProject.objects.filter(
            status=ResearchProject.Status.IN_PROGRESS
        ).count(),
    }
    return render(request, 'core/home.html', context)


class StaffPermissionRequiredMixin(PermissionRequiredMixin):
    """Изменять данные могут только сотрудники (is_staff) с соответствующим правом Django.

    Анонимного пользователя перенаправляет на вход, вошедшему без прав возвращает 403.
    """

    def has_permission(self):
        return self.request.user.is_staff and super().has_permission()
