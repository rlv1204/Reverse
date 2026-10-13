"""Atualização do programa.

Cada versão publicada traz o arquivo ``versao.json`` (o "manifesto"): número
da versão, notas e a lista de arquivos do programa com a impressão digital
SHA-256 de cada um.  Ele serve para duas coisas:

* **Atualizar pela própria janela** — o programa compara a sua versão com o
  manifesto publicado no GitHub, baixa os arquivos novos, confere cada
  impressão digital e só então substitui os arquivos antigos.
* **Instalar/atualizar pelo INSTALAR.bat** — os arquivos da pasta extraída do
  zip são copiados para a pasta de instalação, substituindo a versão anterior.

Em ambos os casos, arquivos que existiam na versão anterior e não existem na
nova são apagados, e as configurações do usuário (em %APPDATA%) não são
tocadas.

Para gerar o manifesto ao publicar uma versão:  python -m climacasa.atualizar
"""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__

APP_DIR = Path(__file__).resolve().parent.parent
MANIFEST = "versao.json"
# Canal de atualização: pasta clima-casa do repositório no GitHub.
UPDATE_BASE = "https://raw.githubusercontent.com/rlv1204/Reverse/claude/blissful-bardeen-iwwgn0/clima-casa/"

_SKIP_DIRS = {"__pycache__", ".pytest_cache"}
_SKIP_FILES = {MANIFEST, ".gitattributes"}


class UpdateError(Exception):
    pass


def version_tuple(text: str) -> tuple[int, ...]:
    parts = []
    for piece in str(text).split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def _normalized(data: bytes) -> bytes:
    # O Git pode trocar as quebras de linha (CRLF/LF) dos arquivos de texto;
    # a impressão digital ignora essa diferença.
    return data.replace(b"\r\n", b"\n")


def digest(data: bytes) -> str:
    return hashlib.sha256(_normalized(data)).hexdigest()


def _for_disk(rel: str, data: bytes) -> bytes:
    data = _normalized(data)
    return data.replace(b"\n", b"\r\n") if rel.endswith(".bat") else data


def _safe_relative(rel: str) -> str:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts or not rel or "\\" in rel:
        raise UpdateError(f"Caminho inválido no manifesto: {rel}")
    return path.as_posix()


# ---------------------------------------------------------------- manifesto


def program_files(root: Path = APP_DIR) -> list[str]:
    files = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and not (set(rel.parts) & _SKIP_DIRS) and rel.as_posix() not in _SKIP_FILES \
                and path.suffix not in (".pyc", ".log"):
            files.append(rel.as_posix())
    return files


def build_manifest(root: Path = APP_DIR, notes: str = "") -> dict:
    return {
        "versao": __version__,
        "notas": notes,
        "arquivos": {rel: digest((root / rel).read_bytes()) for rel in program_files(root)},
    }


def read_manifest(root: Path) -> dict | None:
    try:
        data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("arquivos"), dict) else None


# ---------------------------------------------------------------- substituição de arquivos


def replace_files(dest: Path, manifest: dict, read_new) -> list[str]:
    """Grava a nova versão em ``dest``.

    ``read_new(rel)`` devolve o conteúdo de cada arquivo novo.  Primeiro tudo é
    lido e conferido; só depois os arquivos são trocados, para nunca deixar
    uma instalação pela metade por causa de um download incompleto.
    """
    files = {_safe_relative(rel): sha for rel, sha in manifest["arquivos"].items()}
    staged: dict[str, bytes] = {}
    for rel, sha in files.items():
        data = read_new(rel)
        if digest(data) != sha:
            raise UpdateError(f"O arquivo {rel} chegou diferente do esperado. Tente de novo mais tarde.")
        staged[rel] = data

    old = read_manifest(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for rel, data in staged.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".novo")
        tmp.write_bytes(_for_disk(rel, data))
        tmp.replace(target)
    removed = []
    for rel in (old or {}).get("arquivos", {}):
        try:
            rel = _safe_relative(rel)
        except UpdateError:
            continue
        if rel not in staged and (dest / rel).is_file():
            (dest / rel).unlink()
            removed.append(rel)
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (dest / MANIFEST).write_text(manifest_text, encoding="utf-8")
    shutil.rmtree(dest / "climacasa" / "__pycache__", ignore_errors=True)
    return removed


def install_from_folder(source: Path, dest: Path) -> None:
    """Copia a versão da pasta extraída do zip para a pasta de instalação."""
    manifest = read_manifest(source)
    if manifest is None:
        raise UpdateError(f"Arquivo {MANIFEST} não encontrado em {source}")
    replace_files(dest, manifest, lambda rel: (source / rel).read_bytes())


# ---------------------------------------------------------------- atualização pela internet


class Updater:
    def __init__(self, base_url: str = UPDATE_BASE, app_dir: Path = APP_DIR, timeout: float = 20) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.app_dir = app_dir
        self.timeout = timeout
        self._ssl = ssl.create_default_context()

    def _get(self, rel: str) -> bytes:
        req = urllib.request.Request(self.base_url + rel, headers={"Cache-Control": "no-cache"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateError(f"Não foi possível baixar a atualização ({getattr(exc, 'reason', exc)}).") from None

    def latest(self) -> dict:
        try:
            manifest = json.loads(self._get(MANIFEST))
        except ValueError:
            raise UpdateError("O arquivo de versão publicado está com problema.") from None
        if not isinstance(manifest, dict) or not isinstance(manifest.get("arquivos"), dict):
            raise UpdateError("O arquivo de versão publicado está com problema.")
        return manifest

    def check(self) -> dict:
        manifest = self.latest()
        latest = str(manifest.get("versao", "0"))
        return {
            "current": __version__,
            "latest": latest,
            "notes": str(manifest.get("notas", "")),
            "available": version_tuple(latest) > version_tuple(__version__),
        }

    def apply(self) -> str:
        manifest = self.latest()
        if version_tuple(manifest.get("versao", "0")) <= version_tuple(__version__):
            raise UpdateError("Você já está com a versão mais recente.")
        replace_files(self.app_dir, manifest, self._get)
        return str(manifest["versao"])


def main() -> int:
    notes = " ".join(sys.argv[1:])
    old = read_manifest(APP_DIR) or {}
    if not notes and old.get("versao") == __version__:
        notes = old.get("notas", "")
    manifest = build_manifest(APP_DIR, notes)
    (APP_DIR / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{MANIFEST} gerado: versão {__version__}, {len(manifest['arquivos'])} arquivos")
    return 0


if __name__ == "__main__":
    sys.exit(main())

