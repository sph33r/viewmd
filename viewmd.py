#!/usr/bin/env python3
"""viewmd: local markdown viewer. Python standard library only.

Serves a markdown file or folder on 127.0.0.1 and opens it in the default
browser. Rendering happens in the browser using the libraries in ./vendor.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
VENDOR_DIR = APP_DIR / "vendor"
VENDOR_SUMS = VENDOR_DIR / "SHA256SUMS"

MARKDOWN_EXTS = {".md", ".markdown"}
SKIP_DIRS = {"node_modules", "__pycache__", "venv", "env"}
MAX_FILES = 5000
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}

# The Windows registry can map extensions to wrong types; pin the ones we serve.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}

# Only these file types are served from the document folder via /raw/.
RAW_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg"}

# The page may only load its own scripts and talk to its own server. This
# stops scripts embedded in a markdown file from running or sending data out.
APP_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
)
# Images opened directly (e.g. an SVG) get no script rights at all.
RAW_CSP = (
    "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
    "sandbox; frame-ancestors 'none'"
)


def content_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in CONTENT_TYPES:
        return CONTENT_TYPES[ext]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def resolve_in(base: Path, rel: str) -> Path | None:
    """Resolve rel under base; None if it escapes base (symlinks included)."""
    if "\0" in rel:
        return None
    try:
        target = (base / rel).resolve()
        target.relative_to(base)
    except (ValueError, OSError):
        return None
    return target


def list_markdown(root: Path) -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS
        )
        for name in sorted(filenames):
            if Path(name).suffix.lower() in MARKDOWN_EXTS:
                rel = Path(dirpath, name).relative_to(root)
                found.append(rel.as_posix())
                if len(found) >= MAX_FILES:
                    return found
    return found


def load_vendor_sums() -> dict[str, str]:
    """Parse vendor/SHA256SUMS into {filename: sha256 hex}."""
    sums: dict[str, str] = {}
    for line in VENDOR_SUMS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, name = line.partition(" ")
        sums[name.strip().lstrip("*")] = digest.lower()
    return sums


def verify_vendor(sums: dict[str, str]) -> list[str]:
    """Return a list of problems; empty means every vendored file matches."""
    problems = []
    for name, expected in sums.items():
        path = VENDOR_DIR / name
        if not path.is_file():
            problems.append(f"{name}: missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(f"{name}: checksum mismatch")
    return problems


class ViewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, root: Path, single: str | None, vendor: set[str]):
        super().__init__(addr, Handler)
        self.root = root
        self.single = single  # rel path when launched on one file
        self.vendor = vendor  # vendor files that passed verification
        self.token = secrets.token_urlsafe(16)


class Handler(BaseHTTPRequestHandler):
    server: ViewServer

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    # -- helpers -----------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str, csp: str = APP_CSP) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj).encode("utf-8"), CONTENT_TYPES[".json"])

    def _error(self, status: int, msg: str) -> None:
        self._json({"error": msg}, status)

    def _file(self, path: Path | None, csp: str = APP_CSP) -> None:
        if path is None or not path.is_file():
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        self._send(200, path.read_bytes(), content_type(path), csp)

    # -- routing -----------------------------------------------------------
    def do_GET(self) -> None:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            self._error(HTTPStatus.FORBIDDEN, "bad host")
            return

        url = urlparse(self.path)
        # Every route lives under /<token>/ so other local users and pages
        # that do not know the per-run token cannot reach any content.
        seg, sep, rest = url.path.lstrip("/").partition("/")
        if not hmac.compare_digest(seg.encode(), self.server.token.encode()):
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        if not sep:  # relative URLs in the page need the trailing slash
            self.send_response(HTTPStatus.PERMANENT_REDIRECT)
            self.send_header("Location", url.path + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        route = unquote(rest)
        query = parse_qs(url.query)

        if route == "":
            self._file(WEB_DIR / "index.html")
        elif route.startswith("static/"):
            self._file(resolve_in(WEB_DIR, route[len("static/"):]))
        elif route.startswith("vendor/"):
            name = route[len("vendor/"):]
            self._file(VENDOR_DIR / name if name in self.server.vendor else None)
        elif route.startswith("raw/"):
            target = resolve_in(self.server.root, route[len("raw/"):])
            if target is not None and target.suffix.lower() not in RAW_EXTS:
                target = None
            self._file(target, RAW_CSP)
        elif route == "api/tree":
            self._api_tree()
        elif route == "api/file":
            self._api_file(query.get("path", [""])[0])
        elif route == "api/mtime":
            self._api_mtime(query.get("path", [""])[0])
        else:
            self._error(HTTPStatus.NOT_FOUND, "not found")

    def _markdown_path(self, rel: str) -> Path | None:
        target = resolve_in(self.server.root, rel)
        if target and target.is_file() and target.suffix.lower() in MARKDOWN_EXTS:
            return target
        return None

    def _api_tree(self) -> None:
        srv = self.server
        files = [srv.single] if srv.single else list_markdown(srv.root)
        initial = srv.single
        if initial is None:
            readme = next((f for f in files if f.lower() == "readme.md"), None)
            initial = readme or (files[0] if files else None)
        self._json({"name": srv.root.name, "files": files, "initial": initial})

    def _api_file(self, rel: str) -> None:
        target = self._markdown_path(rel)
        if target is None:
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        text = target.read_text(encoding="utf-8", errors="replace")
        self._json({"text": text, "mtime": target.stat().st_mtime_ns})

    def _api_mtime(self, rel: str) -> None:
        target = self._markdown_path(rel)
        if target is None:
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        self._json({"mtime": target.stat().st_mtime_ns})


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="viewmd", description="View markdown files in the browser."
    )
    p.add_argument(
        "path", nargs="?", default=".", help="markdown file or folder (default: .)"
    )
    p.add_argument(
        "-p", "--port", type=int, default=0, help="port (default: any free port)"
    )
    p.add_argument(
        "--no-browser", action="store_true", help="do not open a browser window"
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    target = Path(args.path).expanduser().resolve()

    single = None
    if target.is_file():
        if target.suffix.lower() not in MARKDOWN_EXTS:
            print(f"viewmd: not a markdown file: {target}", file=sys.stderr)
            return 2
        root, single = target.parent, target.name
    elif target.is_dir():
        root = target
    else:
        print(f"viewmd: no such file or folder: {target}", file=sys.stderr)
        return 2

    if not WEB_DIR.is_dir() or not VENDOR_SUMS.is_file():
        print("viewmd: web/ or vendor/ missing next to viewmd.py", file=sys.stderr)
        return 1
    sums = load_vendor_sums()
    problems = verify_vendor(sums)
    if problems:
        print("viewmd: vendored files failed verification:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    try:
        server = ViewServer(("127.0.0.1", args.port), root, single, set(sums))
    except OSError as exc:
        print(f"viewmd: cannot bind port {args.port}: {exc}", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{server.server_address[1]}/{server.token}/"
    print(f"viewmd: serving {target}\nviewmd: {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
