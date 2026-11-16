class PrivacyHeaders:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Cache-Control"] = "no-store"
        # Native authentication forms need a same-origin Origin/Referer in Chromium.
        # Gift/list/API pages keep no-referrer, and their forms use same-origin fetch.
        response["Referrer-Policy"] = (
            "same-origin"
            if request.path.startswith(("/accounts/", "/join/"))
            or request.path in {"/", "/join-pending"}
            else "no-referrer"
        )
        response["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; font-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response


class SerializeAuthentication:
    """Serialize upstream session challenge updates, including SessionMiddleware.save."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        from django.contrib.sessions.models import Session
        from django.db import transaction

        key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        if request.method == "POST" and request.path.startswith("/accounts/") and key:
            with transaction.atomic():
                Session.objects.select_for_update().filter(session_key=key).first()
                return self.get_response(request)
        return self.get_response(request)
