import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

logger = logging.getLogger("yieldpadel.security")

try:
    import jwt
except ImportError:
    try:
        from jose import jwt
    except ImportError:
        jwt = None
        logger.warning("No JWT library available (neither pyjwt nor python-jose). Safe cryptographic fallbacks enabled.")

SECRET_KEY = os.getenv("SECRET_KEY", "yieldpadel_super_secure_jwt_secret_key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def hash_password(password: str) -> str:
    try:
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return f"{salt}:{key.hex()}"
    except Exception as e:
        logger.error(f"Error in hash_password: {e}")
        salt = secrets.token_hex(8)
        h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return f"{salt}:{h}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if not hashed_password or ":" not in hashed_password:
            return False
        salt, key_hex = hashed_password.split(":")
        new_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return secrets.compare_digest(new_key.hex(), key_hex)
    except Exception as e:
        logger.warning(f"Error in verify_password: {e}")
        return False


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})

        if jwt is not None:
            token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
            if isinstance(token, bytes):
                token = token.decode("utf-8")
            return token
    except Exception as e:
        logger.error(f"Error encoding JWT token: {e}")

    # Cryptographic HMAC fallback if jwt library is unavailable or raises
    try:
        import base64
        import hmac

        header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
        safe_data = to_encode.copy()
        if isinstance(safe_data.get("exp"), datetime):
            safe_data["exp"] = int(safe_data["exp"].timestamp())
        payload = base64.urlsafe_b64encode(json.dumps(safe_data, separators=(",", ":")).encode()).decode().rstrip("=")
        sig = base64.urlsafe_b64encode(
            hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        return f"{header}.{payload}.{sig}"
    except Exception as err:
        logger.error(f"Fallback token creation failed: {err}")
        return secrets.token_urlsafe(32)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    if not token:
        return None

    if jwt is not None:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except Exception as e:
            logger.debug(f"jwt.decode failed: {e}")

    # Cryptographic HMAC fallback validation
    try:
        import base64
        import hmac

        parts = token.split(".")
        if len(parts) == 3:
            header_b64, payload_b64, sig_b64 = parts
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(SECRET_KEY.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
            ).decode().rstrip("=")
            if secrets.compare_digest(sig_b64, expected_sig):
                rem = len(payload_b64) % 4
                padded = payload_b64 + ("=" * (4 - rem) if rem else "")
                data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
                if "exp" in data:
                    exp_val = data["exp"]
                    if isinstance(exp_val, (int, float)) and datetime.now(timezone.utc).timestamp() > exp_val:
                        return None
                return data
    except Exception as err:
        logger.debug(f"Fallback token decode failed: {err}")

    return None
