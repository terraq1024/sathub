from pathlib import Path
from django.conf import settings
from django.http import FileResponse, HttpResponse


def ranged_file_response(request, path: Path, content_type="application/octet-stream"):
    size = path.stat().st_size
    range_header = request.META.get("HTTP_RANGE")
    if not range_header:
        if request.method == "HEAD":
            response = HttpResponse(status=200, content_type=content_type)
        else:
            response = FileResponse(path.open("rb"), content_type=content_type)
        response["Content-Length"] = str(size)
        response["Accept-Ranges"] = "bytes"
        return response
    if not range_header.startswith("bytes=") or "," in range_header:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    raw = range_header[6:]
    try:
        start_text, end_text = raw.split("-", 1)
        if start_text:
            start, end = int(start_text), int(end_text) if end_text else size - 1
        else:
            length = int(end_text)
            start, end = max(0, size - length), size - 1
        if start < 0 or start >= size or end < start:
            raise ValueError
        end = min(end, size - 1)
        if end - start + 1 > int(getattr(settings, "ACCESS_MAX_RANGE_BYTES", 64 * 1024 * 1024)):
            raise ValueError
    except (TypeError, ValueError):
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    with path.open("rb") as source:
        source.seek(start)
        body = source.read(end - start + 1)
    response = HttpResponse(body if request.method != "HEAD" else b"", status=206, content_type=content_type)
    response["Content-Length"] = str(len(body))
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    return response
