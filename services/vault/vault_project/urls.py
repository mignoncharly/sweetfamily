from django.urls import include, path
from vault_core import access_views
from vault_core.health import live, ready

urlpatterns = [
    path("health/live", live),
    path("health/ready", ready),
    path("accounts/enroll/<uuid:member_id>/", access_views.invitation),
    path("accounts/enrollment/", access_views.enrollment),
    path("accounts/personal-code/", access_views.code_login),
    path("accounts/personal-access/", access_views.personal_access),
    path("accounts/", include("allauth.urls")),
    path("", include("vault_core.urls")),
]
