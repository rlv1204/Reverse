"""Configurações salvas no computador do usuário.

Windows: %APPDATA%\\ClimaCasa\\config.json
Outros:  ~/.config/climacasa/config.json
"""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
import uuid
from pathlib import Path

# Nomes dos aparelhos Gree informados pelo usuário (endereço MAC -> nome).
KNOWN_GREE_NAMES = {
    "9424b883c954": "Ângelo",
    "9424b883d28b": "Escritório",
}

DEFAULTS = {
    "lg": {"token": "", "country": "BR", "client_id": ""},
    "gree": {},  # mac -> {"ip", "cipher", "key", "name"}
    "names": {},  # id do aparelho -> nome escolhido pelo usuário
}


def config_dir() -> Path:
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "ClimaCasa"
    return Path.home() / ".config" / "climacasa"


class Config:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "config.json"
        self._lock = threading.RLock()
        self.data = copy.deepcopy(DEFAULTS)
        self._load()
        if not self.data["lg"].get("client_id"):
            self.data["lg"]["client_id"] = f"clima-casa-{uuid.uuid4()}"
            self.save()

    def _load(self) -> None:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            # Arquivo corrompido: guardamos uma cópia e começamos do zero.
            try:
                self.path.replace(self.path.with_suffix(".json.corrompido"))
            except OSError:
                pass
            return
        if isinstance(loaded, dict):
            for key, default in DEFAULTS.items():
                value = loaded.get(key, default)
                if isinstance(default, dict) and isinstance(value, dict):
                    self.data[key] = {**default, **value}
                elif type(value) is type(default):
                    self.data[key] = value

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def update(self, fn) -> None:
        with self._lock:
            fn(self.data)
            self.save()
