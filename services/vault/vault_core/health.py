from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .runtime import assert_runtime


@require_GET
def live(request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request):
    try:
        assert_runtime()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
