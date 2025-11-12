#!/usr/bin/env python3
"""
PeerStor - Minimal single-file file server (Phase 1 MVP)
- Zero-setup: stdlib only
- Runs with: python peerStor/peerstor.py [--port 8080] [--host 0.0.0.0] [--storage ./peerStor/data]
- Features: directory listing, file upload (multipart/form-data), download with Range support, auto port fallback, local IP hint

Note: This MVP intentionally avoids external dependencies. Later phases can swap in Flask/FastAPI while keeping the single-file goal.
"""

import argparse
import cgi
import contextlib
import html
import io
import mimetypes
import os
import posixpath
import shutil
import socket
import sys
import threading
import time
import re
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer  # py3.7+
except Exception:
    from socketserver import ThreadingMixIn
    from http.server import HTTPServer
    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

VERSION = "0.1.0"

# HTML template for directory listing with upload form
LISTING_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PeerStor - {title}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 20px; }}
  header {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
  code {{ background:#f5f5f5; padding:2px 6px; border-radius:4px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid #eee; text-align:left; }}
  th {{ background:#fafafa; }}
  a {{ text-decoration:none; color:#0366d6; }}
  a:hover {{ text-decoration:underline; }}
  .path {{ color:#666; }}
  form.upload {{ margin-top: 16px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
  .footer {{ margin-top:20px; color:#888; font-size: 12px; }}
  .btn {{ background:#0366d6; color:#fff; border:none; padding:8px 12px; border-radius:6px; cursor:pointer; }}
  .btn:hover {{ background:#024f9f; }}
  input[type="file"] {{ max-width: 50ch; }}
</style>
</head>
<body>
<header>
  <h2 style="margin:0">PeerStor</h2>
  <span class="path">{breadcrumb}</span>
</header>
<form class="upload" method="POST" action="/upload{qdir}" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button class="btn" type="submit">Upload</button>
</form>
<table>
  <thead>
    <tr><th>Name</th><th>Size</th><th>Modified</th></tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
<div class="footer">PeerStor {version} — Download supports resume (Range requests). Upload via browser. No auth (MVP).</div>
</body>
</html>"""


def human_size(n: int) -> str:
    if n is None:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    s = float(n)
    for u in units:
        if s < 1024.0:
            return f"{s:.1f} {u}" if u != "B" else f"{int(s)} {u}"
        s /= 1024.0
    return f"{s:.1f} PB"


def get_local_ip() -> str:
    ip = "127.0.0.1"
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as s:
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            pass
    return ip


def safe_join(base: str, *paths: str) -> str:
    base = os.path.abspath(base)
    final = os.path.abspath(os.path.join(base, *paths))
    if os.path.commonpath([base]) != os.path.commonpath([base, final]):
        raise ValueError("Attempted path traversal outside storage")
    return final


class PeerStorHandler(SimpleHTTPRequestHandler):
    server_version = f"PeerStor/{VERSION}"

    def __init__(self, *args, directory=None, **kwargs):
        self._root_directory = directory
        try:
            super().__init__(*args, directory=directory, **kwargs)
        except TypeError:
            # Older Python: fall back to attribute
            if directory is not None:
                self.directory = directory
            super().__init__(*args, **kwargs)

    def do_OPTIONS(self):
        # Basic CORS allowance for future API use (not necessary for MVP but harmless)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path.startswith('/upload'):
            return self.handle_upload()
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown POST endpoint")

    def handle_upload(self):
        # Determine target directory from query (?dir=/sub/path)
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        rel_dir = q.get('dir', [''])[0]
        try:
            target_dir = safe_join(self._root_directory, rel_dir.strip('/'))
        except Exception:
            return self.send_error(HTTPStatus.BAD_REQUEST, "Invalid directory")
        os.makedirs(target_dir, exist_ok=True)

        ctype = self.headers.get('Content-Type', '')
        if not ctype.startswith('multipart/form-data'):
            return self.send_error(HTTPStatus.BAD_REQUEST, "Expected multipart/form-data")

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers.get('Content-Type', ''),
                    'CONTENT_LENGTH': self.headers.get('Content-Length', '0'),
                }
            )
        except Exception as e:
            return self.send_error(HTTPStatus.BAD_REQUEST, f"Failed parsing form: {e}")

        file_item = form['file'] if 'file' in form else None
        if not file_item or not getattr(file_item, 'filename', None):
            return self.send_error(HTTPStatus.BAD_REQUEST, "No file uploaded")

        # Sanitize filename
        filename = os.path.basename(file_item.filename).strip().replace('\x00', '')
        if not filename:
            return self.send_error(HTTPStatus.BAD_REQUEST, "Invalid filename")

        out_path = safe_join(target_dir, filename)
        tmp_path = out_path + ".part"

        try:
            with open(tmp_path, 'wb') as f:
                shutil.copyfileobj(file_item.file, f, length=1024 * 1024)
            os.replace(tmp_path, out_path)
        except Exception as e:
            with contextlib.suppress(FileNotFoundError):
                os.remove(tmp_path)
            return self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Upload failed: {e}")

        # Redirect back to the current directory view
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header('Location', f"/{rel_dir.strip('/')}")
        self.end_headers()

    def list_directory(self, path):
        # Build a clean breadcrumb from storage root
        rel = os.path.relpath(path, start=self._root_directory).replace('\\', '/')
        if rel == '.':
            rel = ''
        from urllib.parse import quote

        try:
            entries = list(os.scandir(path))
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "No permission to list directory")
            return None

        rows = []
        # Parent link
        if rel:
            parent_rel = posixpath.dirname(rel)
            parent_href = '/' + parent_rel
            rows.append(f"<tr><td><a href='{html.escape(parent_href or '/')}'>&larr; Parent directory</a></td><td>-</td><td>-</td></tr>")

        for e in sorted(entries, key=lambda d: (not d.is_dir(), d.name.lower())):
            name = e.name
            display = html.escape(name)
            href = '/' + quote('/'.join(p for p in [rel, name] if p))
            try:
                stat = e.stat()
                size = None if e.is_dir() else stat.st_size
                mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime))
            except OSError:
                size, mtime = None, '-'
            rows.append(
                f"<tr><td><a href='{href}'>{display}{'/' if e.is_dir() else ''}</a></td>"
                f"<td>{human_size(size)}</td><td>{mtime}</td></tr>"
            )

        breadcrumb = '/' + rel if rel else '/'
        qdir = f"?dir=/{rel}" if rel else ""
        html_out = LISTING_HTML.format(
            title=html.escape(breadcrumb),
            breadcrumb=html.escape(breadcrumb),
            rows='\n'.join(rows),
            qdir=qdir,
            version=VERSION,
        )
        enc = 'utf-8'
        encoded = html_out.encode(enc, 'surrogateescape')
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"text/html; charset={enc}")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    # Light CORS for GET/HEAD
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    # Ensure paths are resolved strictly within storage root
    def translate_path(self, path):
        from urllib.parse import unquote
        # Strip query/fragment
        path = path.split('?', 1)[0].split('#', 1)[0]
        path = posixpath.normpath(unquote(path))
        parts = [p for p in path.split('/') if p and p not in ('.', '..')]
        try:
            return safe_join(self._root_directory, *parts)
        except Exception:
            return self._root_directory

    def do_HEAD(self):
        f, rng = self._send_head_with_range()
        if f:
            f.close()

    def do_GET(self):
        if self.path.startswith('/upload'):
            return self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
        f, rng = self._send_head_with_range()
        if not f:
            return
        try:
            if rng is None:
                shutil.copyfileobj(f, self.wfile)
            else:
                start, end = rng
                self._copyfile_range(f, start, end)
        finally:
            f.close()

    def _send_head_with_range(self):
        # Directory handling
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                self.send_header('Location', self.path + '/')
                self.end_headers()
                return None, None
            return self.list_directory(path), None

        ctype = self.guess_type(path)
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None, None

        try:
            fs = os.fstat(f.fileno())
            size = fs.st_size
            range_header = self.headers.get('Range')
            # Decide range
            rng = self._parse_range(range_header, size) if range_header else None

            if rng == (-1, -1):
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Type', ctype)
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', '0')
                self.end_headers()
                f.close()
                return None, None

            if rng is not None:
                start, end = rng
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                content_length = end - start + 1
            else:
                self.send_response(HTTPStatus.OK)
                content_length = size

            self.send_header('Content-Type', ctype)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(content_length))
            self.end_headers()
            return f, rng
        except Exception:
            f.close()
            raise

    def _parse_range(self, header: str, size: int):
        m = re.match(r'bytes=(\d*)-(\d*)$', header)
        if not m:
            return None
        start_s, end_s = m.groups()
        if start_s == '' and end_s == '':
            return None
        if start_s == '':
            # Suffix range: bytes=-N
            try:
                suffix = int(end_s)
            except ValueError:
                return (-1, -1)
            if suffix <= 0:
                return (-1, -1)
            start = max(0, size - suffix)
            end = size - 1
        else:
            try:
                start = int(start_s)
            except ValueError:
                return (-1, -1)
            if end_s:
                try:
                    end = int(end_s)
                except ValueError:
                    return (-1, -1)
            else:
                end = size - 1
        if start >= size or start < 0 or end < start:
            return (-1, -1)
        end = min(end, size - 1)
        return (start, end)

    def _copyfile_range(self, f, start: int, end: int):
        f.seek(start)
        remaining = end - start + 1
        bufsize = 64 * 1024
        while remaining > 0:
            chunk = f.read(min(bufsize, remaining))
            if not chunk:
                break
            self.wfile.write(chunk)
            remaining -= len(chunk)


def find_available_port(host: str, start_port: int, max_tries: int = 20) -> int:
    port = start_port
    for _ in range(max_tries):
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                port += 1
    return 0  # Let OS choose


def serve(host: str, port: int, storage: str):
    os.makedirs(storage, exist_ok=True)

    # Build handler that serves from storage
    def handler_factory(*args, **kwargs):
        return PeerStorHandler(*args, directory=storage, **kwargs)

    chosen_port = find_available_port(host, port) if port != 0 else 0
    server = ThreadingHTTPServer((host, chosen_port), handler_factory)
    actual_host, actual_port = server.server_address

    # Compute local IP for a friendly URL
    ip = get_local_ip() if host in ("0.0.0.0", "::") else host
    print(f"Access at: http://{ip}:{actual_port}")

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="PeerStor: single-file file server (MVP)")
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080; auto-increments if busy)")
    parser.add_argument("--storage", default=None, help="Storage directory (default: ./peerStor/data)")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args(argv)

    if args.version:
        print(VERSION)
        return 0

    script_dir = os.path.abspath(os.path.dirname(__file__))
    storage = args.storage or os.path.join(script_dir, "data")

    try:
        serve(args.host, args.port, storage)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
