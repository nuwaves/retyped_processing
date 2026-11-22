from django.urls import path

from . import views

paid_api_patterns = [
    path("", views.info, name="api-v1-paid-info"),
    path("search/", views.search, name="api-v1-paid-search"),
    path(
        "episodes/<slug:slug>/transcript/",
        views.transcript,
        name="api-v1-paid-transcript",
    ),
]
