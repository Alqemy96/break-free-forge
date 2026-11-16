"""Static file lookup for the built UI: traversal-proof path resolution, MIME types, cache policy.

Resolution never trusts the URL: the path is percent-decoded once, any `..`, backslash, drive colon,
control character or dot-file segment is REJECTED (the server answers 404), and the final real path
(symlinks resolved) must still be inside the static root."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

# Explicit table: the platform registry (Windows especially) is not trusted to know .js or .mjs.
MIME = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8", ".xml": "application/xml; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif", ".ico": "image/x-icon",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
    ".wasm": "application/wasm", ".mp4": "video/mp4", ".webm": "video/webm", ".mp3": "audio/mpeg",
    ".pdf": "application/pdf",
}
DEFAULT_TYPE = "application/octet-stream"

NO_CACHE = "no-cache"
IMMUTABLE = "public, max-age=31536000, immutable"
_HASHED = re.compile(r"[.-][0-9a-f]{8,}\.[A-Za-z0-9]+$")

# Resolution kinds
FILE, FALLBACK, REJECT = "file", "fallback", "reject"


def content_type(path: Path) -> str:
    return MIME.get(path.suffix.lower(), DEFAULT_TYPE)


def cache_control(rel: str) -> str:
    """Content-hashed bundles (Vite's `assets/` directory, or a `name.<hex>.ext` file name) are
    immutable for a year; everything else, index.html included, must be revalidated."""
    if rel.startswith("assets/") or _HASHED.search(rel.rsplit("/", 1)[-1]):
        return IMMUTABLE
    return NO_CACHE


class StaticFiles:
    def __init__(self, root: Path):
        root = Path(root)
        try:
            self.root = root.resolve()
        except (OSError, RuntimeError):
            self.root = root.absolute()
        self.index = self.root / "index.html"

    def resolve(self, url_path: str) -> Tuple[str, Optional[Path]]:
        """`url_path` is already percent-decoded. Returns
        (FILE, path) for an existing file inside the root,
        (FALLBACK, index.html path or None) for anything else that is a plausible UI route,
        (REJECT, None) for a path that tries to leave the root or is otherwise not servable."""
        segments = [s for s in url_path.split("/") if s not in ("", ".")]
        for seg in segments:
            if (seg == ".." or seg.startswith(".") or "\\" in seg or ":" in seg
                    or any(ord(c) < 32 or ord(c) == 127 for c in seg)):
                return REJECT, None
        if not segments:
            return self._fallback()
        try:
            real = self.root.joinpath(*segments).resolve()
            real.relative_to(self.root)
            is_file = real.is_file()
        except (OSError, RuntimeError, ValueError):
            return REJECT, None
        if is_file:
            return FILE, real
        return self._fallback()

    def _fallback(self) -> Tuple[str, Optional[Path]]:
        try:
            real = self.index.resolve()
            real.relative_to(self.root)
            return FALLBACK, (real if real.is_file() else None)
        except (OSError, RuntimeError, ValueError):
            return FALLBACK, None

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.name
