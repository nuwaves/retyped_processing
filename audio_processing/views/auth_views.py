"""Exchange a social provider access token for one of our own API tokens.

The frontend (NextAuth) runs the OAuth login with Google, Facebook, etc. and
posts the provider's access token here. python-social-auth verifies it with
the provider and finds or creates the user; django-oauth-toolkit then issues
our own access/refresh token pair.

This replaces drf-social-oauth2's ``/auth/convert-token/`` with the same
request and response shape, so the frontend needs no change.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from oauth2_provider.models import get_application_model
from oauth2_provider.scopes import get_scopes_backend
from oauth2_provider.settings import oauth2_settings
from oauthlib.common import Request as OAuthRequest
from oauthlib.oauth2.rfc6749.tokens import BearerToken
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from social_core.exceptions import AuthConfigurationError, SocialAuthBaseException
from social_django.utils import load_backend, load_strategy

logger = logging.getLogger(__name__)

GRANT_TYPE = "convert_token"


class ConvertTokenSerializer(serializers.Serializer):
    grant_type = serializers.ChoiceField(choices=[GRANT_TYPE])
    client_id = serializers.CharField()
    backend = serializers.CharField()
    token = serializers.CharField()


def _error(key, message):
    return Response({key: message}, status=HTTP_400_BAD_REQUEST)


def issue_token(request, user, application):
    """Issue an access/refresh token pair through django-oauth-toolkit.

    Goes through DOT's own validator so its token settings (expiry,
    generators, hashed storage, refresh-token families) all apply exactly as
    they do on its stock token endpoint.
    """
    scopes = get_scopes_backend().get_default_scopes(
        application=application, request=request
    )
    oauth_request = OAuthRequest(request.build_absolute_uri())
    oauth_request.user = user
    oauth_request.client = application
    oauth_request.client_id = application.client_id
    oauth_request.scopes = scopes
    oauth_request.grant_type = GRANT_TYPE

    server_kwargs = oauth2_settings.server_kwargs
    validator = oauth2_settings.OAUTH2_VALIDATOR_CLASS()
    bearer = BearerToken(
        validator,
        token_generator=server_kwargs["token_generator"],
        expires_in=server_kwargs["token_expires_in"],
        refresh_token_generator=server_kwargs["refresh_token_generator"],
    )
    token = bearer.create_token(oauth_request, refresh_token=True)
    validator.save_bearer_token(token, oauth_request)
    return dict(token)


class ConvertTokenView(APIView):
    """POST grant_type=convert_token, client_id, backend, token."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ConvertTokenSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        Application = get_application_model()
        application = Application.objects.filter(client_id=data["client_id"]).first()
        if application is None:
            return Response(
                {"detail": "The application for this client_id does not exist."},
                status=HTTP_400_BAD_REQUEST,
            )

        strategy = load_strategy(request._request)
        try:
            backend = load_backend(strategy, data["backend"], redirect_uri=None)
        except AuthConfigurationError as error:
            if error.code != "backend_missing":
                raise
            return _error("invalid_request", "Invalid backend parameter.")

        with transaction.atomic():
            try:
                user = backend.do_auth(access_token=data["token"])
            except SocialAuthBaseException as error:
                # Includes the provider rejecting the token (AuthProviderError).
                logger.info(
                    "Social auth failed for backend %s: %r", data["backend"], error
                )
                return _error(
                    "access_denied", "The token you provided is invalid or expired."
                )

            if not isinstance(user, get_user_model()):
                return _error("invalid_grant", "Invalid credentials given.")
            if not user.is_active:
                return _error("invalid_grant", "User inactive or deleted.")

            token = issue_token(request, user, application)

        token["user"] = {
            "email": getattr(user, "email", ""),
            "first_name": getattr(user, "first_name", ""),
            "last_name": getattr(user, "last_name", ""),
        }
        return Response(token)
