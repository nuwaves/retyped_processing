from unittest import mock

import requests
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from oauth2_provider.models import AccessToken, Application, RefreshToken
from rest_framework import status
from rest_framework.test import APIClient
from social_django.models import UserSocialAuth

GOOGLE_USER_DATA = {
    "sub": "google-uid-123",
    "id": "google-uid-123",
    "email": "listener@example.com",
    "given_name": "Ada",
    "family_name": "Listener",
    "name": "Ada Listener",
}

USER_DATA_PATH = "social_core.backends.google.GoogleOAuth2.user_data"


class ConvertTokenTest(TestCase):
    """/auth/convert-token/ swaps a provider token for one of our API tokens.

    The provider call (user_data) is mocked; everything else, including the
    social-auth pipeline and django-oauth-toolkit token storage, runs for real.
    """

    client_secret = "test-client-secret"

    def setUp(self):
        self.client = APIClient()
        self.application = Application.objects.create(
            name="frontend",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret=self.client_secret,
        )
        self.url = reverse("auth:convert_token")

    def payload(self, **overrides):
        data = {
            "grant_type": "convert_token",
            "client_id": self.application.client_id,
            "backend": "google-oauth2",
            "token": "provider-access-token",
        }
        data.update(overrides)
        return data

    def convert(self, **overrides):
        return self.client.post(self.url, self.payload(**overrides), format="json")

    @mock.patch(USER_DATA_PATH, return_value=GOOGLE_USER_DATA)
    def test_creates_user_and_returns_token(self, _user_data):
        response = self.convert()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        body = response.json()
        for key in ("access_token", "refresh_token", "expires_in", "token_type", "scope"):
            self.assertIn(key, body)
        self.assertEqual(body["token_type"], "Bearer")
        self.assertEqual(
            body["user"],
            {"email": "listener@example.com", "first_name": "Ada", "last_name": "Listener"},
        )

        user = User.objects.get(email="listener@example.com")
        self.assertTrue(
            UserSocialAuth.objects.filter(user=user, provider="google-oauth2").exists()
        )
        self.assertTrue(AccessToken.objects.filter(user=user, application=self.application).exists())
        self.assertTrue(RefreshToken.objects.filter(user=user, application=self.application).exists())

    @mock.patch(USER_DATA_PATH, return_value=GOOGLE_USER_DATA)
    def test_issued_token_authenticates_api_requests(self, _user_data):
        access_token = self.convert().json()["access_token"]

        bookmarks = reverse("v1:api-v1-bookmarks")
        self.assertEqual(self.client.get(bookmarks).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        self.assertEqual(self.client.get(bookmarks).status_code, status.HTTP_200_OK)

    @mock.patch(USER_DATA_PATH, return_value=GOOGLE_USER_DATA)
    def test_repeat_login_reuses_user(self, _user_data):
        first = self.convert().json()
        second = self.convert().json()

        self.assertEqual(User.objects.filter(email="listener@example.com").count(), 1)
        self.assertNotEqual(first["access_token"], second["access_token"])

    @mock.patch(USER_DATA_PATH, return_value=GOOGLE_USER_DATA)
    def test_refresh_token_works_on_token_endpoint(self, _user_data):
        refresh_token = self.convert().json()["refresh_token"]

        response = self.client.post(
            reverse("auth:token"),
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.application.client_id,
                "client_secret": self.client_secret,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertIn("access_token", response.json())

    def test_unknown_backend_is_rejected(self):
        response = self.convert(backend="not-a-backend")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("invalid_request", response.json())

    def test_unknown_client_id_is_rejected(self):
        response = self.convert(client_id="nope")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_grant_type_is_rejected(self):
        response = self.convert(grant_type="password")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_token_is_rejected(self):
        data = self.payload()
        del data["token"]
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_provider_rejecting_token_returns_400(self):
        provider_response = requests.Response()
        provider_response.status_code = 401
        error = requests.HTTPError(response=provider_response)
        with mock.patch(USER_DATA_PATH, side_effect=error):
            response = self.convert()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("access_denied", response.json())
        self.assertFalse(AccessToken.objects.exists())

    @mock.patch(USER_DATA_PATH, return_value=GOOGLE_USER_DATA)
    def test_inactive_user_gets_no_token(self, _user_data):
        self.convert()
        User.objects.filter(email="listener@example.com").update(is_active=False)
        AccessToken.objects.all().delete()

        response = self.convert()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AccessToken.objects.exists())
