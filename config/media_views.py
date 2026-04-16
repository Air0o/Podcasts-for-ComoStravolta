import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils._os import safe_join


RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def media_serve(request, path: str) -> HttpResponse:
    if not settings.DEBUG:
        raise Http404

    normalized_path = safe_join(str(settings.MEDIA_ROOT), path)
    file_path = Path(normalized_path)
    if not file_path.exists() or not file_path.is_file():
        raise Http404("Requested media file was not found")

    stat_result = file_path.stat()

    content_type, _ = mimetypes.guess_type(str(file_path))
    content_type = content_type or "application/octet-stream"

    range_header = request.headers.get("Range", "")
    if not range_header:
        with file_path.open("rb") as source:
            response = HttpResponse(source.read(), content_type=content_type)
        response["Content-Length"] = str(stat_result.st_size)
        response["Accept-Ranges"] = "bytes"
        response["Content-Disposition"] = f'inline; filename="{file_path.name}"'
        return response

    match = RANGE_RE.fullmatch(range_header.strip())
    if not match:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{stat_result.st_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    start_text, end_text = match.groups()
    if start_text == "" and end_text == "":
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{stat_result.st_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    if start_text == "":
        suffix_length = int(end_text)
        if suffix_length <= 0:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{stat_result.st_size}"
            response["Accept-Ranges"] = "bytes"
            return response
        start = max(stat_result.st_size - suffix_length, 0)
        end = stat_result.st_size - 1
    else:
        start = int(start_text)
        end = int(end_text) if end_text else stat_result.st_size - 1

    if start >= stat_result.st_size or start > end:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{stat_result.st_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    end = min(end, stat_result.st_size - 1)
    length = (end - start) + 1

    with file_path.open("rb") as source:
        source.seek(start)
        data = source.read(length)

    response = HttpResponse(data, status=206, content_type=content_type)
    response["Content-Range"] = f"bytes {start}-{end}/{stat_result.st_size}"
    response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = f'inline; filename="{file_path.name}"'
    return response
