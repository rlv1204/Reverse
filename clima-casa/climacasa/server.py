"""Servidor local que entrega a tela do programa e recebe os comandos.

Ele só aceita conexões do próprio computador (127.0.0.1).  Cada execução
gera uma senha aleatória que vai embutida na página; pedidos sem essa senha
são recusados, o que impede que outros sites abertos no navegador enviem
comandos aos aparelhos.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .devices import ControlError, Manager

WEB_DIR = Path(__file__).with_name("web")
APP_SIGNATURE = "clima-casa"


class ClimaServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, manager: Manager) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.manager = manager
        self.token = secrets.token_urlsafe(24)
        self.last_heartbeat = time.monotonic()
        self.first_heartbeat = False
        self.quit_event = threading.Event()

    @property
    def port(self) -> int:
        return self.server_address[1]


class Handler(BaseHTTPRequestHandler):
    server: ClimaServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silencioso: nada de poluir a tela
        pass

    # -------------------------------------------------------------- utilidades

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in (f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}")

    def _api_allowed(self) -> bool:
        return self._host_ok() and secrets.compare_digest(self.headers.get("X-Clima-Token", ""), self.server.token)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 64_000:
            raise ControlError("Pedido grande demais")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise ControlError("Pedido inválido") from None
        if not isinstance(data, dict):
            raise ControlError("Pedido inválido")
        return data

    # -------------------------------------------------------------- GET

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._send(HTTPStatus.FORBIDDEN, b"Forbidden", "text/plain")
        path = unquote(self.path.split("?", 1)[0])
        if path == "/ping":
            return self._json(200, {"app": APP_SIGNATURE})
        if path.startswith("/api/"):
            if not self._api_allowed():
                return self._json(403, {"error": "Acesso negado"})
            try:
                return self._api_get(path)
            except Exception:
                traceback.print_exc()
                return self._json(500, {"error": "Erro interno do programa. Detalhes no arquivo clima-casa.log."})
        if path in ("/", "/index.html"):
            html = (WEB_DIR / "index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", self.server.token)
            return self._send(200, html.encode(), "text/html; charset=utf-8", {
                "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                           "script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            })
        file = (WEB_DIR / path.lstrip("/")).resolve()
        if WEB_DIR.resolve() in file.parents and file.is_file():
            ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            return self._send(200, file.read_bytes(), ctype)
        return self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")

    def _api_get(self, path: str) -> None:
        manager = self.server.manager
        if path == "/api/devices":
            return self._json(200, {"devices": manager.devices(), **manager.status()})
        return self._json(404, {"error": "Não encontrado"})

    # -------------------------------------------------------------- POST

    def do_POST(self) -> None:
        if not self._api_allowed():
            return self._json(403, {"error": "Acesso negado"})
        path = unquote(self.path.split("?", 1)[0])
        manager = self.server.manager
        try:
            body = self._body()
            if path == "/api/heartbeat":
                self.server.last_heartbeat = time.monotonic()
                self.server.first_heartbeat = True
                return self._json(200, {"ok": True})
            if path == "/api/quit":
                self._json(200, {"ok": True})
                self.server.quit_event.set()
                return None
            if path.startswith("/api/devices/") and path.endswith("/control"):
                device_id = path[len("/api/devices/"):-len("/control")]
                return self._json(200, {"device": manager.control(device_id, body)})
            if path.startswith("/api/devices/") and path.endswith("/rename"):
                device_id = path[len("/api/devices/"):-len("/rename")]
                manager.rename(device_id, str(body.get("name", "")))
                return self._json(200, {"ok": True})
            if path == "/api/gree/discover":
                ip = str(body.get("ip") or "").strip() or None
                return self._json(200, manager.discover_gree(ip))
            if path == "/api/gree/remove":
                manager.remove_gree(str(body.get("mac", "")))
                return self._json(200, {"ok": True})
            if path == "/api/lg/token":
                return self._json(200, manager.set_lg_token(str(body.get("token", "")), str(body.get("country", "BR"))))
        except ControlError as exc:
            return self._json(400, {"error": str(exc)})
        except OSError as exc:
            return self._json(500, {"error": f"Erro de rede: {exc}"})
        except Exception:
            traceback.print_exc()
            return self._json(500, {"error": "Erro interno do programa. Detalhes no arquivo clima-casa.log."})
        return self._json(404, {"error": "Não encontrado"})
