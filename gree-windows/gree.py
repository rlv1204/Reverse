"""Controle local de ar-condicionado Gree (protocolo do app Gree+/EWPE Smart) para Windows.

Fala diretamente com o módulo Wi-Fi do aparelho pela rede local (UDP 7000),
sem passar pela nuvem da Gree. Funciona em Windows, Linux e macOS.

Uso rápido:
    python gree.py scan                    # procura aparelhos e faz o bind
    python gree.py status Sala
    python gree.py set Sala Pow=1 Mod=1 SetTem=23 WdSpd=0
    python gree.py gui                     # interface gráfica (Tkinter)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PORT = 7000
GENERIC_KEY_V1 = b"a3K8Bx%2r8Y7#xDh"  # AES-128-ECB, firmwares antigos
GENERIC_KEY_V2 = b"{yxAHAY_Lm6pbC/<"  # AES-128-GCM, firmwares novos
GCM_NONCE = bytes.fromhex("5440784449675a516c5e6313")
GCM_AAD = b"qualcomm-test"

# Parâmetros conhecidos (nomes usados pelo próprio firmware/app).
PROPS = {
    "Pow": "Liga (1) / desliga (0)",
    "Mod": "Modo: 0 Auto, 1 Frio, 2 Desumidificar, 3 Ventilar, 4 Calor",
    "SetTem": "Temperatura alvo (°C, 16-30)",
    "TemUn": "Unidade: 0 °C, 1 °F",
    "TemRec": "Meio grau em °F (bit auxiliar)",
    "TemSen": "Temperatura ambiente medida (só leitura; alguns firmwares somam 40)",
    "WdSpd": "Ventilador: 0 Auto, 1 Baixo, 2 Méd-baixo, 3 Médio, 4 Méd-alto, 5 Alto",
    "Tur": "Turbo",
    "Quiet": "Silencioso",
    "SwUpDn": "Aleta vertical: 0 padrão, 1 oscilar, 2-6 posições fixas",
    "SwingLfRig": "Aleta horizontal: 0 padrão, 1 oscilar, 2-6 posições fixas",
    "Lig": "Luz do display",
    "Blo": "X-Fan (secagem da serpentina)",
    "Health": "Ionizador / Health",
    "Air": "Ar fresco",
    "SwhSlp": "Modo sono",
    "SlpMod": "Tipo de modo sono",
    "SvSt": "Economia de energia",
    "StHt": "Aquecimento 8 °C (anticongelamento)",
    "HeatCoolType": "Tipo do aparelho (só leitura)",
}
STATUS_COLS = list(PROPS)


# --------------------------------------------------------------------------- criptografia

class CipherV1:
    """AES-128-ECB + PKCS7, base64. Chave genérica para scan/bind, depois chave do aparelho."""

    name = "v1"

    def __init__(self, key: bytes = GENERIC_KEY_V1):
        self.key = key

    def encrypt(self, obj: dict) -> tuple[str, str | None]:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        pad = 16 - len(raw) % 16
        enc = Cipher(algorithms.AES(self.key), modes.ECB()).encryptor()
        return base64.b64encode(enc.update(raw + bytes([pad]) * pad) + enc.finalize()).decode(), None

    def decrypt(self, pack: str, tag: str | None = None) -> dict:
        dec = Cipher(algorithms.AES(self.key), modes.ECB()).decryptor()
        return _json_prefix(dec.update(base64.b64decode(pack)) + dec.finalize())


class CipherV2:
    """AES-128-GCM com nonce e AAD fixos; o campo "tag" do pacote leva o tag GCM."""

    name = "v2"

    def __init__(self, key: bytes = GENERIC_KEY_V2):
        self.key = key

    def encrypt(self, obj: dict) -> tuple[str, str | None]:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        out = AESGCM(self.key).encrypt(GCM_NONCE, raw, GCM_AAD)
        return base64.b64encode(out[:-16]).decode(), base64.b64encode(out[-16:]).decode()

    def decrypt(self, pack: str, tag: str | None = None) -> dict:
        data = base64.b64decode(pack)
        if tag:
            return _json_prefix(AESGCM(self.key).decrypt(GCM_NONCE, data + base64.b64decode(tag), GCM_AAD))
        # Sem tag não há autenticação: GCM se reduz a CTR iniciando em J0+1.
        dec = Cipher(algorithms.AES(self.key), modes.CTR(GCM_NONCE + b"\x00\x00\x00\x02")).decryptor()
        return _json_prefix(dec.update(data) + dec.finalize())


CIPHERS = {"v1": CipherV1, "v2": CipherV2}


def _json_prefix(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="strict")
    return json.loads(text[: text.rindex("}") + 1])


# --------------------------------------------------------------------------- transporte

@dataclass
class Device:
    mac: str
    ip: str
    name: str = ""
    key: str = ""
    cipher: str = "v1"
    port: int = PORT
    model: str = ""
    version: str = ""

    def make_cipher(self):
        return CIPHERS[self.cipher](self.key.encode())


class GreeError(Exception):
    pass


def _send(ip: str, port: int, packet: dict, timeout: float) -> dict:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(json.dumps(packet).encode(), (ip, port))
        try:
            data, _ = s.recvfrom(65535)
        except socket.timeout as exc:
            raise GreeError(f"sem resposta de {ip}:{port}") from exc
    return json.loads(data)


def _request(dev: Device, inner: dict, cipher, i: int = 0, timeout: float = 3.0) -> dict:
    pack, tag = cipher.encrypt(inner)
    packet = {"cid": "app", "i": i, "t": "pack", "uid": 0, "tcid": dev.mac, "pack": pack}
    if tag:
        packet["tag"] = tag
    reply = _send(dev.ip, dev.port, packet, timeout)
    if "pack" not in reply:
        raise GreeError(f"resposta inesperada: {reply}")
    return cipher.decrypt(reply["pack"], reply.get("tag"))


def scan(broadcast: str = "255.255.255.255", timeout: float = 3.0) -> list[Device]:
    """Envia {"t":"scan"} em broadcast e coleta as respostas dos módulos Wi-Fi."""
    found: dict[str, Device] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.5)
        s.sendto(b'{"t":"scan"}', (broadcast, PORT))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, (ip, port) = s.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                reply = json.loads(data)
                info = None
                for c in (CipherV1(), CipherV2()):
                    try:
                        info = c.decrypt(reply["pack"], reply.get("tag"))
                        break
                    except Exception:
                        continue
                if not info:
                    continue
                mac = info.get("mac") or info.get("cid") or reply.get("cid")
                found[mac] = Device(
                    mac=mac, ip=ip, port=port, name=info.get("name", "") or mac,
                    model=info.get("model", ""), version=info.get("ver", ""),
                )
            except (ValueError, KeyError):
                continue
    return list(found.values())


def bind(dev: Device, timeout: float = 3.0) -> Device:
    """Obtém a chave exclusiva do aparelho. Tenta ECB (v1) e depois GCM (v2)."""
    for cls in (CipherV1, CipherV2):
        try:
            res = _request(dev, {"mac": dev.mac, "t": "bind", "uid": 0}, cls(), i=1, timeout=timeout)
        except Exception:
            continue
        if res.get("t") == "bindok" and res.get("key"):
            dev.key, dev.cipher = res["key"], cls.name
            return dev
    raise GreeError(f"bind falhou para {dev.name} ({dev.ip})")


def status(dev: Device, cols: list[str] | None = None) -> dict:
    res = _request(dev, {"cols": cols or STATUS_COLS, "mac": dev.mac, "t": "status"}, dev.make_cipher())
    return dict(zip(res.get("cols", []), res.get("dat", [])))


def set_props(dev: Device, **values: int) -> dict:
    res = _request(
        dev, {"opt": list(values), "p": list(values.values()), "t": "cmd"}, dev.make_cipher()
    )
    return dict(zip(res.get("opt", []), res.get("val") or res.get("p") or []))


# --------------------------------------------------------------------------- persistência

def store_path() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "gree-local" / "devices.json"


def load_devices() -> dict[str, Device]:
    p = store_path()
    if not p.exists():
        return {}
    return {d["mac"]: Device(**d) for d in json.loads(p.read_text(encoding="utf-8"))}


def save_devices(devs: dict[str, Device]) -> None:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([asdict(d) for d in devs.values()], indent=2, ensure_ascii=False), encoding="utf-8")


def find(devs: dict[str, Device], ref: str) -> Device:
    for d in devs.values():
        if ref.lower() in (d.mac.lower(), d.ip, d.name.lower()):
            return d
    raise GreeError(f"aparelho '{ref}' não encontrado; rode 'scan' primeiro")


# --------------------------------------------------------------------------- CLI

def cmd_scan(args) -> None:
    devs = load_devices()
    for d in scan(args.broadcast, args.timeout):
        old = devs.get(d.mac)
        if old and old.key:
            d.key, d.cipher = old.key, old.cipher
            d.name = old.name if old.name and old.name != old.mac else d.name
        else:
            try:
                bind(d)
            except GreeError as e:
                print(f"  ! {e}")
        devs[d.mac] = d
        print(f"{d.name:20} {d.ip:15} mac={d.mac} cifra={d.cipher} chave={'ok' if d.key else '—'}")
    if not devs:
        print("Nenhum aparelho encontrado. Verifique se o PC está na mesma rede/VLAN e libere UDP 7000 no firewall.")
    save_devices(devs)


def cmd_add(args) -> None:
    devs = load_devices()
    mac = args.mac.lower().replace(":", "").replace("-", "")
    d = Device(mac=mac, ip=args.ip, port=args.port, name=args.name or mac)
    bind(d)
    devs[d.mac] = d
    save_devices(devs)
    print(f"{d.name}: bind ok (cifra {d.cipher})")


def cmd_list(_args) -> None:
    for d in load_devices().values():
        print(f"{d.name:20} {d.ip:15} mac={d.mac} cifra={d.cipher}")


def cmd_status(args) -> None:
    d = find(load_devices(), args.device)
    for k, v in status(d).items():
        print(f"{k:13} = {v:<4} {PROPS.get(k, '')}")


def cmd_set(args) -> None:
    d = find(load_devices(), args.device)
    values = {}
    for kv in args.values:
        k, _, v = kv.partition("=")
        values[k] = int(v)
    print(set_props(d, **values))


def cmd_rename(args) -> None:
    devs = load_devices()
    d = find(devs, args.device)
    d.name = args.name
    save_devices(devs)


def cmd_gui(_args) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    devs = load_devices()
    root = tk.Tk()
    root.title("Gree local")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=12)
    frm.grid()

    names = {f"{d.name} ({d.ip})": d.mac for d in devs.values()}
    sel = tk.StringVar(value=next(iter(names), ""))
    power = tk.IntVar()
    mode = tk.StringVar(value="Frio")
    temp = tk.IntVar(value=24)
    fan = tk.StringVar(value="Auto")
    swing = tk.IntVar()
    room = tk.StringVar(value="—")
    modes_ = ["Auto", "Frio", "Desumidificar", "Ventilar", "Calor"]
    fans = ["Auto", "Baixo", "Méd-baixo", "Médio", "Méd-alto", "Alto"]

    def current() -> Device:
        return devs[names[sel.get()]]

    def refresh(*_):
        if not names:
            return
        try:
            st = status(current())
        except Exception as e:
            messagebox.showerror("Gree", str(e))
            return
        power.set(st.get("Pow", 0))
        mode.set(modes_[st.get("Mod", 1)] if st.get("Mod", 1) < 5 else "Frio")
        temp.set(st.get("SetTem", 24))
        fan.set(fans[st.get("WdSpd", 0)] if st.get("WdSpd", 0) < 6 else "Auto")
        swing.set(1 if st.get("SwUpDn") == 1 else 0)
        t = st.get("TemSen")
        room.set(f"{t - 40 if t and t > 60 else t} °C" if t else "—")

    def apply():
        try:
            set_props(current(), Pow=power.get(), Mod=modes_.index(mode.get()), SetTem=temp.get(),
                      WdSpd=fans.index(fan.get()), SwUpDn=swing.get())
        except Exception as e:
            messagebox.showerror("Gree", str(e))
        refresh()

    def rescan():
        nonlocal_devs = load_devices()
        for d in scan():
            if d.mac not in nonlocal_devs or not nonlocal_devs[d.mac].key:
                try:
                    bind(d)
                except GreeError:
                    continue
                nonlocal_devs[d.mac] = d
            else:
                nonlocal_devs[d.mac].ip = d.ip
        save_devices(nonlocal_devs)
        devs.clear()
        devs.update(nonlocal_devs)
        names.clear()
        names.update({f"{d.name} ({d.ip})": d.mac for d in devs.values()})
        box["values"] = list(names)
        if names and sel.get() not in names:
            sel.set(next(iter(names)))
        refresh()

    r = 0
    ttk.Label(frm, text="Aparelho").grid(row=r, column=0, sticky="w")
    box = ttk.Combobox(frm, textvariable=sel, values=list(names), state="readonly", width=28)
    box.grid(row=r, column=1, sticky="we")
    box.bind("<<ComboboxSelected>>", refresh)
    ttk.Button(frm, text="Procurar", command=rescan).grid(row=r, column=2, padx=(6, 0))
    r += 1
    ttk.Label(frm, text="Ambiente").grid(row=r, column=0, sticky="w")
    ttk.Label(frm, textvariable=room).grid(row=r, column=1, sticky="w")
    r += 1
    ttk.Checkbutton(frm, text="Ligado", variable=power).grid(row=r, column=1, sticky="w")
    r += 1
    ttk.Label(frm, text="Modo").grid(row=r, column=0, sticky="w")
    ttk.Combobox(frm, textvariable=mode, values=modes_, state="readonly").grid(row=r, column=1, sticky="we")
    r += 1
    ttk.Label(frm, text="Temperatura").grid(row=r, column=0, sticky="w")
    ttk.Spinbox(frm, from_=16, to=30, textvariable=temp, width=5).grid(row=r, column=1, sticky="w")
    r += 1
    ttk.Label(frm, text="Ventilador").grid(row=r, column=0, sticky="w")
    ttk.Combobox(frm, textvariable=fan, values=fans, state="readonly").grid(row=r, column=1, sticky="we")
    r += 1
    ttk.Checkbutton(frm, text="Oscilar aleta vertical", variable=swing).grid(row=r, column=1, sticky="w")
    r += 1
    ttk.Button(frm, text="Atualizar", command=refresh).grid(row=r, column=1, sticky="w", pady=(8, 0))
    ttk.Button(frm, text="Aplicar", command=apply).grid(row=r, column=2, pady=(8, 0))

    refresh()
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Controle local de ar-condicionado Gree (Gree+/EWPE).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="procura aparelhos na rede e faz o bind")
    p.add_argument("--broadcast", default="255.255.255.255", help="ex.: 192.168.0.255")
    p.add_argument("--timeout", type=float, default=3.0)
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("add", help="adiciona por IP/MAC quando o broadcast não funciona")
    p.add_argument("ip")
    p.add_argument("mac")
    p.add_argument("--name")
    p.add_argument("--port", type=int, default=PORT, help="porta UDP, se houver redirecionamento no roteador")
    p.set_defaults(fn=cmd_add)
    sub.add_parser("list", help="lista aparelhos salvos").set_defaults(fn=cmd_list)
    p = sub.add_parser("status", help="lê o estado do aparelho")
    p.add_argument("device", help="nome, IP ou MAC")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("set", help="altera parâmetros, ex.: Pow=1 SetTem=23")
    p.add_argument("device")
    p.add_argument("values", nargs="+")
    p.set_defaults(fn=cmd_set)
    p = sub.add_parser("rename", help="dá um nome amigável ao aparelho")
    p.add_argument("device")
    p.add_argument("name")
    p.set_defaults(fn=cmd_rename)
    sub.add_parser("gui", help="abre a interface gráfica").set_defaults(fn=cmd_gui)
    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except GreeError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
