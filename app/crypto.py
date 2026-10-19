import base64
import os
import secrets
from typing import Dict, Optional

try:
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def generate_preshared_key() -> str:
    """Generate a random 32-byte WireGuard Pre-shared Key (base64 encoded)."""
    random_bytes = secrets.token_bytes(32)
    return base64.b64encode(random_bytes).decode('utf-8')


def generate_keypair() -> Dict[str, str]:
    """
    Generate a standard WireGuard Curve25519 keypair.
    Returns:
        dict: {"private_key": "<base64>", "public_key": "<base64>"}
    """
    if HAS_CRYPTOGRAPHY:
        private_key = x25519.X25519PrivateKey.generate()
        public_key = private_key.public_key()

        priv_raw = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        pub_raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

        return {
            "private_key": base64.b64encode(priv_raw).decode('utf-8'),
            "public_key": base64.b64encode(pub_raw).decode('utf-8')
        }
    else:
        # Fallback pure python X25519 implementation
        priv_bytes = bytearray(secrets.token_bytes(32))
        priv_bytes[0] &= 248
        priv_bytes[31] &= 127
        priv_bytes[31] |= 64
        pub_bytes = _curve25519_base(bytes(priv_bytes))
        return {
            "private_key": base64.b64encode(bytes(priv_bytes)).decode('utf-8'),
            "public_key": base64.b64encode(pub_bytes).decode('utf-8')
        }


def derive_public_key(private_key_b64: str) -> str:
    """
    Derive the WireGuard public key from a base64 encoded private key.
    """
    cleaned_key = private_key_b64.strip()
    try:
        raw_priv = base64.b64decode(cleaned_key)
        if len(raw_priv) != 32:
            raise ValueError(f"WireGuard private key must be 32 bytes, got {len(raw_priv)}")

        if HAS_CRYPTOGRAPHY:
            priv_obj = x25519.X25519PrivateKey.from_private_bytes(raw_priv)
            pub_raw = priv_obj.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            return base64.b64encode(pub_raw).decode('utf-8')
        else:
            pub_raw = _curve25519_base(raw_priv)
            return base64.b64encode(pub_raw).decode('utf-8')
    except Exception as e:
        raise ValueError(f"Invalid private key format: {str(e)}")


def validate_key(key_b64: str) -> bool:
    """Check if the string is a valid 32-byte base64 encoded key."""
    try:
        raw = base64.b64decode(key_b64.strip())
        return len(raw) == 32
    except Exception:
        return False


# Pure Python Curve25519 implementation for emergency fallback
P = 2**255 - 19
A24 = 121665

def _curve25519_cswap(swap: int, x_2: int, x_3: int):
    dummy = swap * ((x_2 ^ x_3) % P)
    x_2 ^= dummy
    x_3 ^= dummy
    return x_2, x_3

def _curve25519_scalar_mult(scalar_bytes: bytes, u_bytes: bytes) -> bytes:
    a = int.from_bytes(scalar_bytes, 'little')
    a &= ~7
    a &= ~(128 << 248)
    a |= 64 << 248

    u = int.from_bytes(u_bytes, 'little') % P

    x_1 = u
    x_2 = 1
    z_2 = 0
    x_3 = u
    z_3 = 1
    swap = 0

    for t in range(254, -1, -1):
        k_t = (a >> t) & 1
        swap ^= k_t
        x_2, x_3 = _curve25519_cswap(swap, x_2, x_3)
        z_2, z_3 = _curve25519_cswap(swap, z_2, z_3)
        swap = k_t

        A = (x_2 + z_2) % P
        AA = (A * A) % P
        B = (x_2 - z_2) % P
        BB = (B * B) % P
        E = (AA - BB) % P
        C = (x_3 + z_3) % P
        D = (x_3 - z_3) % P
        DA = (D * A) % P
        CB = (C * B) % P
        x_3 = ((DA + CB) ** 2) % P
        z_3 = (x_1 * ((DA - CB) ** 2)) % P
        x_2 = (AA * BB) % P
        z_2 = (E * ((AA + A24 * E) % P)) % P

    x_2, x_3 = _curve25519_cswap(swap, x_2, x_3)
    z_2, z_3 = _curve25519_cswap(swap, z_2, z_3)

    result = (x_2 * pow(z_2, P - 2, P)) % P
    return result.to_bytes(32, 'little')

def _curve25519_base(scalar_bytes: bytes) -> bytes:
    base_point = (9).to_bytes(32, 'little')
    return _curve25519_scalar_mult(scalar_bytes, base_point)
