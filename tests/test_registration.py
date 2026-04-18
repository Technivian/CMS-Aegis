from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from contracts.models import OrganizationMembership, UserProfile


User = get_user_model()


@override_settings(
    AUTHENTICATION_BACKENDS=[
        'django.contrib.auth.backends.ModelBackend',
        'django.contrib.auth.backends.AllowAllUsersModelBackend',
    ]
)
class RegistrationFlowTests(TestCase):
    def test_register_get_sets_csrf_cookie(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)

    def test_register_succeeds_with_multiple_auth_backends(self):
        response = self.client.post(
            reverse('register'),
            data={
                'username': 'newuser',
                'email': 'newuser@example.com',
                'password1': 'SafePass123!',
                'password2': 'SafePass123!',
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('login'))

        user = User.objects.get(username='newuser')
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertTrue(OrganizationMembership.objects.filter(user=user, is_active=True).exists())
        self.assertEqual(int(self.client.session.get('_auth_user_id')), user.id)
