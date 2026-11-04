from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.module_loading import import_string


class AuthenticationBackendsTest(TestCase):
    """Every configured auth backend must import.

    Django and social_django import these lazily, so a broken one only shows
    up as a 500 on pages that render templates (the admin) or on login, while
    /health/ keeps passing.
    """

    def test_all_backends_import(self):
        for path in settings.AUTHENTICATION_BACKENDS:
            with self.subTest(backend=path):
                import_string(path)

    def test_admin_login_page_renders(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)

    def test_admin_index_renders_for_superuser(self):
        user = get_user_model().objects.create_superuser(
            "admin", "admin@example.com", "pw-for-tests"
        )
        self.client.force_login(user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
