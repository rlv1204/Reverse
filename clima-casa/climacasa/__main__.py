"""Ponto de partida do Clima Casa.

Uso:  python -m climacasa            (abre a janela do programa)
      python -m climacasa --sem-janela   (só o servidor, para abrir no navegador)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import __version__, instancia
from .atualizar import APP_DIR
from .config import Config, config_dir
from .devices import Manager
from .server import ClimaServer

DEFAULT_PORT = 8765
PORT_ATTEMPTS = 10
# Opções do Edge/Chrome que impedem o navegador de "congelar" a janela do
# programa quando ela fica parada ou minimizada por muito tempo.
KEEP_AWAKE_FLAGS = [
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
]


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
                [browser, f"--app={url}", "--window-size=480,980", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check", *KEEP_AWAKE_FLAGS],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except OSError:
            pass
    webbrowser.open(url)


def _windows_network_profiles() -> list[tuple[str, str]]:
    """Tipo de cada rede no Windows ("Public" ou "Private"), sem exigir administrador."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetConnectionProfile | ForEach-Object { $_.InterfaceAlias + '|' + $_.NetworkCategory }"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [tuple(line.split("|", 1)) for line in out.splitlines() if "|" in line]


def diagnose() -> int:
    """Verificação usada pelo instalador: rede local e aparelhos Gree visíveis."""
    from . import gree
    from .config import KNOWN_GREE_NAMES

    print(f"Python {sys.version.split()[0]} - OK")
    ips = gree.local_ipv4_addresses()
    print("Endereço(s) deste computador na rede:", ", ".join(ips) or "nenhum encontrado")
    for alias, category in _windows_network_profiles():
        kind = "Privada" if category.strip() in ("Private", "DomainAuthenticated") else "Pública"
        print(f"  Conexão '{alias}': rede {kind}")
        if kind == "Pública":
            print("    -> Recomendado mudar para Privada (veja 'Computador ligado por cabo' no LEIA-ME).")
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
    for dev in found:
        if not any(ip.rsplit(".", 1)[0] == dev.ip.rsplit(".", 1)[0] for ip in ips):
            print(f"  Aviso: o aparelho {dev.ip} está em outra faixa de rede que o computador"
                  " (provavelmente há dois roteadores). Funciona, mas confira o IP se ele mudar.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="climacasa", description="Controle dos ares-condicionados")
    parser.add_argument("--porta", type=int, default=DEFAULT_PORT)
    parser.add_argument("--sem-janela", action="store_true", help="não abre a janela automaticamente")
    parser.add_argument("--reiniciar", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--diagnostico", action="store_true", help="testa a rede e procura os aparelhos Gree")
    args = parser.parse_args(argv)
    if args.diagnostico:
        return diagnose()

    ports = range(args.porta, args.porta + PORT_ATTEMPTS)
    if args.reiniciar:
        # Reinício depois de uma atualização: esperamos a versão antiga sair.
        deadline = time.monotonic() + 20
        while instancia.ping(ports.start) and time.monotonic() < deadline:
            time.sleep(0.5)
    else:
        for port in ports:
            info = instancia.ping(port)
            if info and info.get("version") == __version__:
                # Já está aberto: só mostramos a janela de novo.
                if not args.sem_janela:
                    open_window(f"http://127.0.0.1:{port}/")
                return 0
        # Uma versão diferente ainda aberta (por exemplo, antes de atualizar).
        instancia.quit_running()

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
    instancia.write(server.port, server.token, server.instance)

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Clima Casa {__version__} rodando em {url}")
    print("Para encerrar, feche a janela do programa (ou pressione Ctrl+C aqui).")

    if not config.data["gree"]:
        # Primeira vez: procuramos os aparelhos Gree automaticamente.
        manager.start_discovery()

    if not args.sem_janela and not args.reiniciar:
        open_window(url)

    # O programa fica aberto até a janela ser fechada (ela avisa ao fechar),
    # até "Encerrar o programa" nas configurações ou até uma atualização.
    # Janelas paradas, minimizadas ou com o computador suspenso não encerram nada.
    try:
        while not server.quit_event.wait(1):
            pass
    except KeyboardInterrupt:
        pass
    server.shutdown()
    instancia.clear(server.instance)
    if server.restart_requested:
        restart(server.port)
    return 0


def restart(port: int) -> None:
    """Abre de novo o programa (já com os arquivos novos) depois de atualizar."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    command = [str(pythonw if pythonw.is_file() else exe), "-m", "climacasa", "--reiniciar", "--porta", str(port)]
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(command, cwd=str(APP_DIR), creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
