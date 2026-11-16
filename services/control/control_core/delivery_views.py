from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from noel_delivery import record_webhook

from .models import AuthMail, DeliveryReceipt


@csrf_exempt
@require_http_methods(["POST"])
def webhook(request):
    try:
        record_webhook(request, AuthMail, DeliveryReceipt)
    except DatabaseError:
        return JsonResponse({"accepted": False}, status=503)
    except Exception:
        return JsonResponse({"accepted": False}, status=403)
    return JsonResponse({"accepted": True})
