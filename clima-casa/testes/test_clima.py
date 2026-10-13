"""Testes automáticos.  Rode com:  python -m unittest discover -s testes"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from climacasa import aes, gree  # noqa: E402
from climacasa.config import Config  # noqa: E402
from climacasa.devices import ControlError, Manager  # noqa: E402
from climacasa.server import ClimaServer  # noqa: E402
from simuladores import LG_DEVICE_ID, FakeGree, FakeLG  # noqa: E402


def temp_config() -> Config:
    return Config(Path(tempfile.mkdtemp()) / "config.json")


class AESTests(unittest.TestCase):
    def test_fips197_block(self):
        key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        block = bytes.fromhex("00112233445566778899aabbccddeeff")
        cipher = aes.AES(key)
        out = cipher.encrypt_block(block)
        self.assertEqual(out.hex(), "69c4e0d86a7b0430d8cdb78070b4c55a")
        self.assertEqual(cipher.decrypt_block(out), block)

    def test_fips197_aes256(self):
        key = bytes(range(32))
        block = bytes.fromhex("00112233445566778899aabbccddeeff")
        self.assertEqual(aes.AES(key).encrypt_block(block).hex(), "8ea2b7ca516745bfeafc49904b496089")

    def test_gcm_nist_case4(self):
        key = bytes.fromhex("feffe9928665731c6d6a8f9467308308")
        iv = bytes.fromhex("cafebabefacedbaddecaf888")
        aad = bytes.fromhex("feedfacedeadbeeffeedfacedeadbeefabaddad2")
        pt = bytes.fromhex(
            "d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a72"
            "1c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39")
        ct, tag = aes.gcm_encrypt(key, iv, pt, aad)
        self.assertEqual(ct.hex(), "42831ec2217774244b7221b784d0d49ce3aa212f2c02a4e035c17e2329aca12e"
                                   "21d514b25466931c7d8f6a5aac84aa051ba30b396a0aac973d58e091")
        self.assertEqual(tag.hex(), "5bc94fbc3221a5db94fae95ae7121a47")
        self.assertEqual(aes.gcm_decrypt(key, iv, ct, aad, tag), pt)
        with self.assertRaises(ValueError):
            aes.gcm_decrypt(key, iv, ct, aad, bytes(16))

    def test_matches_reference_library_when_available(self):
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            self.skipTest("biblioteca cryptography não instalada")
        for n in (0, 1, 15, 16, 17, 100):
            data = os.urandom(n)
            key = os.urandom(16)
            enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
            pad = 16 - n % 16
            self.assertEqual(aes.ecb_encrypt(key, data), enc.update(data + bytes([pad]) * pad) + enc.finalize())
            nonce = os.urandom(12)
            ct, tag = aes.gcm_encrypt(key, nonce, data, b"qualcomm-test")
            self.assertEqual(ct + tag, AESGCM(key).encrypt(nonce, data, b"qualcomm-test"))


class GreeProtocolTests(unittest.TestCase):
    def setUp(self):
        first = FakeGree("9424b883c954", cipher=1, host="127.0.0.2")
        # o segundo simulador usa a mesma porta do primeiro, em outro IP
        self.port = first.address[1]
        self.devices = [first, FakeGree("9424b883d28b", cipher=2, host="127.0.0.3", port=self.port)]

    def tearDown(self):
        for dev in self.devices:
            dev.close()

    def test_scan_detects_both_cipher_generations(self):
        found = {d.mac: d for d in gree.discover(timeout=1, targets=["127.0.0.2", "127.0.0.3"], port=self.port)}
        self.assertEqual(found["9424b883c954"].cipher, 1)
        self.assertEqual(found["9424b883d28b"].cipher, 2)
        self.assertEqual(found["9424b883d28b"].ip, "127.0.0.3")

    def test_bind_status_and_command(self):
        for fake in self.devices:
            # começa com a cifra errada de propósito: o pareamento deve descobrir a certa
            dev = gree.GreeDevice(mac=fake.mac, ip=fake.address[0], cipher=1 if fake.cipher == 2 else 2,
                                  port=self.port, timeout=0.5)
            self.assertEqual(dev.bind(), fake.key)
            self.assertEqual(dev.cipher, fake.cipher)
            self.assertEqual(dev.status()["SetTem"], 24)
            dev.command({"Pow": 1, "SetTem": 21})
            self.assertEqual(fake.state["Pow"], 1)
            self.assertEqual(fake.state["SetTem"], 21)

    def test_rebinds_when_key_changes(self):
        fake = self.devices[0]
        dev = gree.GreeDevice(mac=fake.mac, ip=fake.address[0], cipher=1, key="chave-antiga-123", port=self.port,
                              timeout=0.5)
        self.assertEqual(dev.status()["Pow"], 0)
        self.assertEqual(dev.key, fake.key)

    def test_silent_device_raises_timeout(self):
        fake = self.devices[0]
        fake.silent = True
        dev = gree.GreeDevice(mac=fake.mac, ip=fake.address[0], key=fake.key, port=self.port, timeout=0.3)
        with self.assertRaises(gree.GreeTimeout):
            dev.status()

    def test_state_translation(self):
        self.assertEqual(gree.current_temperature({"TemSen": 63}), 23)
        self.assertEqual(gree.current_temperature({"TemSen": 23}), 23)
        self.assertIsNone(gree.current_temperature({"TemSen": 0}))
        self.assertEqual(gree.swing_from_raw({"SwUpDn": 1, "SwingLfRig": 1}), "both")
        self.assertEqual(gree.swing_from_raw({"SwUpDn": 3, "SwingLfRig": 0}), "off")
        self.assertEqual(gree.feature_to_raw("turbo", True), {"Tur": 1, "Quiet": 0})
        self.assertEqual(gree.feature_to_raw("sleep", False), {"SwhSlp": 0, "SlpMod": 0})


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.gree_a = FakeGree("9424b883c954", cipher=1, host="127.0.0.2")
        self.gree_b = FakeGree("9424b883d28b", cipher=2, host="127.0.0.3", port=self.gree_a.address[1])
        self.lg = FakeLG()
        self.config = temp_config()
        self.manager = Manager(self.config, lg_base_url=self.lg.base_url, gree_port=self.gree_a.address[1],
                               gree_scan_targets=["127.0.0.2", "127.0.0.3"])

    def tearDown(self):
        self.gree_a.close()
        self.gree_b.close()
        self.lg.close()

    def test_discovery_names_and_persistence(self):
        result = self.manager.discover_gree()
        self.assertEqual(result["found"], 2)
        names = {d["name"] for d in self.manager.devices()}
        self.assertEqual(names, {"Ângelo", "Escritório"})
        saved = json.loads(self.config.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["gree"]["9424b883c954"]["key"], self.gree_a.key)
        self.assertEqual(saved["gree"]["9424b883d28b"]["cipher"], 2)
        # um novo Manager lê a configuração e funciona sem procurar de novo
        again = Manager(Config(self.config.path), gree_port=self.gree_a.address[1], gree_scan_targets=[])
        dev = next(d for d in again.devices() if d["id"] == "gree:9424b883d28b")
        self.assertTrue(dev["online"])
        self.assertEqual(dev["current"], 23)

    def test_gree_controls(self):
        self.manager.discover_gree()
        dev_id = "gree:9424b883c954"
        self.assertTrue(self.manager.control(dev_id, {"power": True})["power"])
        self.assertEqual(self.manager.control(dev_id, {"mode": "dry"})["mode"], "dry")
        self.assertEqual(self.manager.control(dev_id, {"target": 19})["target"], 19)
        self.assertEqual(self.manager.control(dev_id, {"fan": "5"})["fan"], "5")
        self.assertEqual(self.manager.control(dev_id, {"swing": "vertical"})["swing"], "vertical")
        view = self.manager.control(dev_id, {"feature": "turbo", "on": True})
        self.assertTrue(next(f for f in view["features"] if f["key"] == "turbo")["on"])
        self.assertEqual(self.gree_a.state["Tur"], 1)
        with self.assertRaises(ControlError):
            self.manager.control(dev_id, {"target": 40})
        with self.assertRaises(ControlError):
            self.manager.control(dev_id, {"mode": "voar"})

    def test_offline_gree_reports_error(self):
        self.manager.discover_gree()
        self.gree_a.silent = True
        entry = self.manager._gree["9424b883c954"]
        entry.device.timeout = 0.3
        entry.updated = 0
        self.manager._last_discovery = 10**12  # sem nova procura durante o teste
        dev = next(d for d in self.manager.devices() if d["id"] == "gree:9424b883c954")
        self.assertFalse(dev["online"])
        self.assertIn("sem resposta", dev["error"])

    def test_lg_token_validation(self):
        with self.assertRaises(ControlError) as ctx:
            self.manager.set_lg_token("errado", "BR")
        self.assertIn("Token da LG inválido", str(ctx.exception))
        self.assertEqual(self.manager.set_lg_token(FakeLG.TOKEN, "BR"), {"devices": 1})
        headers = self.lg.headers_seen[-1]
        self.assertEqual(headers.get("x-country"), "BR")
        self.assertEqual(headers.get("x-api-key"), "v6GFvkweNo7DK7yD3ylIZ9w52aKBU0eJ7wLXkSR3")
        self.assertTrue(headers.get("x-client-id").startswith("clima-casa-"))

    def test_lg_view_and_controls(self):
        self.manager.set_lg_token(FakeLG.TOKEN, "BR")
        dev_id = f"lg:{LG_DEVICE_ID}"
        view = next(d for d in self.manager.devices() if d["id"] == dev_id)
        self.assertEqual(view["name"], "Sala LG")
        self.assertEqual((view["tempMin"], view["tempMax"]), (18, 30))
        self.assertEqual(view["current"], 26)
        self.assertEqual(view["humidity"], 61)
        self.assertEqual([m["value"] for m in view["modes"]], ["cool", "dry", "fan", "auto", "lg:ENERGY_SAVING"])
        self.assertEqual([f["value"] for f in view["fans"]], ["AUTO", "LOW", "MID", "HIGH"])
        self.assertEqual([s["value"] for s in view["swings"]], ["off", "vertical"])
        self.assertEqual({f["key"] for f in view["features"]}, {"turbo", "eco", "light"})

        with self.assertRaises(ControlError) as ctx:
            self.manager.control(dev_id, {"mode": "dry"})
        self.assertIn("Ligue o aparelho", str(ctx.exception))

        self.assertTrue(self.manager.control(dev_id, {"power": True})["power"])
        self.assertEqual(self.lg.controls[-1], {"operation": {"airConOperationMode": "POWER_ON"}})
        self.manager.control(dev_id, {"mode": "dry"})
        self.assertEqual(self.lg.controls[-1], {"airConJobMode": {"currentJobMode": "AIR_DRY"}})
        self.assertEqual(self.manager.control(dev_id, {"target": 25})["target"], 25)
        self.assertEqual(self.lg.controls[-1], {"temperatureInUnits": {"targetTemperature": 25, "unit": "C"}})
        self.manager.control(dev_id, {"fan": "HIGH"})
        self.assertEqual(self.lg.controls[-1], {"airFlow": {"windStrength": "HIGH"}})
        self.assertEqual(self.manager.control(dev_id, {"swing": "both"})["swing"], "vertical")
        self.assertEqual(self.lg.controls[-1], {"windDirection": {"rotateUpDown": True}})
        view = self.manager.control(dev_id, {"feature": "turbo", "on": True})
        self.assertEqual(self.lg.controls[-1], {"airFlow": {"windStrength": "POWER"}})
        self.assertTrue(next(f for f in view["features"] if f["key"] == "turbo")["on"])
        self.assertEqual(view["fan"], "HIGH")
        self.manager.control(dev_id, {"feature": "turbo", "on": False})
        self.assertEqual(self.lg.controls[-1], {"airFlow": {"windStrength": "HIGH"}})
        self.manager.control(dev_id, {"feature": "eco", "on": True})
        self.assertEqual(self.lg.controls[-1], {"powerSave": {"powerSaveEnabled": True}})
        self.manager.control(dev_id, {"feature": "light", "on": False})
        self.assertEqual(self.lg.controls[-1], {"display": {"light": "OFF"}})
        with self.assertRaises(ControlError):
            self.manager.control(dev_id, {"target": 10})


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.lg = FakeLG()
        config = temp_config()
        config.data["lg"]["token"] = FakeLG.TOKEN
        self.server = ClimaServer(0, Manager(config, lg_base_url=self.lg.base_url, gree_scan_targets=[]))
        Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.lg.close()

    def request(self, method, path, body=None, token=True, host=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Clima-Token"] = self.server.token
        if host:
            headers["Host"] = host
        req = urllib.request.Request(self.base + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_page_contains_token_and_assets_load(self):
        status, body = self.request("GET", "/", token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), body)
        for asset in ("/app.js", "/app.css", "/icone.svg"):
            self.assertEqual(self.request("GET", asset, token=False)[0], 200)
        self.assertEqual(self.request("GET", "/../config.py", token=False)[0], 404)

    def test_api_requires_token_and_local_host(self):
        self.assertEqual(self.request("GET", "/api/devices", token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/quit", {}, token=False)[0], 403)
        self.assertEqual(self.request("GET", "/api/devices", host="evil.example:80")[0], 403)
        self.assertFalse(self.server.quit_event.is_set())

    def test_control_round_trip(self):
        status, body = self.request("GET", "/api/devices")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["lgConfigured"])
        self.assertEqual(data["devices"][0]["id"], f"lg:{LG_DEVICE_ID}")
        status, body = self.request("POST", f"/api/devices/lg:{LG_DEVICE_ID}/control", {"power": True})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["device"]["power"])
        status, body = self.request("POST", f"/api/devices/lg:{LG_DEVICE_ID}/control", {"target": 99})
        self.assertEqual(status, 400)
        self.assertIn("temperatura", json.loads(body)["error"])
        status, _ = self.request("POST", "/api/gree/discover", {"ip": "não-é-ip"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
