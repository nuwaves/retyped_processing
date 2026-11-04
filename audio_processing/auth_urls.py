"""Auth endpoints, mounted at /auth/.

convert-token is what the frontend calls after a NextAuth login. token and
revoke-token are django-oauth-toolkit's stock endpoints, for refreshing and
revoking the tokens convert-token issues.
"""

from django.urls import re_path
from oauth2_provider.views import RevokeTokenView, TokenView

from audio_processing.views.auth_views import ConvertTokenView

app_name = "auth"

urlpatterns = [
    re_path(r"^convert-token/?$", ConvertTokenView.as_view(), name="convert_token"),
    re_path(r"^token/?$", TokenView.as_view(), name="token"),
    re_path(r"^revoke-token/?$", RevokeTokenView.as_view(), name="revoke_token"),
]
