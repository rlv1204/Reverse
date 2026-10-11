"""Testes com um aparelho Gree simulado em 127.0.0.1:7000 (ECB e GCM)."""
import json
import socket
import threading
import unittest

import gree


class FakeUnit(threading.Thread):
    def __init__(self, cipher_cls):
        super().__init__(daemon=True)
        self.cls = cipher_cls
        self.state = {"Pow": 0, "Mod": 1, "SetTem": 24, "WdSpd": 0, "TemSen": 66}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", gree.PORT))
        self.sock.settimeout(0.2)
        self.running = True

    def reply(self, addr, inner, cipher, i=0):
        pack, tag = cipher.encrypt(inner)
        msg = {"t": "pack", "i": i, "uid": 0, "cid": "f4911e000001", "tcid": "", "pack": pack}
        if tag:
            msg["tag"] = tag
        self.sock.sendto(json.dumps(msg).encode(), addr)

    def run(self):
        generic, private = self.cls(), self.cls(b"PrivKey123456789")
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            req = json.loads(data)
            if req["t"] == "scan":
                self.reply(addr, {"t": "dev", "cid": "f4911e000001", "mac": "f4911e000001",
                                  "name": "Sala", "ver": "V1.2.1"}, gree.CipherV1(), 1)
                continue
            try:
                inner = generic.decrypt(req["pack"], req.get("tag"))
                assert inner["t"] == "bind"
                self.reply(addr, {"t": "bindok", "mac": "f4911e000001", "key": "PrivKey123456789"}, generic, 1)
                continue
            except Exception:
                pass
            try:
                inner = private.decrypt(req["pack"], req.get("tag"))
            except Exception:
                continue  # aparelho real também ignora pacotes com a cifra errada
            if inner["t"] == "status":
                self.reply(addr, {"t": "dat", "cols": inner["cols"],
                                  "dat": [self.state.get(c, 0) for c in inner["cols"]]}, private)
            elif inner["t"] == "cmd":
                self.state.update(zip(inner["opt"], inner["p"]))
                self.reply(addr, {"t": "res", "opt": inner["opt"], "p": inner["p"], "val": inner["p"], "r": 200}, private)


class GreeTest(unittest.TestCase):
    def roundtrip(self, cls):
        unit = FakeUnit(cls)
        unit.start()
        try:
            devs = gree.scan("127.0.0.1", timeout=1.0)
            self.assertEqual([d.name for d in devs], ["Sala"])
            d = gree.bind(devs[0])
            self.assertEqual((d.key, d.cipher), ("PrivKey123456789", cls.name))
            self.assertEqual(gree.set_props(d, Pow=1, SetTem=22), {"Pow": 1, "SetTem": 22})
            st = gree.status(d, ["Pow", "SetTem", "TemSen"])
            self.assertEqual(st, {"Pow": 1, "SetTem": 22, "TemSen": 66})
        finally:
            unit.running = False
            unit.join()
            unit.sock.close()

    def test_ecb_unit(self):
        self.roundtrip(gree.CipherV1)

    def test_gcm_unit(self):
        self.roundtrip(gree.CipherV2)

    def test_gcm_without_tag_matches(self):
        c = gree.CipherV2()
        pack, _tag = c.encrypt({"t": "x", "v": 1})
        self.assertEqual(c.decrypt(pack), {"t": "x", "v": 1})


if __name__ == "__main__":
    unittest.main()
