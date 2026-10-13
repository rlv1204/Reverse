"""Controle de aparelhos LG pela API oficial "LG ThinQ Connect".

A LG oferece uma API pública para os aparelhos cadastrados no app LG ThinQ.
O acesso é feito com um "Token de Acesso Pessoal" (PAT) que o próprio dono
da conta gera em https://connect-pat.lgthinq.com (veja o LEIA-ME).

Formato da API (o mesmo usado pela biblioteca oficial ``thinqconnect`` da LG):
  * servidor:  https://api-<região>.lgthinq.com   (Brasil -> região "aic");
  * cabeçalhos: Authorization (Bearer <token>), x-country, x-message-id,
    x-client-id, x-api-key e x-service-phase;
  * GET  devices                    -> lista de aparelhos;
  * GET  devices/<id>/profile       -> o que o aparelho aceita (modos, faixas);
  * GET  devices/<id>/state         -> estado atual;
  * POST devices/<id>/control       -> comandos, ex. {"operation": {...}}.
"""

from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
import uuid

API_KEY = "v6GFvkweNo7DK7yD3ylIZ9w52aKBU0eJ7wLXkSR3"
AIR_CONDITIONER = "DEVICE_AIR_CONDITIONER"

_REGIONS = {
    "aic": "AG AR AW BB BO BR BS BZ CA CL CO CR CU DM DO EC GD GT GY HN HT JM KN LC MX NI PA PE PR PY SR SV TT US UY VC VE",
    "kic": "AU BD CN HK ID IN JP KH KR LA LK MM MY NP NZ PH SG TH TW VN",
}

MODE_FROM_LG = {"COOL": "cool", "AIR_DRY": "dry", "FAN": "fan", "AUTO": "auto", "HEAT": "heat"}
MODE_TO_LG = {v: k for k, v in MODE_FROM_LG.items()}
EXTRA_MODE_LABELS = {"ENERGY_SAVING": "Eco", "AIR_CLEAN": "Purificar", "AROMA": "Aroma"}

FAN_LABELS = {
    "AUTO": "Automático",
    "SLOW": "Muito baixo",
    "SLOW_LOW": "Muito baixo",
    "LOW": "Baixo",
    "LOW_MID": "Médio-baixo",
    "MID": "Médio",
    "MID_HIGH": "Médio-alto",
    "HIGH": "Alto",
    "HIGH_POWER": "Muito alto",
    "POWER": "Jet (máximo)",
    "NATURE": "Natural",
}
FAN_ORDER = list(FAN_LABELS)

ERROR_MESSAGES = {
    "1103": "Token da LG inválido. Gere um novo token e cole nas Configurações.",
    "1218": "Token da LG inválido. Gere um novo token e cole nas Configurações.",
    "1302": "Token da LG não encontrado. Gere um novo token e cole nas Configurações.",
    "1306": "Muitos pedidos à LG em pouco tempo. Aguarde um minuto e tente de novo.",
    "1307": "O país escolhido não é atendido pela API da LG.",
    "1308": "Este token não tem permissão de controle. Gere um token marcando todas as permissões.",
    "1222": "O ar-condicionado LG está desconectado da internet.",
    "2209": "O aparelho demorou a responder. Tente de novo.",
    "2210": "A LG pediu para tentar de novo em instantes.",
    "2301": "O controle remoto pela internet está desativado no aparelho.",
    "2302": "Este comando não é aceito no estado atual do aparelho.",
    "2304": "Ligue o aparelho antes de alterar esta opção.",
    "2305": "Esta opção não está disponível neste modo.",
}


class LGError(Exception):
    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


def region_for_country(country: str) -> str:
    country = country.upper()
    for region, countries in _REGIONS.items():
        if country in countries.split():
            return region
    return "eic"


def _message_id() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode()


class ThinQClient:
    def __init__(self, token: str, country: str, client_id: str, base_url: str | None = None, timeout: float = 15) -> None:
        self.token = token.strip()
        self.country = (country or "BR").upper()
        self.client_id = client_id
        self.base_url = (base_url or f"https://api-{region_for_country(self.country)}.lgthinq.com").rstrip("/")
        self.timeout = timeout
        self._ssl = ssl.create_default_context()

    def _request(self, method: str, endpoint: str, body: dict | None = None, extra_headers: dict | None = None):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "x-country": self.country,
            "x-message-id": _message_id(),
            "x-client-id": self.client_id,
            "x-api-key": API_KEY,
            "x-service-phase": "OP",
            "Accept": "application/json",
            **(extra_headers or {}),
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.base_url}/{endpoint}", data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl) as resp:
                payload = json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raise self._error_from_http(exc) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise LGError(f"Sem conexão com os servidores da LG ({reason}). Verifique a internet.") from None
        except ValueError:
            raise LGError("A LG respondeu em um formato inesperado.") from None
        return payload.get("response") if isinstance(payload, dict) else payload

    @staticmethod
    def _error_from_http(exc: urllib.error.HTTPError) -> LGError:
        code, message = "", ""
        try:
            error = json.loads(exc.read() or b"{}").get("error") or {}
            code, message = str(error.get("code", "")), str(error.get("message", ""))
        except (ValueError, AttributeError):
            pass
        if exc.code == 401 and not code:
            code = "1103"
        text = ERROR_MESSAGES.get(code) or f"A LG recusou o pedido ({code or exc.code}{': ' + message if message else ''})."
        return LGError(text, code)

    def devices(self) -> list[dict]:
        result = self._request("GET", "devices") or []
        return result if isinstance(result, list) else []

    def profile(self, device_id: str) -> dict:
        return self._request("GET", f"devices/{device_id}/profile") or {}

    def state(self, device_id: str) -> dict:
        return self._request("GET", f"devices/{device_id}/state") or {}

    def control(self, device_id: str, payload: dict) -> dict:
        return self._request("POST", f"devices/{device_id}/control", payload, {"x-conditional-control": "true"}) or {}


# ---------------------------------------------------------------- perfil do aparelho


def _prop(profile: dict, resource: str, name: str) -> dict:
    res = (profile.get("property") or {}).get(resource)
    if isinstance(res, list):
        res = next((r for r in res if isinstance(r, dict) and r.get("unit") == "C"), res[0] if res else {})
    prop = (res or {}).get(name) if isinstance(res, dict) else None
    return prop if isinstance(prop, dict) else {}


def _writable(prop: dict) -> bool:
    return "w" in (prop.get("mode") or [])


def _write_values(prop: dict):
    return (prop.get("value") or {}).get("w")


class Capabilities:
    """O que um aparelho LG aceita, extraído do seu perfil."""

    def __init__(self, profile: dict) -> None:
        props = profile.get("property") or {}
        modes = _write_values(_prop(profile, "airConJobMode", "currentJobMode")) or list(MODE_FROM_LG)
        self.modes: list[str] = [m for m in modes if isinstance(m, str)]

        self.temp_resource = "temperatureInUnits" if "temperatureInUnits" in props else "temperature"
        self.temp_keys = {}
        for key in ("targetTemperature", "coolTargetTemperature", "heatTargetTemperature", "autoTargetTemperature"):
            prop = _prop(profile, self.temp_resource, key)
            if _writable(prop):
                self.temp_keys[key] = _write_values(prop) or {}
        rng = next(iter(self.temp_keys.values()), {}) if self.temp_keys else {}
        self.temp_min = float(rng.get("min", 18)) if isinstance(rng, dict) else 18.0
        self.temp_max = float(rng.get("max", 30)) if isinstance(rng, dict) else 30.0
        self.temp_step = float(rng.get("step", 1)) if isinstance(rng, dict) else 1.0

        air_flow = props.get("airFlow") if isinstance(props.get("airFlow"), dict) else {}
        self.fan_key = "windStrengthDetail" if "windStrengthDetail" in air_flow else "windStrength"
        fans = _write_values(_prop(profile, "airFlow", self.fan_key)) or []
        self.fans: list[str] = sorted(
            (f for f in fans if isinstance(f, str)),
            key=lambda f: FAN_ORDER.index(f) if f in FAN_ORDER else len(FAN_ORDER),
        )

        self.swing_vertical = _writable(_prop(profile, "windDirection", "rotateUpDown"))
        self.swing_horizontal = _writable(_prop(profile, "windDirection", "rotateLeftRight"))
        self.power_save = _writable(_prop(profile, "powerSave", "powerSaveEnabled"))
        light = _write_values(_prop(profile, "display", "light")) or []
        self.light_values = light if isinstance(light, list) else []

    def temp_key_for_mode(self, mode: str) -> str:
        preferred = {"cool": "coolTargetTemperature", "heat": "heatTargetTemperature", "auto": "autoTargetTemperature"}
        if "targetTemperature" in self.temp_keys:
            return "targetTemperature"
        key = preferred.get(mode)
        if key in self.temp_keys:
            return key
        return next(iter(self.temp_keys), "targetTemperature")


def _temperatures(state: dict) -> dict:
    temps = state.get("temperatureInUnits")
    if isinstance(temps, list):
        return next((t for t in temps if isinstance(t, dict) and t.get("unit") == "C"), {})
    temps = state.get("temperature")
    if isinstance(temps, list):
        return next((t for t in temps if isinstance(t, dict) and t.get("unit") == "C"), {})
    return temps if isinstance(temps, dict) else {}


def light_is_on(value) -> bool:
    return str(value).upper() not in ("OFF", "FALSE", "0", "NONE", "")


def light_value(values: list, on: bool):
    """Escolhe o valor do perfil que liga/desliga a luz do painel."""
    upper = {str(v).upper(): v for v in values}
    if on:
        for candidate in ("ON", "TRUE", "LEVEL_3", "LEVEL_2", "LEVEL_1", "BRIGHT"):
            if candidate in upper:
                return upper[candidate]
        return next((v for v in values if light_is_on(v)), None)
    return upper.get("OFF")
