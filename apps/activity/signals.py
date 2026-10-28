"""Обработчики сигналов: вход и выход, изменения главных предметных записей."""
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .log import current_request, write
from .models import ActivityLog

# Главные предметные модели, изменения которых пишутся в журнал. Строки авторов, докладчиков и участников
# (PublicationAuthor и т. п.) не пишутся: иначе одно сохранение публикации давало бы десятки записей.
TRACKED_MODELS = [
    'staff.Teacher', 'research.ResearchProject', 'publications.Publication', 'ip.IntellectualProperty',
    'conferences.Conference', 'conferences.Report', 'schools.ScientificSchool', 'schools.DissertationDefense',
    'students.Student', 'students.StudentAchievement', 'adjuncts.Adjunct', 'adjuncts.PlanStage',
    'adjuncts.AdjunctAchievement', 'adjuncts.Task', 'adjuncts.TaskComment',
]


def is_tracked(sender):
    return sender._meta.label in TRACKED_MODELS


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    write(ActivityLog.Action.LOGIN, request, user=user)


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is not None:
        write(ActivityLog.Action.LOGOUT, request, user=user)


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs):
    # В credentials Django уже скрыл пароль; берём только введённый логин.
    username = str(credentials.get('username', ''))[:150]
    user = get_user_model().objects.filter(username=username).first() if username else None
    write(ActivityLog.Action.LOGIN_FAILED, request, user=user, username=username)


@receiver(post_save)
def log_save(sender, instance, created, raw=False, **kwargs):
    request = current_request.get()
    if raw or request is None or not is_tracked(sender) or not request.user.is_authenticated:
        return
    write(ActivityLog.Action.CREATE if created else ActivityLog.Action.UPDATE, request, obj=instance)


@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    request = current_request.get()
    if request is None or not is_tracked(sender) or not request.user.is_authenticated:
        return
    write(ActivityLog.Action.DELETE, request, obj=instance)
