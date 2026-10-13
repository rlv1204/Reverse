"""Ponto de partida do Clima Casa.

Uso:  python -m climacasa            (abre a janela do programa)
      python -m climacasa --sem-janela   (só o servidor, para abrir no navegador)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from .config import Config, config_dir
from .devices import Manager
from .server import APP_SIGNATURE, ClimaServer

DEFAULT_PORT = 8765
PORT_ATTEMPTS = 10
# Sem sinal da janela por este tempo, o programa entende que ela foi fechada.
# (O navegador reduz os temporizadores de janelas minimizadas a ~1 por minuto.)
HEARTBEAT_TIMEOUT = 150
STARTUP_GRACE = 300


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=1.5) as resp:
            return json.loads(resp.read()).get("app") == APP_SIGNATURE
    except (OSError, ValueError):
        return False


def _find_app_browser() -> str | None:
    """Edge (já vem no Windows) ou Chrome, que abrem a página como janela própria."""
    candidates = []
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
            candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for path in candidates:
        if path.is_file():
            return str(path)
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def open_window(url: str) -> None:
    browser = _find_app_browser()
    if browser:
        profile = config_dir() / "janela"
        try:
            subprocess.Popen(
                [browser, f"--app={url}", "--window-size=460,860", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except OSError:
            pass
    webbrowser.open(url)


def diagnose() -> int:
    """Verificação usada pelo instalador: rede local e aparelhos Gree visíveis."""
    from . import gree
    from .config import KNOWN_GREE_NAMES

    print(f"Python {sys.version.split()[0]} - OK")
    ips = gree.local_ipv4_addresses()
    print("Endereço(s) deste computador na rede:", ", ".join(ips) or "nenhum encontrado")
    print("Procurando aparelhos Gree na rede (alguns segundos)...")
    try:
        found = gree.discover(timeout=4.0)
    except OSError as exc:
        print(f"  Erro de rede: {exc}")
        return 1
    for dev in found:
        name = KNOWN_GREE_NAMES.get(dev.mac, dev.name)
        print(f"  Encontrado: {name}  (MAC {dev.mac}, IP {dev.ip}, criptografia v{dev.cipher})")
    missing = [n for mac, n in KNOWN_GREE_NAMES.items() if mac not in {d.mac for d in found}]
    if not found:
        print("  Nenhum aparelho Gree respondeu. Veja a seção 'Problemas comuns' do LEIA-ME.")
    elif missing:
        print("  Não responderam desta vez:", ", ".join(missing))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="climacasa", description="Controle dos ares-condicionados")
    parser.add_argument("--porta", type=int, default=DEFAULT_PORT)
    parser.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    parser.add_argument("--manter-aberto", action="store_true", help="não encerra quando a janela é fechada")
    parser.add_argument("--diagnostico", action="store_true", help="testa a rede e procura os aparelhos Gree")
    args = parser.parse_args(argv)
    if args.diagnostico:
        return diagnose()

    ports = range(args.porta, args.porta + PORT_ATTEMPTS)
    for port in ports:
        if _already_running(port):
            # Já está aberto: só mostramos a janela de novo.
            if not args.sem_janela:
                open_window(f"http://127.0.0.1:{port}/")
            return 0

    if sys.stderr is None:
        # Aberto pelo atalho (sem janela de console): erros vão para um arquivo.
        log = config_dir() / "clima-casa.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        sys.stderr = open(log, "a", encoding="utf-8", buffering=1)

    config = Config()
    manager = Manager(config)
    server = None
    for port in ports:
        try:
            server = ClimaServer(port, manager)
            break
        except OSError:
            continue  # porta ocupada por outro programa: tentamos a próxima
    if server is None:
        print(f"As portas {ports.start} a {ports.stop - 1} estão ocupadas. Tente: --porta 9000", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{server.port}/"

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Clima Casa rodando em {url}")
    print("Para encerrar, feche a janela do programa (ou pressione Ctrl+C aqui).")

    if not config.data["gree"]:
        # Primeira vez: procuramos os aparelhos Gree automaticamente.
        manager.start_discovery()

    if not args.sem_janela:
        open_window(url)

    started = last_tick = time.monotonic()
    try:
        while not server.quit_event.wait(5):
            now = time.monotonic()
            if now - last_tick > 30:
                # O computador estava suspenso: damos tempo para a janela "acordar".
                server.last_heartbeat = now
            last_tick = now
            if args.manter_aberto or args.sem_janela:
                continue
            if server.first_heartbeat and now - server.last_heartbeat > HEARTBEAT_TIMEOUT:
                break
            if not server.first_heartbeat and now - started > STARTUP_GRACE:
                break
    except KeyboardInterrupt:
        pass
    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
