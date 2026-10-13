"""Controle da cópia do programa que está aberta.

Quando o programa está rodando, ele grava em %APPDATA%\\ClimaCasa\\instancia.json
a porta e a senha da sessão.  Assim o instalador e as atualizações conseguem
pedir para a cópia aberta se encerrar antes de trocar os arquivos.
"""

from __future__ import annotations

import json
import time
import urllib.request

from .config import config_dir

APP_SIGNATURE = "clima-casa"


def _path():
    return config_dir() / "instancia.json"


def write(port: int, token: str, instance: str) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"port": port, "token": token, "instance": instance}), encoding="utf-8")


def clear(instance: str) -> None:
    """Apaga o arquivo, se ele ainda for desta cópia."""
    path = _path()
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("instance") == instance:
            path.unlink()
    except (OSError, ValueError):
        pass


def ping(port: int, timeout: float = 1.5) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=timeout) as resp:
            info = json.loads(resp.read())
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) and info.get("app") == APP_SIGNATURE else None


def quit_running(wait: float = 10.0) -> bool:
    """Pede para a cópia aberta (se houver) se encerrar.  True se não sobrou nenhuma."""
    try:
        info = json.loads(_path().read_text(encoding="utf-8"))
        port, token = int(info["port"]), str(info["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return True
    if ping(port) is None:
        return True
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}", method="POST",
                                 headers={"X-Clima-Token": token, "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except OSError:
        pass
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if ping(port, timeout=0.5) is None:
            return True
        time.sleep(0.3)
    return False
