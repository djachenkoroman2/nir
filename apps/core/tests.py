from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class AuthFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ivanov', password='secret', first_name='Иван')

    def test_home_redirects_anonymous_to_login(self):
        response = self.client.get(reverse('core:home'))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_login_success_shows_greeting(self):
        response = self.client.post(reverse('login'), {'username': 'ivanov', 'password': 'secret'}, follow=True)
        self.assertContains(response, 'Здравствуйте, Иван!')

    def test_login_failure_shows_error(self):
        response = self.client.post(reverse('login'), {'username': 'ivanov', 'password': 'wrong'})
        self.assertContains(response, 'Неверный логин или пароль')

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
