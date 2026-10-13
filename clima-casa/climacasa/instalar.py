"""Cria os atalhos do Clima Casa no Windows (Área de Trabalho e Menu Iniciar).

Executado pelo INSTALAR.bat:  python -m climacasa.instalar
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from .config import config_dir

APP_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- ícone

def _render_icon(size: int = 128, samples: int = 4) -> bytes:
    """Desenha o ícone (fundo azul com um ar-condicionado) e devolve RGBA."""
    blue, white, dark = (59, 130, 246), (255, 255, 255), (30, 41, 59)

    def rounded(px, py, x0, y0, x1, y1, r):
        cx = min(max(px, x0 + r), x1 - r)
        cy = min(max(py, y0 + r), y1 - r)
        return (px - cx) ** 2 + (py - cy) ** 2 <= r * r and x0 <= px <= x1 and y0 <= py <= y1

    def capsule(px, py, ax, ay, bx, by, r):
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2 <= r * r

    # coordenadas no espaço 0..64 (o mesmo do icone.svg)
    shapes = [
        (blue, lambda x, y: rounded(x, y, 0, 0, 64, 64, 14)),
        (white, lambda x, y: rounded(x, y, 10, 16, 54, 36, 5)),
        (dark, lambda x, y: rounded(x, y, 13, 31, 51, 33.5, 1.2)),
        (white, lambda x, y: capsule(x, y, 20, 40, 17, 50, 1.5)),
        (white, lambda x, y: capsule(x, y, 32, 40, 32, 52, 1.5)),
        (white, lambda x, y: capsule(x, y, 44, 40, 47, 50, 1.5)),
    ]
    scale = 64 / size
    out = bytearray()
    for py in range(size):
        out.append(0)  # filtro PNG "nenhum" no início de cada linha
        for px in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(samples):
                for sx in range(samples):
                    x = (px + (sx + 0.5) / samples) * scale
                    y = (py + (sy + 0.5) / samples) * scale
                    color = None
                    for c, inside in shapes:
                        if inside(x, y):
                            color = c
                    if color:
                        acc[0] += color[0]
                        acc[1] += color[1]
                        acc[2] += color[2]
                        acc[3] += 1
            n = samples * samples
            alpha = acc[3] / n
            if acc[3]:
                out += bytes(int(acc[i] / acc[3]) for i in range(3))
            else:
                out += b"\0\0\0"
            out.append(int(alpha * 255))
    return bytes(out)


def _png(size: int, rows: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def write_icon(path: Path, size: int = 128) -> Path:
    png = _png(size, _render_icon(size))
    # Arquivo .ico com uma imagem PNG dentro (aceito desde o Windows Vista).
    ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), 22) + png
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ico)
    return path


# ---------------------------------------------------------------- atalhos

_POWERSHELL = r"""
$ws = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  $s = $ws.CreateShortcut((Join-Path $folder 'Clima Casa.lnk'))
  $s.TargetPath = $env:CC_TARGET
  $s.Arguments = '-m climacasa'
  $s.WorkingDirectory = $env:CC_WORKDIR
  $s.IconLocation = $env:CC_ICON
  $s.Description = 'Controle dos ares-condicionados'
  $s.Save()
}
"""


def pythonw_path() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.is_file() else exe)


def create_shortcuts() -> None:
    icon = write_icon(config_dir() / "clima-casa.ico")
    env = {**os.environ, "CC_TARGET": pythonw_path(), "CC_WORKDIR": str(APP_DIR), "CC_ICON": str(icon)}
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _POWERSHELL],
        env=env, check=True,
    )


def main() -> int:
    if sys.platform != "win32":
        print("Os atalhos são criados apenas no Windows. Para abrir: python -m climacasa")
        return 0
    try:
        create_shortcuts()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Não foi possível criar os atalhos ({exc}). Use o arquivo ABRIR-CLIMA-CASA.bat.")
        return 1
    print("Atalho 'Clima Casa' criado na Área de Trabalho e no Menu Iniciar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
