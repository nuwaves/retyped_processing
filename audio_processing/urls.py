"""
URL configuration for audio_processing project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf.urls.static import static

from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from .api_urls import api_v1_patterns
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.contrib.sitemaps.views import sitemap
from audio_processing.sitemaps import get_episode_sitemaps, get_podcast_sitemaps
from audio_processing.sitemaps import sitemap_index_view
from django.conf import settings

def health_check(request):
    return JsonResponse({"status": "healthy"})


schema_view = get_schema_view(
    openapi.Info(
        title="Retyped API",
        default_version="v1",
        description="Retyped API to serve the frontend",
        terms_of_service="#",
        contact=openapi.Contact(email="contact@domain.local"),
    ),
    public=True,
)

urlpatterns = [
    # path('admin_tools_stats/', include('admin_tools_stats.urls')),
    path(
        "swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    # Admin and health endpoints
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health"),
    # Auth Endpoints called outside v1 because namespace
    re_path(r"^auth/", include("drf_social_oauth2.urls", namespace="drf")),
    # API v1 endpoints
    path("api/v1/", include((api_v1_patterns, "api_v1"), namespace="v1")),
    # Sitemap index and paginated sitemaps
    path("sitemap.xml", sitemap_index_view, name="sitemap-index"),
    re_path(r"^sitemap-(?P<section>episodes-\d+)\.xml$", sitemap, {"sitemaps": get_episode_sitemaps()}),
    re_path(r"^sitemap-(?P<section>podcasts-\d+)\.xml$", sitemap, {"sitemaps": get_podcast_sitemaps()}),
    ] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
