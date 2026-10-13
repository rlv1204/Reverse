"""Controle local de aparelhos Gree (o mesmo protocolo usado pelo app Gree+).

Como funciona (resumo da engenharia reversa do protocolo):

1. Descoberta: o computador envia ``{"t": "scan"}`` em UDP para a porta 7000.
   Cada aparelho responde com um pacote cujo campo ``pack`` está criptografado
   com uma chave genérica, conhecida por todos os aplicativos.
2. Pareamento ("bind"): pedimos ao aparelho sua chave própria.  A resposta
   ``bindok`` traz a chave que passa a criptografar todas as mensagens.
3. Estado: ``{"t": "status", "cols": [...]}`` devolve os valores pedidos.
4. Comando: ``{"t": "cmd", "opt": [...], "p": [...]}`` altera os valores.

Há duas gerações de criptografia:
  * v1: AES-128-ECB, chave genérica ``a3K8Bx%2r8Y7#xDh``;
  * v2: AES-128-GCM, chave genérica ``{yxAHAY_Lm6pbC/<``, nonce e AAD fixos.
O programa detecta automaticamente qual delas o aparelho usa.

Tudo acontece apenas na rede local: o computador precisa estar ligado (por
cabo ou Wi-Fi) ao mesmo roteador que os aparelhos.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import socket
import threading
import time
from dataclasses import dataclass, field

from . import aes

PORT = 7000
GENERIC_KEY = {1: b"a3K8Bx%2r8Y7#xDh", 2: b"{yxAHAY_Lm6pbC/<"}
GCM_NONCE = bytes.fromhex("5440784449675a516c5e6313")
GCM_AAD = b"qualcomm-test"

TEMP_OFFSET = 40

# Nomes das propriedades no protocolo Gree.
STATUS_COLS = [
    "Pow", "Mod", "SetTem", "TemUn", "TemRec", "TemSen", "WdSpd", "Tur", "Quiet",
    "SwUpDn", "SwingLfRig", "SwhSlp", "SlpMod", "Lig", "Health", "Blo", "SvSt",
    "Air", "StHt", "DwatSen",
]

MODES = {0: "auto", 1: "cool", 2: "dry", 3: "fan", 4: "heat"}
MODE_CODES = {v: k for k, v in MODES.items()}

FAN_OPTIONS = [
    ("0", "Automático"),
    ("1", "Baixo"),
    ("2", "Médio-baixo"),
    ("3", "Médio"),
    ("4", "Médio-alto"),
    ("5", "Alto"),
]

# (chave, rótulo, ícone, propriedades Gree enviadas ao ligar/desligar)
FEATURES = [
    ("turbo", "Turbo", "rocket", ("Tur",)),
    ("sleep", "Sono", "moon", ("SwhSlp", "SlpMod")),
    ("quiet", "Silencioso", "quiet", ("Quiet",)),
    ("light", "Luz do painel", "bulb", ("Lig",)),
    ("health", "Saúde", "leaf", ("Health",)),
    ("xfan", "X-Fan", "fan", ("Blo",)),
    ("eco", "Economia", "eco", ("SvSt",)),
]

# Valores de SwUpDn que representam oscilação (1 = completa, 7 a 11 = parcial).
_VERTICAL_SWING_VALUES = {1, 7, 8, 9, 10, 11}


class GreeError(Exception):
    """Falha de comunicação ou de protocolo com um aparelho Gree."""


class GreeTimeout(GreeError):
    """O aparelho não respondeu dentro do prazo."""


def _udp_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # No Windows, uma resposta ICMP "porta inalcançável" de um envio anterior
    # faria o próximo recvfrom falhar; desligamos esse comportamento.
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass
    return sock


def normalize_mac(mac: str) -> str:
    return "".join(ch for ch in str(mac).lower() if ch in "0123456789abcdef")


# ---------------------------------------------------------------- criptografia


def encrypt_pack(data: dict, key: bytes, cipher: int) -> tuple[str, str | None]:
    raw = json.dumps(data, separators=(",", ":")).encode()
    if cipher == 1:
        return base64.b64encode(aes.ecb_encrypt(key, raw)).decode(), None
    ct, tag = aes.gcm_encrypt(key, GCM_NONCE, raw, GCM_AAD)
    return base64.b64encode(ct).decode(), base64.b64encode(tag).decode()


def decrypt_pack(pack: str, key: bytes, cipher: int) -> dict:
    """Decifra o campo ``pack``.  Lança GreeError se a chave não servir."""
    try:
        data = base64.b64decode(pack)
        if cipher == 1:
            plain = aes.ecb_decrypt(key, data)
        else:
            # Os módulos Gree nem sempre enviam uma tag coerente; assim como o
            # app oficial, validamos o resultado pelo conteúdo JSON.
            plain = aes.gcm_decrypt(key, GCM_NONCE, data, GCM_AAD)
        text = plain.decode("utf-8", errors="strict")
        # O preenchimento vem depois da última chave "}" do JSON.
        text = text[: text.rindex("}") + 1]
        result = json.loads(text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise GreeError("Não foi possível decifrar a resposta do aparelho") from exc
    if not isinstance(result, dict):
        raise GreeError("Resposta do aparelho em formato inesperado")
    return result


def decrypt_with_generic_keys(pack: str) -> tuple[dict, int]:
    """Tenta as duas chaves genéricas; devolve (conteúdo, versão da cifra)."""
    for cipher in (1, 2):
        try:
            return decrypt_pack(pack, GENERIC_KEY[cipher], cipher), cipher
        except GreeError:
            continue
    raise GreeError("Resposta de descoberta com criptografia desconhecida")


# ---------------------------------------------------------------- descoberta


@dataclass
class Discovered:
    mac: str
    ip: str
    cipher: int
    name: str = ""
    firmware: str = ""
    model: str = ""
    brand: str = ""


def local_ipv4_addresses() -> list[str]:
    """Endereços IPv4 deste computador (sem precisar de bibliotecas extras)."""
    found: list[str] = []

    def add(ip: str) -> None:
        try:
            addr = ipaddress.IPv4Address(ip)
        except ValueError:
            return
        if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
            return
        if ip not in found:
            found.append(ip)

    # Endereço da interface usada para sair para a Internet/roteador.
    for probe in ("192.168.0.1", "10.0.0.1", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 80))  # UDP: não envia nada
                add(s.getsockname()[0])
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except OSError:
        pass
    return found


def scan_targets(extra: list[str] | None = None) -> list[str]:
    """Endereços para onde mandar o pedido de descoberta.

    Além do broadcast, enviamos um pedido individual para cada endereço da
    sub-rede /24 de cada interface: alguns roteadores e o próprio Windows nem
    sempre repassam broadcasts entre o cabo e o Wi-Fi.
    """
    targets = ["255.255.255.255"]
    for ip in local_ipv4_addresses():
        net = ipaddress.IPv4Network(f"{ip}/24", strict=False)
        targets.append(str(net.broadcast_address))
        targets += [str(host) for host in net.hosts() if str(host) != ip]
    for ip in extra or []:
        if ip and ip not in targets:
            targets.append(ip)
    return targets


def discover(timeout: float = 3.0, targets: list[str] | None = None, port: int = PORT) -> list[Discovered]:
    """Procura aparelhos Gree na rede local."""
    if targets is None:
        targets = scan_targets()
    devices: dict[str, Discovered] = {}
    with _udp_socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 0))
        request = json.dumps({"t": "scan"}).encode()
        for target in targets:
            try:
                sock.sendto(request, (target, port))
            except OSError:
                continue  # endereço inalcançável: ignorar
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            except OSError:
                continue
            found = _parse_scan_reply(data, addr[0])
            if found and found.mac not in devices:
                devices[found.mac] = found
    return list(devices.values())


def _parse_scan_reply(data: bytes, ip: str) -> Discovered | None:
    try:
        envelope = json.loads(data)
        pack, cipher = decrypt_with_generic_keys(envelope["pack"])
    except (ValueError, KeyError, TypeError, GreeError):
        return None
    mac = normalize_mac(pack.get("mac") or pack.get("cid") or envelope.get("cid") or "")
    if not mac:
        return None
    return Discovered(
        mac=mac,
        ip=ip,
        cipher=cipher,
        name=str(pack.get("name") or ""),
        firmware=str(pack.get("ver") or ""),
        model=str(pack.get("model") or ""),
        brand=str(pack.get("brand") or ""),
    )


# ---------------------------------------------------------------- aparelho


@dataclass
class GreeDevice:
    mac: str
    ip: str
    cipher: int = 1
    key: str = ""
    port: int = PORT
    timeout: float = 2.0
    retries: int = 1
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # -- transporte

    def _exchange(self, inner: dict, generic: bool, expect: str) -> dict:
        key = GENERIC_KEY[self.cipher] if generic else self.key.encode()
        pack, tag = encrypt_pack(inner, key, self.cipher)
        envelope = {"cid": "app", "i": 1 if generic else 0, "pack": pack, "t": "pack", "tcid": self.mac, "uid": 0}
        if tag:
            envelope["tag"] = tag
        payload = json.dumps(envelope).encode()
        last_error: Exception | None = None
        with self._lock:
            for _ in range(self.retries + 1):
                try:
                    return self._send_once(payload, key, expect)
                except (socket.timeout, TimeoutError) as exc:
                    last_error = exc
                except OSError as exc:
                    raise GreeError(f"Erro de rede ao falar com {self.ip}: {exc}") from exc
        raise GreeTimeout(f"O aparelho {self.ip} não respondeu") from last_error

    def _send_once(self, payload: bytes, key: bytes, expect: str) -> dict:
        with _udp_socket() as sock:
            sock.bind(("", 0))
            sock.sendto(payload, (self.ip, self.port))
            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout()
                sock.settimeout(remaining)
                try:
                    data, addr = sock.recvfrom(65535)
                except ConnectionResetError:
                    continue
                if addr[0] != self.ip:
                    continue
                try:
                    envelope = json.loads(data)
                    pack_text = envelope["pack"]
                except (ValueError, KeyError, TypeError):
                    continue
                reply = decrypt_pack(pack_text, key, self.cipher)
                if str(reply.get("t", "")).lower() == expect:
                    return reply

    # -- operações

    def bind(self) -> str:
        """Obtém a chave própria do aparelho, testando as duas cifras se preciso."""
        order = [self.cipher] + [c for c in (1, 2) if c != self.cipher]
        errors = []
        for cipher in order:
            self.cipher = cipher
            try:
                reply = self._exchange({"mac": self.mac, "t": "bind", "uid": 0}, generic=True, expect="bindok")
            except GreeError as exc:
                errors.append(str(exc))
                continue
            key = str(reply.get("key") or "")
            if len(key) != 16:
                raise GreeError("O aparelho devolveu uma chave inválida no pareamento")
            self.key = key
            return key
        raise GreeError(errors[-1] if errors else "Falha no pareamento")

    def _ensure_bound(self) -> None:
        if not self.key:
            self.bind()

    def ping(self) -> Discovered | None:
        """Pergunta "quem é você?" diretamente ao endereço do aparelho."""
        for found in discover(timeout=1.5, targets=[self.ip], port=self.port):
            if found.mac == self.mac:
                return found
        return None

    def _with_rebind(self, inner: dict, expect: str) -> dict:
        self._ensure_bound()
        try:
            return self._exchange(inner, generic=False, expect=expect)
        except GreeTimeout:
            # Silêncio pode significar aparelho desligado da rede ou chave
            # errada (o aparelho ignora mensagens que não consegue decifrar).
            found = self.ping()
            if found is None:
                raise
            self.cipher = found.cipher
        except GreeError:
            pass
        # A chave mudou (por exemplo, aparelho reconfigurado no app Gree+).
        self.bind()
        return self._exchange(inner, generic=False, expect=expect)

    def status(self, cols: list[str] | None = None) -> dict:
        cols = cols or STATUS_COLS
        reply = self._with_rebind({"cols": cols, "mac": self.mac, "t": "status"}, expect="dat")
        names = reply.get("cols") or cols
        values = reply.get("dat") or []
        return dict(zip(names, values))

    def command(self, values: dict) -> dict:
        opts = list(values.keys())
        reply = self._with_rebind({"opt": opts, "p": [values[k] for k in opts], "t": "cmd"}, expect="res")
        result_values = reply.get("val") or reply.get("p") or []
        return dict(zip(reply.get("opt") or opts, result_values))


# ---------------------------------------------------------------- tradução de estado


def current_temperature(raw: dict) -> float | None:
    value = raw.get("TemSen")
    if not isinstance(value, (int, float)) or value == 0:
        return None
    # A maioria dos módulos soma 40 ao valor do sensor; os mais novos não.
    return value - TEMP_OFFSET if value >= TEMP_OFFSET else value


def swing_from_raw(raw: dict) -> str:
    vertical = raw.get("SwUpDn") in _VERTICAL_SWING_VALUES
    horizontal = raw.get("SwingLfRig") == 1
    if vertical and horizontal:
        return "both"
    if vertical:
        return "vertical"
    if horizontal:
        return "horizontal"
    return "off"


def swing_to_raw(swing: str) -> dict:
    table = {"off": (0, 0), "vertical": (1, 0), "horizontal": (0, 1), "both": (1, 1)}
    if swing not in table:
        raise ValueError(f"Direção inválida: {swing}")
    up_down, left_right = table[swing]
    return {"SwUpDn": up_down, "SwingLfRig": left_right}


def feature_to_raw(key: str, on: bool) -> dict:
    for feature_key, _label, _icon, props in FEATURES:
        if feature_key == key:
            values = {prop: 1 if on else 0 for prop in props}
            # Turbo e Silencioso são mutuamente exclusivos no controle remoto.
            if on and key == "turbo":
                values["Quiet"] = 0
            if on and key == "quiet":
                values["Tur"] = 0
            return values
    raise ValueError(f"Função desconhecida: {key}")
