from django.contrib.auth.models import AnonymousUser

from .models import AuditEvent


def request_context(request):
    if request is None:
        return {}
    return {
        "request_id": request.headers.get("X-Request-ID", ""),
        "ip": request.META.get("REMOTE_ADDR"),
    }


def record_request_event(request, *, action, object_type, object_id="", payload=None):
    return record_event(
        actor=getattr(request, "user", None),
        action=action,
        object_type=object_type,
        object_id=object_id,
        payload=payload,
        **request_context(request),
    )


def record_event(
    *,
    actor=None,
    action,
    object_type,
    object_id="",
    request_id="",
    payload=None,
    ip=None,
):
    """Persist one audit event and return it."""
    if actor is None or isinstance(actor, AnonymousUser) or not getattr(actor, "is_authenticated", False):
        actor = None

    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else "",
        request_id=request_id or "",
        payload={} if payload is None else payload,
        ip=ip,
    )
