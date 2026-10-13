"""Simuladores usados nos testes: um aparelho Gree e a API da LG.

Eles reproduzem o protocolo real para que o programa possa ser testado sem
os aparelhos físicos.  Também podem ser usados para ver a tela funcionando:

    python testes/simuladores.py
"""

from __future__ import annotations

import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from climacasa import gree  # noqa: E402


class FakeGree:
    """Aparelho Gree falso escutando em UDP."""

    def __init__(self, mac: str, cipher: int = 1, host: str = "127.0.0.1", port: int = 0, name: str = "") -> None:
        self.mac = mac
        self.cipher = cipher
        self.key = ("K" + mac)[:16].ljust(16, "x")
        self.name = name or mac[-4:]
        self.state = {"Pow": 0, "Mod": 1, "SetTem": 24, "TemUn": 0, "TemRec": 0, "TemSen": 63, "WdSpd": 3,
                      "Tur": 0, "Quiet": 0, "SwUpDn": 1, "SwingLfRig": 1, "SwhSlp": 0, "SlpMod": 0, "Lig": 1,
                      "Health": 0, "Blo": 0, "SvSt": 0, "Air": 0, "StHt": 0, "DwatSen": 0}
        self.commands: list[dict] = []
        self.silent = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.address = self.sock.getsockname()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.sock.close()

    def _reply(self, pack: dict, key: bytes, addr) -> None:
        enc, tag = gree.encrypt_pack(pack, key, self.cipher)
        msg = {"t": "pack", "i": 0, "uid": 0, "cid": self.mac, "tcid": "", "pack": enc}
        if tag:
            msg["tag"] = tag
        self.sock.sendto(json.dumps(msg).encode(), addr)

    def _serve(self) -> None:
        generic = gree.GENERIC_KEY[self.cipher]
        while True:
            try:
                data, addr = self.sock.recvfrom(65535)
            except OSError:
                return
            if self.silent:
                continue
            msg = json.loads(data)
            if msg.get("t") == "scan":
                self._reply({"t": "dev", "cid": self.mac, "mac": self.mac, "name": self.name, "ver": "V1.17",
                             "model": "gree", "brand": "gree"}, generic, addr)
                continue
            key = generic if msg.get("i") == 1 else self.key.encode()
            try:
                pack = gree.decrypt_pack(msg["pack"], key, self.cipher)
            except gree.GreeError:
                continue  # como o aparelho real: ignora o que não consegue decifrar
            if pack.get("t") == "bind":
                self._reply({"t": "bindok", "mac": self.mac, "key": self.key, "r": 200}, generic, addr)
            elif pack.get("t") == "status":
                cols = pack["cols"]
                self._reply({"t": "dat", "mac": self.mac, "r": 200, "cols": cols,
                             "dat": [self.state.get(c, 0) for c in cols]}, self.key.encode(), addr)
            elif pack.get("t") == "cmd":
                values = dict(zip(pack["opt"], pack["p"]))
                self.commands.append(values)
                self.state.update(values)
                self._reply({"t": "res", "mac": self.mac, "r": 200, "opt": pack["opt"], "p": pack["p"],
                             "val": pack["p"]}, self.key.encode(), addr)


LG_DEVICE_ID = "lg-ac-0001"
LG_PROFILE = {
    "property": {
        "airConJobMode": {"currentJobMode": {"type": "enum", "mode": ["r", "w"],
                                             "value": {"r": ["COOL", "AIR_DRY", "FAN", "AUTO", "ENERGY_SAVING"],
                                                       "w": ["COOL", "AIR_DRY", "FAN", "AUTO", "ENERGY_SAVING"]}}},
        "operation": {"airConOperationMode": {"type": "enum", "mode": ["r", "w"],
                                              "value": {"r": ["POWER_ON", "POWER_OFF"], "w": ["POWER_ON", "POWER_OFF"]}}},
        "temperatureInUnits": [
            {"unit": "C",
             "currentTemperature": {"type": "number", "mode": ["r"]},
             "targetTemperature": {"type": "range", "mode": ["r", "w"],
                                   "value": {"r": {"min": 18, "max": 30, "step": 1}, "w": {"min": 18, "max": 30, "step": 1}}}},
            {"unit": "F",
             "currentTemperature": {"type": "number", "mode": ["r"]},
             "targetTemperature": {"type": "range", "mode": ["r", "w"],
                                   "value": {"r": {"min": 64, "max": 86, "step": 2}, "w": {"min": 64, "max": 86, "step": 2}}}},
        ],
        "airFlow": {"windStrength": {"type": "enum", "mode": ["r", "w"],
                                     "value": {"r": ["LOW", "MID", "HIGH", "AUTO", "POWER"],
                                               "w": ["LOW", "MID", "HIGH", "AUTO", "POWER"]}}},
        "windDirection": {"rotateUpDown": {"type": "boolean", "mode": ["r", "w"], "value": {"r": [True, False], "w": [True, False]}}},
        "powerSave": {"powerSaveEnabled": {"type": "boolean", "mode": ["r", "w"], "value": {"r": [True, False], "w": [True, False]}}},
        "display": {"light": {"type": "enum", "mode": ["r", "w"], "value": {"r": ["ON", "OFF"], "w": ["ON", "OFF"]}}},
    }
}


class FakeLG:
    """API LG ThinQ Connect falsa (HTTP local)."""

    TOKEN = "thinqpat_teste"

    def __init__(self) -> None:
        self.state = {
            "airConJobMode": {"currentJobMode": "COOL"},
            "operation": {"airConOperationMode": "POWER_OFF"},
            "temperatureInUnits": [{"currentTemperature": 26, "targetTemperature": 22, "unit": "C"},
                                   {"currentTemperature": 79, "targetTemperature": 72, "unit": "F"}],
            "airFlow": {"windStrength": "MID"},
            "windDirection": {"rotateUpDown": False},
            "powerSave": {"powerSaveEnabled": False},
            "display": {"light": "ON"},
            "airQualitySensor": {"humidity": 61},
        }
        self.controls: list[dict] = []
        self.headers_seen: list = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _auth(self) -> bool:
                fake.headers_seen.append(self.headers)
                if self.headers.get("Authorization") != f"Bearer {FakeLG.TOKEN}":
                    self._reply(401, {"error": {"code": "1103", "message": "Invalid token"}})
                    return False
                return True

            def do_GET(self):
                if not self._auth():
                    return
                if self.path == "/devices":
                    return self._reply(200, {"response": [
                        {"deviceId": LG_DEVICE_ID, "deviceInfo": {"deviceType": "DEVICE_AIR_CONDITIONER",
                                                                  "modelName": "S4-W12JA3AA", "alias": "Sala LG"}},
                        {"deviceId": "fridge", "deviceInfo": {"deviceType": "DEVICE_REFRIGERATOR", "alias": "Geladeira"}},
                    ]})
                if self.path == f"/devices/{LG_DEVICE_ID}/profile":
                    return self._reply(200, {"response": LG_PROFILE})
                if self.path == f"/devices/{LG_DEVICE_ID}/state":
                    return self._reply(200, {"response": fake.state})
                return self._reply(404, {"error": {"code": "1205", "message": "Not exist device"}})

            def do_POST(self):
                if not self._auth():
                    return
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                fake.controls.append(body)
                if "operation" not in body and fake.state["operation"]["airConOperationMode"] == "POWER_OFF" \
                        and "airConJobMode" in body:
                    return self._reply(400, {"error": {"code": "2304", "message": "Command not supported in power off"}})
                for resource, values in body.items():
                    current = fake.state.get(resource)
                    if isinstance(current, list):
                        for item in current:
                            if item["unit"] == values.get("unit", "C"):
                                item.update({k: v for k, v in values.items() if k != "unit"})
                    else:
                        fake.state.setdefault(resource, {}).update(values)
                return self._reply(200, {"response": {}})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()


if __name__ == "__main__":
    # Demonstração: dois Gree falsos + um LG falso, com a tela de verdade.
    import tempfile

    from climacasa.config import Config
    from climacasa.devices import Manager
    from climacasa.server import ClimaServer

    a = FakeGree("9424b883c954", cipher=1, host="127.0.0.2")
    b = FakeGree("9424b883d28b", cipher=2, host="127.0.0.3", port=a.address[1])
    lg_api = FakeLG()
    cfg = Config(Path(tempfile.mkdtemp()) / "config.json")
    cfg.data["lg"]["token"] = FakeLG.TOKEN
    manager = Manager(cfg, lg_base_url=lg_api.base_url, gree_port=a.address[1],
                      gree_scan_targets=["127.0.0.2", "127.0.0.3"])
    manager.discover_gree()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ClimaServer(port, manager)
    print(f"Demonstração em http://127.0.0.1:{port}/  (token {server.token})")
    server.serve_forever()
