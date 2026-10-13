"""Reúne os aparelhos Gree e LG em um único formato para a interface.

Cada aparelho é apresentado à tela como um dicionário com os mesmos campos,
independentemente da marca:

    id, brand, name, source, online, error, power, mode, modes, target,
    tempMin, tempMax, tempStep, current, humidity, fan, fans, swing, swings,
    features
"""

from __future__ import annotations

import copy
import ipaddress
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import gree, lg
from .config import KNOWN_GREE_NAMES, Config

MODE_INFO = {
    "cool": ("Frio", "snow"),
    "dry": ("Seco", "drop"),
    "fan": ("Ventilar", "fan"),
    "auto": ("Auto", "auto"),
    "heat": ("Calor", "sun"),
}
SWING_LABELS = {"off": "Parada", "vertical": "Vertical", "horizontal": "Horizontal", "both": "Ambas"}

GREE_TTL = 4.0
GREE_TTL_OFFLINE = 20.0
GREE_REDISCOVER_INTERVAL = 60.0
LG_TTL = 30.0
LG_TTL_ERROR = 60.0
LG_LIST_TTL = 600.0


class ControlError(Exception):
    """Pedido que não pôde ser atendido; a mensagem vai direto para a tela."""


def _mode_options(keys: list[str]) -> list[dict]:
    options = []
    for key in keys:
        label, icon = MODE_INFO.get(key, (key, "auto"))
        options.append({"value": key, "label": label, "icon": icon})
    return options


def _swing_options(vertical: bool, horizontal: bool) -> list[dict]:
    keys = ["off"]
    if vertical:
        keys.append("vertical")
    if horizontal:
        keys.append("horizontal")
    if vertical and horizontal:
        keys.append("both")
    return [{"value": k, "label": SWING_LABELS[k]} for k in keys] if len(keys) > 1 else []


@dataclass
class _Entry:
    raw: dict = field(default_factory=dict)
    updated: float = 0.0
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class _GreeEntry(_Entry):
    device: gree.GreeDevice | None = None
    firmware: str = ""
    name: str = ""


@dataclass
class _LGEntry(_Entry):
    info: dict = field(default_factory=dict)
    caps: lg.Capabilities | None = None
    last_fan: str = ""


class Manager:
    def __init__(self, config: Config, lg_base_url: str | None = None, gree_port: int = gree.PORT,
                 gree_scan_targets: list[str] | None = None) -> None:
        self.config = config
        self._lg_base_url = lg_base_url
        self._gree_port = gree_port
        self._gree_scan_targets = gree_scan_targets
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=8)
        self._gree: dict[str, _GreeEntry] = {}
        self._lg: dict[str, _LGEntry] = {}
        self._lg_client: lg.ThinQClient | None = None
        self._lg_listed = 0.0
        self._lg_error: str | None = None
        self._last_discovery = 0.0
        self._discovery_lock = threading.Lock()
        for mac, saved in self.config.data["gree"].items():
            self._add_gree_entry(mac, saved)
        self._configure_lg()

    # ------------------------------------------------------------ Gree

    def _add_gree_entry(self, mac: str, saved: dict) -> None:
        device = gree.GreeDevice(
            mac=mac,
            ip=saved.get("ip", ""),
            cipher=int(saved.get("cipher", 1)),
            key=saved.get("key", ""),
            port=self._gree_port,
        )
        self._gree[mac] = _GreeEntry(device=device, firmware=saved.get("firmware", ""), name=saved.get("name", ""))

    def _save_gree(self, mac: str) -> None:
        entry = self._gree[mac]
        dev = entry.device

        def apply(data):
            data["gree"][mac] = {"ip": dev.ip, "cipher": dev.cipher, "key": dev.key, "firmware": entry.firmware,
                                 "name": entry.name}

        self.config.update(apply)

    def discover_gree(self, extra_ip: str | None = None) -> dict:
        """Procura aparelhos Gree e pareia os novos.  Devolve um resumo."""
        if extra_ip:
            try:
                ipaddress.IPv4Address(extra_ip)
            except ValueError:
                raise ControlError("Endereço IP inválido. Exemplo de formato correto: 192.168.0.25") from None
        with self._discovery_lock:
            targets = self._gree_scan_targets
            if targets is None:
                targets = gree.scan_targets([extra_ip] if extra_ip else None)
            elif extra_ip:
                targets = targets + [extra_ip]
            found = gree.discover(timeout=3.0, targets=targets, port=self._gree_port)
            self._last_discovery = time.monotonic()
        new, updated, failed = [], [], []
        for item in found:
            with self._lock:
                entry = self._gree.get(item.mac)
                if entry is None:
                    self._add_gree_entry(item.mac, {"ip": item.ip, "cipher": item.cipher, "firmware": item.firmware,
                                                    "name": item.name})
                    entry = self._gree[item.mac]
                    is_new = True
                else:
                    is_new = False
                    if entry.device.ip != item.ip or entry.device.cipher != item.cipher:
                        entry.device.ip = item.ip
                        entry.device.cipher = item.cipher
                    entry.firmware = item.firmware or entry.firmware
                    entry.name = item.name or entry.name
            try:
                if not entry.device.key:
                    entry.device.bind()
            except gree.GreeError as exc:
                failed.append({"mac": item.mac, "ip": item.ip, "error": str(exc)})
            self._save_gree(item.mac)
            entry.updated = 0.0  # força leitura do estado
            (new if is_new else updated).append({"id": f"gree:{item.mac}", "ip": item.ip, "name": self._name(f"gree:{item.mac}")})
        return {"found": len(found), "new": new, "updated": updated, "failed": failed}

    def remove_gree(self, mac: str) -> None:
        with self._lock:
            self._gree.pop(mac, None)

        def apply(data):
            data["gree"].pop(mac, None)
            data["names"].pop(f"gree:{mac}", None)

        self.config.update(apply)

    def _refresh_gree(self, mac: str) -> None:
        entry = self._gree.get(mac)
        if entry is None:
            return
        with entry.lock:
            ttl = GREE_TTL if entry.error is None else GREE_TTL_OFFLINE
            if time.monotonic() - entry.updated < ttl:
                return
            dev = entry.device
            key_before, cipher_before, ip_before = dev.key, dev.cipher, dev.ip
            try:
                entry.raw = dev.status()
                entry.error = None
            except gree.GreeTimeout:
                entry.error = "Aparelho sem resposta na rede local. Ele está ligado na tomada? O computador está na mesma rede da casa?"
                self._maybe_rediscover()
            except gree.GreeError as exc:
                entry.error = str(exc)
            entry.updated = time.monotonic()
            if (dev.key, dev.cipher, dev.ip) != (key_before, cipher_before, ip_before):
                self._save_gree(mac)

    def _maybe_rediscover(self) -> None:
        """O roteador pode ter trocado o IP do aparelho: procuramos de novo."""
        if time.monotonic() - self._last_discovery < GREE_REDISCOVER_INTERVAL:
            return
        if self._discovery_lock.locked():
            return
        self._last_discovery = time.monotonic()
        self.start_discovery()

    def start_discovery(self) -> None:
        """Procura aparelhos Gree em segundo plano."""
        def run():
            try:
                self.discover_gree()
            except OSError:
                pass
        self._pool.submit(run)

    def _gree_view(self, mac: str, entry: _GreeEntry) -> dict:
        raw = entry.raw
        view = self._base_view(f"gree:{mac}", "gree", "Rede local (Gree)", entry)
        view.update({
            "modes": _mode_options(["cool", "dry", "fan", "auto", "heat"]),
            "tempMin": 16, "tempMax": 30, "tempStep": 1,
            "fans": [{"value": v, "label": label} for v, label in gree.FAN_OPTIONS],
            "swings": _swing_options(True, True),
            "address": entry.device.ip,
            "firmware": entry.firmware,
        })
        if raw:
            view.update({
                "power": bool(raw.get("Pow")),
                "mode": gree.MODES.get(raw.get("Mod")),
                "target": raw.get("SetTem"),
                "current": gree.current_temperature(raw),
                "humidity": raw.get("DwatSen") or None,
                "fan": str(raw.get("WdSpd")) if raw.get("WdSpd") is not None else None,
                "swing": gree.swing_from_raw(raw),
                "features": [
                    {"key": key, "label": label, "icon": icon, "on": bool(raw.get(props[0]))}
                    for key, label, icon, props in gree.FEATURES
                ],
            })
        return view

    def _control_gree(self, mac: str, body: dict) -> None:
        entry = self._gree.get(mac)
        if entry is None:
            raise ControlError("Aparelho não encontrado")
        values = gree_command(body)
        with entry.lock:
            try:
                confirmed = entry.device.command(values)
            except gree.GreeTimeout:
                raise ControlError("O aparelho não respondeu. Verifique se ele está ligado na tomada e conectado à rede da casa.") from None
            except gree.GreeError as exc:
                raise ControlError(str(exc)) from None
            entry.raw.update(values)
            entry.raw.update({k: v for k, v in confirmed.items() if k in values})
            entry.error = None
            entry.updated = time.monotonic()
        self._save_gree(mac)

    # ------------------------------------------------------------ LG

    def _configure_lg(self) -> None:
        settings = self.config.data["lg"]
        with self._lock:
            self._lg.clear()
            self._lg_listed = 0.0
            self._lg_error = None
            self._lg_client = None
            if settings.get("token"):
                self._lg_client = lg.ThinQClient(settings["token"], settings.get("country", "BR"),
                                                 settings["client_id"], base_url=self._lg_base_url)

    def set_lg_token(self, token: str, country: str) -> dict:
        token = (token or "").strip()
        country = (country or "BR").strip().upper()
        if not token:
            def clear(data):
                data["lg"]["token"] = ""
            self.config.update(clear)
            self._configure_lg()
            return {"devices": 0}
        client = lg.ThinQClient(token, country, self.config.data["lg"]["client_id"], base_url=self._lg_base_url)
        try:
            found = [d for d in client.devices() if (d.get("deviceInfo") or {}).get("deviceType") == lg.AIR_CONDITIONER]
        except lg.LGError as exc:
            raise ControlError(str(exc)) from None

        def apply(data):
            data["lg"]["token"] = token
            data["lg"]["country"] = country

        self.config.update(apply)
        self._configure_lg()
        return {"devices": len(found)}

    def _refresh_lg_list(self) -> None:
        client = self._lg_client
        if client is None or time.monotonic() - self._lg_listed < (LG_LIST_TTL if not self._lg_error else LG_TTL_ERROR):
            return
        self._lg_listed = time.monotonic()
        try:
            devices = client.devices()
            self._lg_error = None
        except lg.LGError as exc:
            self._lg_error = str(exc)
            return
        seen = set()
        for item in devices:
            info = item.get("deviceInfo") or {}
            device_id = item.get("deviceId")
            if info.get("deviceType") != lg.AIR_CONDITIONER or not device_id:
                continue
            seen.add(device_id)
            with self._lock:
                entry = self._lg.setdefault(device_id, _LGEntry())
                entry.info = info
        with self._lock:
            for device_id in list(self._lg):
                if device_id not in seen:
                    self._lg.pop(device_id)

    def _refresh_lg(self, device_id: str) -> None:
        entry = self._lg.get(device_id)
        client = self._lg_client
        if entry is None or client is None:
            return
        with entry.lock:
            ttl = LG_TTL if entry.error is None else LG_TTL_ERROR
            if time.monotonic() - entry.updated < ttl:
                return
            try:
                if entry.caps is None:
                    entry.caps = lg.Capabilities(client.profile(device_id))
                entry.raw = client.state(device_id)
                entry.error = None
            except lg.LGError as exc:
                entry.error = str(exc)
            entry.updated = time.monotonic()

    def _lg_view(self, device_id: str, entry: _LGEntry) -> dict:
        view = self._base_view(f"lg:{device_id}", "lg", "LG ThinQ", entry)
        caps = entry.caps
        view["model"] = entry.info.get("modelName", "")
        if caps is None:
            return view
        modes = [lg.MODE_FROM_LG.get(m, f"lg:{m}") for m in caps.modes]
        mode_options = _mode_options([m for m in modes if not m.startswith("lg:")])
        mode_options += [{"value": m, "label": lg.EXTRA_MODE_LABELS.get(m[3:], m[3:].title()), "icon": "auto"}
                         for m in modes if m.startswith("lg:")]
        features = []
        if "POWER" in caps.fans:
            features.append({"key": "turbo", "label": "Jet (turbo)", "icon": "rocket", "on": False})
        if caps.power_save:
            features.append({"key": "eco", "label": "Economia", "icon": "eco", "on": False})
        if lg.light_value(caps.light_values, True) is not None and lg.light_value(caps.light_values, False) is not None:
            features.append({"key": "light", "label": "Luz do painel", "icon": "bulb", "on": False})
        view.update({
            "modes": mode_options,
            "tempMin": caps.temp_min, "tempMax": caps.temp_max, "tempStep": caps.temp_step,
            "fans": [{"value": f, "label": lg.FAN_LABELS.get(f, f.title())} for f in caps.fans if f != "POWER"],
            "swings": _swing_options(caps.swing_vertical, caps.swing_horizontal),
            "features": features,
        })
        raw = entry.raw
        if not raw:
            return view
        temps = lg._temperatures(raw)
        job = (raw.get("airConJobMode") or {}).get("currentJobMode")
        fan = (raw.get("airFlow") or {}).get(caps.fan_key)
        direction = raw.get("windDirection") or {}
        mode = lg.MODE_FROM_LG.get(job, f"lg:{job}" if job else None)
        target_key = caps.temp_key_for_mode(mode or "")
        humidity = (raw.get("airQualitySensor") or {}).get("humidity")
        if humidity is None:
            humidity = (raw.get("humidity") or {}).get("currentHumidity")
        for feature in features:
            if feature["key"] == "turbo":
                feature["on"] = fan == "POWER"
            elif feature["key"] == "eco":
                feature["on"] = bool((raw.get("powerSave") or {}).get("powerSaveEnabled"))
            elif feature["key"] == "light":
                feature["on"] = lg.light_is_on((raw.get("display") or {}).get("light"))
        vertical = bool(direction.get("rotateUpDown"))
        horizontal = bool(direction.get("rotateLeftRight"))
        view.update({
            "power": (raw.get("operation") or {}).get("airConOperationMode") == "POWER_ON",
            "mode": mode,
            "target": temps.get(target_key, temps.get("targetTemperature")),
            "current": temps.get("currentTemperature"),
            "humidity": humidity,
            "fan": fan if fan != "POWER" else entry.last_fan or None,
            "swing": "both" if vertical and horizontal else "vertical" if vertical else "horizontal" if horizontal else "off",
        })
        if fan and fan != "POWER":
            entry.last_fan = fan
        return view

    def _control_lg(self, device_id: str, body: dict) -> None:
        entry = self._lg.get(device_id)
        client = self._lg_client
        if entry is None or client is None or entry.caps is None:
            raise ControlError("Aparelho LG ainda não carregado. Aguarde alguns segundos.")
        payload = lg_command(entry.caps, body, entry)
        with entry.lock:
            try:
                client.control(device_id, payload)
            except lg.LGError as exc:
                raise ControlError(str(exc)) from None
            entry.raw = apply_lg_payload(entry.raw, payload)
            # A LG demora alguns segundos para refletir a mudança: relemos depois.
            entry.updated = time.monotonic() - LG_TTL + 5

    # ------------------------------------------------------------ comum

    def _name(self, device_id: str) -> str:
        names = self.config.data["names"]
        if names.get(device_id):
            return names[device_id]
        brand, _, ident = device_id.partition(":")
        if brand == "gree":
            entry = self._gree.get(ident)
            return KNOWN_GREE_NAMES.get(ident) or (entry.name if entry else "") or f"Gree {ident[-4:].upper()}"
        entry = self._lg.get(ident)
        return (entry.info.get("alias") if entry else "") or "LG"

    def _base_view(self, device_id: str, brand: str, source: str, entry: _Entry) -> dict:
        return {
            "id": device_id, "brand": brand, "name": self._name(device_id), "source": source,
            "online": entry.error is None and bool(entry.raw), "error": entry.error, "loaded": entry.updated > 0,
            "power": None, "mode": None, "modes": [], "target": None, "tempMin": 16, "tempMax": 30, "tempStep": 1,
            "current": None, "humidity": None, "fan": None, "fans": [], "swing": None, "swings": [], "features": [],
        }

    def rename(self, device_id: str, name: str) -> None:
        name = (name or "").strip()[:40]

        def apply(data):
            if name:
                data["names"][device_id] = name
            else:
                data["names"].pop(device_id, None)

        self.config.update(apply)

    def refresh(self) -> None:
        """Atualiza em paralelo o estado dos aparelhos cujo cache venceu."""
        self._refresh_lg_list()
        jobs = [self._pool.submit(self._refresh_gree, mac) for mac in list(self._gree)]
        jobs += [self._pool.submit(self._refresh_lg, dev) for dev in list(self._lg)]
        for job in jobs:
            job.result()

    def devices(self) -> list[dict]:
        self.refresh()
        views = [self._gree_view(mac, e) for mac, e in list(self._gree.items())]
        views += [self._lg_view(dev, e) for dev, e in list(self._lg.items())]
        return sorted(views, key=lambda v: (v["brand"] != "lg", v["name"].lower()))

    def device(self, device_id: str) -> dict | None:
        return next((d for d in self.devices() if d["id"] == device_id), None)

    def control(self, device_id: str, body: dict) -> dict | None:
        brand, _, ident = device_id.partition(":")
        if brand == "gree":
            self._control_gree(ident, body)
        elif brand == "lg":
            self._control_lg(ident, body)
        else:
            raise ControlError("Aparelho desconhecido")
        return self.device(device_id)

    def status(self) -> dict:
        settings = self.config.data["lg"]
        return {
            "lgConfigured": bool(settings.get("token")),
            "lgCountry": settings.get("country", "BR"),
            "lgError": self._lg_error,
        }


# ---------------------------------------------------------------- tradução de comandos


def _number(body: dict, key: str) -> float:
    try:
        return float(body[key])
    except (TypeError, ValueError):
        raise ControlError("Valor numérico inválido") from None


def gree_command(body: dict) -> dict:
    if "power" in body:
        return {"Pow": 1 if body["power"] else 0}
    if "mode" in body:
        if body["mode"] not in gree.MODE_CODES:
            raise ControlError("Modo não suportado")
        return {"Mod": gree.MODE_CODES[body["mode"]]}
    if "target" in body:
        value = int(round(_number(body, "target")))
        if not 16 <= value <= 30:
            raise ControlError("A temperatura deve ficar entre 16 °C e 30 °C")
        return {"SetTem": value, "TemUn": 0, "TemRec": 0}
    if "fan" in body:
        valid = [v for v, _ in gree.FAN_OPTIONS]
        if str(body["fan"]) not in valid:
            raise ControlError("Velocidade inválida")
        # Escolher uma velocidade cancela Turbo e Silencioso, como no controle remoto.
        return {"WdSpd": int(body["fan"]), "Tur": 0, "Quiet": 0}
    if "swing" in body:
        try:
            return gree.swing_to_raw(str(body["swing"]))
        except ValueError as exc:
            raise ControlError(str(exc)) from None
    if "feature" in body:
        try:
            return gree.feature_to_raw(str(body["feature"]), bool(body.get("on")))
        except ValueError as exc:
            raise ControlError(str(exc)) from None
    raise ControlError("Comando vazio")


def lg_command(caps: lg.Capabilities, body: dict, entry: _LGEntry | None = None) -> dict:
    if "power" in body:
        return {"operation": {"airConOperationMode": "POWER_ON" if body["power"] else "POWER_OFF"}}
    if "mode" in body:
        mode = str(body["mode"])
        value = mode[3:] if mode.startswith("lg:") else lg.MODE_TO_LG.get(mode)
        if value not in caps.modes:
            raise ControlError("Este aparelho LG não oferece esse modo")
        return {"airConJobMode": {"currentJobMode": value}}
    if "target" in body:
        value = _number(body, "target")
        if not caps.temp_min <= value <= caps.temp_max:
            raise ControlError(f"A temperatura deve ficar entre {caps.temp_min:g} °C e {caps.temp_max:g} °C")
        if caps.temp_step >= 1:
            value = int(round(value))
        current_mode = ""
        if entry is not None:
            job = (entry.raw.get("airConJobMode") or {}).get("currentJobMode")
            current_mode = lg.MODE_FROM_LG.get(job, "")
        return {caps.temp_resource: {caps.temp_key_for_mode(current_mode): value, "unit": "C"}}
    if "fan" in body:
        if body["fan"] not in caps.fans:
            raise ControlError("Velocidade não suportada por este aparelho")
        return {"airFlow": {caps.fan_key: body["fan"]}}
    if "swing" in body:
        swing = str(body["swing"])
        if swing not in SWING_LABELS:
            raise ControlError("Direção inválida")
        direction = {}
        if caps.swing_vertical:
            direction["rotateUpDown"] = swing in ("vertical", "both")
        if caps.swing_horizontal:
            direction["rotateLeftRight"] = swing in ("horizontal", "both")
        if not direction:
            raise ControlError("Este aparelho não permite mudar a direção do vento pelo app")
        return {"windDirection": direction}
    if "feature" in body:
        key, on = str(body["feature"]), bool(body.get("on"))
        if key == "turbo" and "POWER" in caps.fans:
            fallback = (entry.last_fan if entry else "") or ("AUTO" if "AUTO" in caps.fans else caps.fans[0])
            return {"airFlow": {caps.fan_key: "POWER" if on else fallback}}
        if key == "eco" and caps.power_save:
            return {"powerSave": {"powerSaveEnabled": on}}
        if key == "light":
            value = lg.light_value(caps.light_values, on)
            if value is not None:
                return {"display": {"light": value}}
        raise ControlError("Função não suportada por este aparelho")
    raise ControlError("Comando vazio")


def apply_lg_payload(state: dict, payload: dict) -> dict:
    """Aplica um comando ao estado guardado, para a tela responder na hora."""
    state = copy.deepcopy(state)
    for resource, values in payload.items():
        current = state.get(resource)
        if isinstance(current, list):
            unit = values.get("unit", "C")
            for item in current:
                if isinstance(item, dict) and item.get("unit") == unit:
                    item.update({k: v for k, v in values.items() if k != "unit"})
        elif isinstance(current, dict):
            current.update(values)
        else:
            state[resource] = dict(values)
    return state
