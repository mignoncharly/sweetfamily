from control_core.health import live, ready
from django.urls import include, path

urlpatterns = [
    path("health/live", live),
    path("health/ready", ready),
    path("accounts/", include("allauth.urls")),
    path("", include("control_core.urls")),
]
