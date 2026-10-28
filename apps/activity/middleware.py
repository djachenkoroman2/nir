from .log import current_request, write
from .models import ActivityLog

# Служебные адреса, просмотр которых не пишется: статика, медиа, админка (её изменения пишут сигналы).
SKIPPED_PREFIXES = ('/static/', '/media/', '/admin/')


class ActivityMiddleware:
    """Передаёт запрос сигналам изменения данных и пишет просмотры страниц и выгрузки отчётов."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current_request.set(request)
        try:
            response = self.get_response(request)
        finally:
            current_request.reset(token)
        action = self.action_for(request, response)
        if action:
            write(action, request, isolate=False)
        return response

    @staticmethod
    def action_for(request, response):
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated or request.method != 'GET' or response.status_code != 200:
            return None
        if request.path.startswith(SKIPPED_PREFIXES):
            return None
        if 'attachment' in response.get('Content-Disposition', ''):
            return ActivityLog.Action.EXPORT
        if response.get('Content-Type', '').startswith('text/html'):
            return ActivityLog.Action.VIEW
        return None
