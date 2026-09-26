"""X-LLM-Lens-Key header check for write endpoints."""
import hmac
from functools import wraps

from django.conf import settings
from rest_framework.response import Response

HEADER = "X-LLM-Lens-Key"


def require_lens_key(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        supplied = request.headers.get(HEADER, "")
        if not hmac.compare_digest(supplied.encode(), settings.LENS_API_KEY.encode()):
            return Response({"error": f"missing or invalid {HEADER} header"}, status=401)
        return view(request, *args, **kwargs)

    return wrapper
