"""AES em Python puro (sem bibliotecas externas).

Os aparelhos Gree criptografam as mensagens da rede local com AES-128:
  * firmware antigo  -> AES-ECB com preenchimento PKCS#7;
  * firmware novo    -> AES-GCM com nonce e dados associados fixos.

As mensagens têm poucas centenas de bytes, então uma implementação em
Python puro é rápida o bastante e evita que o usuário precise instalar
pacotes adicionais.  A implementação é verificada em testes/test_aes.py
contra os vetores oficiais do NIST (FIPS-197 e SP 800-38D).
"""

from __future__ import annotations


def _xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x11B) & 0xFF if a & 0x100 else a


def _gmul(a: int, b: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = _xtime(a)
        b >>= 1
    return result


def _build_sbox() -> tuple[list[int], list[int]]:
    sbox = [0] * 256
    inv = [0] * 256
    for x in range(256):
        # inverso multiplicativo em GF(2^8) (0 mapeia para 0)
        y = 0
        if x:
            y = 1
            for _ in range(254):
                y = _gmul(y, x)
        s = y
        for shift in range(1, 5):
            s ^= ((y << shift) | (y >> (8 - shift))) & 0xFF
        s ^= 0x63
        sbox[x] = s
        inv[s] = x
    return sbox, inv


_SBOX, _INV_SBOX = _build_sbox()
_MUL2 = [_gmul(x, 2) for x in range(256)]
_MUL3 = [_gmul(x, 3) for x in range(256)]
_MUL9 = [_gmul(x, 9) for x in range(256)]
_MUL11 = [_gmul(x, 11) for x in range(256)]
_MUL13 = [_gmul(x, 13) for x in range(256)]
_MUL14 = [_gmul(x, 14) for x in range(256)]


class AES:
    """Cifra de bloco AES (chaves de 16, 24 ou 32 bytes)."""

    def __init__(self, key: bytes) -> None:
        if len(key) not in (16, 24, 32):
            raise ValueError("A chave AES deve ter 16, 24 ou 32 bytes")
        self._rounds = {16: 10, 24: 12, 32: 14}[len(key)]
        self._round_keys = self._expand(key)

    def _expand(self, key: bytes) -> list[list[int]]:
        nk = len(key) // 4
        words = [list(key[4 * i : 4 * i + 4]) for i in range(nk)]
        rcon = 1
        for i in range(nk, 4 * (self._rounds + 1)):
            temp = list(words[i - 1])
            if i % nk == 0:
                temp = temp[1:] + temp[:1]
                temp = [_SBOX[b] for b in temp]
                temp[0] ^= rcon
                rcon = _xtime(rcon)
            elif nk > 6 and i % nk == 4:
                temp = [_SBOX[b] for b in temp]
            words.append([a ^ b for a, b in zip(words[i - nk], temp)])
        return [sum(words[4 * r : 4 * r + 4], []) for r in range(self._rounds + 1)]

    def encrypt_block(self, block: bytes) -> bytes:
        s = [b ^ k for b, k in zip(block, self._round_keys[0])]
        for rnd in range(1, self._rounds + 1):
            s = [_SBOX[b] for b in s]
            # ShiftRows (estado em ordem de colunas: índice = 4*coluna + linha)
            s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]
            if rnd != self._rounds:
                mixed = []
                for c in range(4):
                    a0, a1, a2, a3 = s[4 * c : 4 * c + 4]
                    mixed += [
                        _MUL2[a0] ^ _MUL3[a1] ^ a2 ^ a3,
                        a0 ^ _MUL2[a1] ^ _MUL3[a2] ^ a3,
                        a0 ^ a1 ^ _MUL2[a2] ^ _MUL3[a3],
                        _MUL3[a0] ^ a1 ^ a2 ^ _MUL2[a3],
                    ]
                s = mixed
            s = [b ^ k for b, k in zip(s, self._round_keys[rnd])]
        return bytes(s)

    def decrypt_block(self, block: bytes) -> bytes:
        s = [b ^ k for b, k in zip(block, self._round_keys[self._rounds])]
        for rnd in range(self._rounds - 1, -1, -1):
            s = [s[(i - 4 * (i % 4)) % 16] for i in range(16)]
            s = [_INV_SBOX[b] for b in s]
            s = [b ^ k for b, k in zip(s, self._round_keys[rnd])]
            if rnd != 0:
                mixed = []
                for c in range(4):
                    a0, a1, a2, a3 = s[4 * c : 4 * c + 4]
                    mixed += [
                        _MUL14[a0] ^ _MUL11[a1] ^ _MUL13[a2] ^ _MUL9[a3],
                        _MUL9[a0] ^ _MUL14[a1] ^ _MUL11[a2] ^ _MUL13[a3],
                        _MUL13[a0] ^ _MUL9[a1] ^ _MUL14[a2] ^ _MUL11[a3],
                        _MUL11[a0] ^ _MUL13[a1] ^ _MUL9[a2] ^ _MUL14[a3],
                    ]
                s = mixed
        return bytes(s)


# ---------------------------------------------------------------- ECB


def ecb_encrypt(key: bytes, data: bytes) -> bytes:
    """AES-ECB com preenchimento PKCS#7."""
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad
    cipher = AES(key)
    return b"".join(cipher.encrypt_block(data[i : i + 16]) for i in range(0, len(data), 16))


def ecb_decrypt(key: bytes, data: bytes) -> bytes:
    """AES-ECB sem remover o preenchimento (quem chama decide como limpar)."""
    if len(data) % 16:
        raise ValueError("Tamanho inválido para AES-ECB")
    cipher = AES(key)
    return b"".join(cipher.decrypt_block(data[i : i + 16]) for i in range(0, len(data), 16))


# ---------------------------------------------------------------- GCM

_R = 0xE1 << 120


def _gf_mult(x: int, y: int) -> int:
    z = 0
    v = y
    for i in range(127, -1, -1):
        if (x >> i) & 1:
            z ^= v
        v = (v >> 1) ^ _R if v & 1 else v >> 1
    return z


def _ghash(h: int, aad: bytes, ct: bytes) -> int:
    def blocks(data: bytes):
        for i in range(0, len(data), 16):
            yield data[i : i + 16].ljust(16, b"\0")

    y = 0
    for blk in list(blocks(aad)) + list(blocks(ct)):
        y = _gf_mult(y ^ int.from_bytes(blk, "big"), h)
    lengths = (len(aad) * 8).to_bytes(8, "big") + (len(ct) * 8).to_bytes(8, "big")
    return _gf_mult(y ^ int.from_bytes(lengths, "big"), h)


def _gcm_ctr(cipher: AES, j0: bytes, data: bytes) -> bytes:
    out = bytearray()
    counter = int.from_bytes(j0[12:], "big")
    for i in range(0, len(data), 16):
        counter = (counter + 1) & 0xFFFFFFFF
        stream = cipher.encrypt_block(j0[:12] + counter.to_bytes(4, "big"))
        out += bytes(a ^ b for a, b in zip(data[i : i + 16], stream))
    return bytes(out)


def _gcm_setup(key: bytes, nonce: bytes) -> tuple[AES, int, bytes]:
    if len(nonce) != 12:
        raise ValueError("Esta implementação de GCM aceita apenas nonce de 12 bytes")
    cipher = AES(key)
    h = int.from_bytes(cipher.encrypt_block(b"\0" * 16), "big")
    j0 = nonce + b"\0\0\0\1"
    return cipher, h, j0


def gcm_encrypt(key: bytes, nonce: bytes, data: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
    """Retorna (texto_cifrado, tag de 16 bytes)."""
    cipher, h, j0 = _gcm_setup(key, nonce)
    ct = _gcm_ctr(cipher, j0, data)
    s = _ghash(h, aad, ct)
    tag = (s ^ int.from_bytes(cipher.encrypt_block(j0), "big")).to_bytes(16, "big")
    return ct, tag


def gcm_decrypt(key: bytes, nonce: bytes, data: bytes, aad: bytes = b"", tag: bytes | None = None) -> bytes:
    """Decifra; se `tag` for informada, ela é conferida."""
    cipher, h, j0 = _gcm_setup(key, nonce)
    if tag is not None:
        s = _ghash(h, aad, data)
        expected = (s ^ int.from_bytes(cipher.encrypt_block(j0), "big")).to_bytes(16, "big")
        if expected != tag:
            raise ValueError("Tag GCM inválida")
    return _gcm_ctr(cipher, j0, data)
