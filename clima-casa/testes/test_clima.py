"""Testes automáticos.  Rode com:  python -m unittest discover -s testes"""

from __future__ import annotations

import functools
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from climacasa import __version__, aes, atualizar, gree  # noqa: E402
from climacasa import server as server_module  # noqa: E402
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
        self.assertEqual(gree.vane_from_raw({"SwUpDn": 0}), "auto")
        self.assertEqual(gree.vane_from_raw({"SwUpDn": 1}), "swing")
        self.assertEqual(gree.vane_from_raw({"SwUpDn": 9}), "swing")
        self.assertEqual(gree.vane_from_raw({"SwUpDn": 2}), "1")
        self.assertEqual(gree.vane_from_raw({"SwUpDn": 6}), "5")
        self.assertEqual(gree.vane_to_raw("3"), {"SwUpDn": 4})
        self.assertEqual(gree.vane_to_raw("swing"), {"SwUpDn": 1})
        with self.assertRaises(ValueError):
            gree.vane_to_raw("6")
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
        view = self.manager.control(dev_id, {"vane": "3"})
        self.assertEqual(view["vane"], "3")
        self.assertEqual(self.gree_a.state["SwUpDn"], 4)
        self.assertEqual(self.gree_a.commands[-1], {"SwUpDn": 4})  # aleta horizontal intocada
        self.assertEqual([v["value"] for v in view["vanes"]], ["auto", "swing", "1", "2", "3", "4", "5"])
        self.assertIsNone(view["hswing"])
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
        entry.updated = float("-inf")
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
        self.assertEqual([v["value"] for v in view["vanes"]], ["fixed", "swing"])
        self.assertEqual(view["vane"], "fixed")
        self.assertIsNone(view["hswing"])  # o perfil simulado não tem aleta horizontal
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
        self.assertEqual(self.manager.control(dev_id, {"vane": "swing"})["vane"], "swing")
        self.assertEqual(self.lg.controls[-1], {"windDirection": {"rotateUpDown": True}})
        with self.assertRaises(ControlError):
            self.manager.control(dev_id, {"vane": "3"})  # a API da LG não tem posições fixas
        with self.assertRaises(ControlError):
            self.manager.control(dev_id, {"hswing": True})
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

    def test_closing_window_quits_only_after_grace_period(self):
        server_module.CLOSE_GRACE = 0.4
        self.addCleanup(setattr, server_module, "CLOSE_GRACE", 15.0)
        self.assertEqual(self.request("POST", "/api/bye?t=errado", {}, token=False)[0], 403)
        # recarregar a página: o aviso de fechamento é seguido de um novo pedido
        self.assertEqual(self.request("POST", f"/api/bye?t={self.server.token}", {}, token=False)[0], 200)
        self.assertEqual(self.request("GET", "/api/devices")[0], 200)
        time.sleep(0.8)
        self.assertFalse(self.server.quit_event.is_set())
        # fechar de verdade: nenhum pedido depois do aviso
        self.request("POST", f"/api/bye?t={self.server.token}", {}, token=False)
        self.assertTrue(self.server.quit_event.wait(3))

    def test_ping_identifies_version_and_instance(self):
        status, body = self.request("GET", "/ping", token=False)
        info = json.loads(body)
        self.assertEqual((info["app"], info["version"], info["instance"]), ("clima-casa", __version__, self.server.instance))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.published = self.root / "publicado"
        self.installed = self.root / "instalado"
        for folder, files in (
            (self.installed, {"climacasa/a.py": b"velho\n", "climacasa/antigo.py": b"apagar\n", "INSTALAR.bat": b"x\r\n",
                              "meu-arquivo.txt": b"do usuario\n"}),
            (self.published, {"climacasa/a.py": b"novo\n", "climacasa/b.py": b"b\n", "INSTALAR.bat": b"@echo off\ny\n"}),
        ):
            for rel, data in files.items():
                (folder / rel).parent.mkdir(parents=True, exist_ok=True)
                (folder / rel).write_bytes(data)
        old = {"versao": "1.0.0", "arquivos": {r: atualizar.digest((self.installed / r).read_bytes())
                                               for r in ("climacasa/a.py", "climacasa/antigo.py", "INSTALAR.bat")}}
        (self.installed / "versao.json").write_text(json.dumps(old), encoding="utf-8")
        new = {"versao": "99.0.0", "notas": "teste", "arquivos": {
            r: atualizar.digest((self.published / r).read_bytes()) for r in ("climacasa/a.py", "climacasa/b.py", "INSTALAR.bat")}}
        (self.published / "versao.json").write_text(json.dumps(new), encoding="utf-8")
        handler = functools.partial(QuietHandler, directory=str(self.published))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.updater = atualizar.Updater(f"http://127.0.0.1:{self.httpd.server_address[1]}/", self.installed)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_check_reports_new_version(self):
        info = self.updater.check()
        self.assertTrue(info["available"])
        self.assertEqual((info["current"], info["latest"], info["notes"]), (__version__, "99.0.0", "teste"))

    def test_apply_replaces_files_and_removes_stale_ones(self):
        self.assertEqual(self.updater.apply(), "99.0.0")
        self.assertEqual((self.installed / "climacasa/a.py").read_bytes(), b"novo\n")
        self.assertEqual((self.installed / "climacasa/b.py").read_bytes(), b"b\n")
        self.assertFalse((self.installed / "climacasa/antigo.py").exists())
        self.assertEqual((self.installed / "INSTALAR.bat").read_bytes(), b"@echo off\r\ny\r\n")
        self.assertTrue((self.installed / "meu-arquivo.txt").exists())  # não é do programa: fica
        self.assertEqual(atualizar.read_manifest(self.installed)["versao"], "99.0.0")

    def test_corrupted_download_changes_nothing(self):
        (self.published / "climacasa/b.py").write_bytes(b"adulterado\n")
        with self.assertRaises(atualizar.UpdateError):
            self.updater.apply()
        self.assertEqual((self.installed / "climacasa/a.py").read_bytes(), b"velho\n")
        self.assertTrue((self.installed / "climacasa/antigo.py").exists())

    def test_install_from_extracted_folder(self):
        atualizar.install_from_folder(self.published, self.installed)
        self.assertEqual((self.installed / "climacasa/a.py").read_bytes(), b"novo\n")
        self.assertFalse((self.installed / "climacasa/antigo.py").exists())

    def test_manifest_with_unsafe_path_is_rejected(self):
        bad = {"versao": "99.0.0", "arquivos": {"../fora.txt": atualizar.digest(b"x")}}
        with self.assertRaises(atualizar.UpdateError):
            atualizar.replace_files(self.installed, bad, lambda rel: b"x")

    def test_published_manifest_matches_program_files(self):
        manifest = atualizar.read_manifest(atualizar.APP_DIR)
        self.assertIsNotNone(manifest, "rode: python -m climacasa.atualizar")
        self.assertEqual(manifest["versao"], __version__, "versao.json desatualizado: rode python -m climacasa.atualizar")
        self.assertEqual(manifest["arquivos"], atualizar.build_manifest()["arquivos"],
                         "versao.json desatualizado: rode python -m climacasa.atualizar")


if __name__ == "__main__":
    unittest.main()
