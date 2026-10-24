"""Fast JSON serialization for native club API payloads."""

import gzip
import json
from collections.abc import Mapping

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask


def accepts_gzip(value: str) -> bool:
    """Honor explicit gzip quality before a wildcard coding preference."""
    qualities = {}
    for item in value.split(","):
        coding, *parameters = item.strip().lower().split(";")
        if coding not in {"gzip", "*"}:
            continue
        quality = 1.0
        for parameter in parameters:
            key, separator, raw = parameter.strip().partition("=")
            if key == "q" and separator:
                try:
                    quality = float(raw)
                except ValueError:
                    quality = 0.0
        if not 0 <= quality <= 1:
            quality = 0.0
        qualities[coding] = min(qualities.get(coding, 1.0), quality)
    return qualities.get("gzip", qualities.get("*", 0.0)) > 0


class ClubJSONResponse(JSONResponse):
    """Serialize JSON-native club payloads directly, encoding rare values lazily."""

    def __init__(
        self,
        content,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        background: BackgroundTask | None = None,
        *,
        gzip_enabled: bool = False,
    ) -> None:
        super().__init__(content, status_code, headers, media_type, background)
        # Explicit identity also prevents the outer middleware from treating
        # an expressly rejected gzip token (q=0) as acceptance by substring.
        self.headers["Content-Encoding"] = "identity"
        self.headers.add_vary_header("Accept-Encoding")
        if gzip_enabled:
            self.body = gzip.compress(self.body, compresslevel=1, mtime=0)
            response_headers = self.headers
            response_headers["Content-Encoding"] = "gzip"
            response_headers["Content-Length"] = str(len(self.body))

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=jsonable_encoder,
        ).encode(self.charset)
