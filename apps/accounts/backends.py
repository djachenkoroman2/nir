from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from apps.staff.models import PERSON_ACCOUNT_RELATIONS


class PersonModelBackend(ModelBackend):
    """Как ModelBackend, но пользователь загружается сразу с карточкой человека кафедры.

    Карточку (преподаватель, адъюнкт или курсант — get_person) нужно знать на каждой странице: для прав, меню
    и ограничений кабинета курсанта. Так она приходит в том же запросе, что и пользователь.
    """

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            user = UserModel._default_manager.select_related(*PERSON_ACCOUNT_RELATIONS).get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
