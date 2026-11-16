from django.urls import path

from . import delivery_views, portal, views

urlpatterns = [
    path("help", portal.help_page),
    path("events/new", portal.create),
    path("transfers", portal.transfers),
    path("events/<uuid:event_id>", portal.dashboard),
    path("events/<uuid:event_id>/rules", portal.rules),
    path("events/<uuid:event_id>/people/new", portal.person),
    path("events/<uuid:event_id>/people/<uuid:member_id>", portal.person),
    path("events/<uuid:event_id>/exclusions", portal.exclusions),
    path("events/<uuid:event_id>/reminders", portal.reminders),
    path("events/<uuid:event_id>/export", portal.export),
    path("events/<uuid:event_id>/transfer", portal.propose_transfer),
    path("events/<uuid:source_id>/copy", portal.create),
    path("events/<uuid:event_id>/retry/<uuid:command_id>", portal.retry),
    path("events/<uuid:event_id>/action/<str:action>", portal.action),
    path("events/<uuid:event_id>/people/<uuid:member_id>/<str:action>", portal.action),
    path("api/events/<uuid:event_id>/reminders", views.reminder_settings),
    path("webhooks/resend", delivery_views.webhook),
    path("internal/status-projections", views.status_projection),
    path("", portal.home),
    path("api/events", views.events),
    path("api/events/<uuid:event_id>", views.event_detail),
    path("api/events/<uuid:event_id>/participants", views.add_member),
    path("api/events/<uuid:event_id>/open", views.open_event),
    path("api/events/<uuid:event_id>/status", views.event_status),
    path("api/events/<uuid:event_id>/participants/<uuid:member_id>/email", views.correct_member),
    path("api/events/<uuid:event_id>/<str:action>", views.lifecycle),
]
