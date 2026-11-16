from django.urls import include, path
from vault_core.health import live, ready

urlpatterns = [
    path("health/live", live),
    path("health/ready", ready),
    path("accounts/", include("allauth.urls")),
    path("", include("vault_core.urls")),
]
