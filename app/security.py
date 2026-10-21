import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import configuracion

_hasheador = PasswordHasher()


def generar_hash_contrasena(contrasena: str) -> str:
    return _hasheador.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_contrasena: str) -> bool:
    try:
        return _hasheador.verify(hash_contrasena, contrasena)
    except (VerifyMismatchError, InvalidHashError):
        return False


ALGORITMO = "HS256"


def crear_token_acceso(usuario_id: uuid.UUID) -> str:
    ahora = datetime.now(UTC)
    contenido = {
        "sub": str(usuario_id),
        "iat": ahora,
        "exp": ahora + timedelta(minutes=configuracion.minutos_token_acceso),
        "type": "access",
    }
    return jwt.encode(contenido, configuracion.clave_secreta, algorithm=ALGORITMO)


def decodificar_token_acceso(token: str) -> uuid.UUID:
    contenido = jwt.decode(
        token,
        configuracion.clave_secreta,
        algorithms=[ALGORITMO],
        options={"require": ["sub", "exp"]},
    )
    if contenido.get("type") != "access":
        raise jwt.InvalidTokenError("no es un token de acceso")
    try:
        return uuid.UUID(contenido["sub"])
    except ValueError as error:
        raise jwt.InvalidTokenError("sub no es un uuid") from error


def generar_token_refresco() -> str:
    return secrets.token_hex(32)


def calcular_hash_token_refresco(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def caducidad_token_refresco() -> datetime:
    return datetime.now(UTC) + timedelta(days=configuracion.dias_token_refresco)
