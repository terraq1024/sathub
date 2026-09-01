import logging

from django.views.csrf import csrf_failure as django_csrf_failure

logger = logging.getLogger(__name__)


def csrf_failure(request, reason=""):
    logger.error("CSRF validation failed for %s %s: %s", request.method, request.path, reason)
    return django_csrf_failure(request, reason=reason)
