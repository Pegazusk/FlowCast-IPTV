import re
import time
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import configuracion
from app.security import ALGORITMO

MINUTOS_DESBLOQUEO = 15
MAXIMO_INTENTOS = 5
SEGUNDOS_CASTIGO = 60

_PATRON_ADULTO = re.compile(
    r"(?<![A-Z0-9])(XXX|ADULT[OA]?S?|PORN[A-Z]*|EROT[A-Z]*|ONLY ?FANS|SOLO ADULTOS)(?![A-Z0-9])"
    r"|\+ ?18(?!\d)|(?<!\d)18 ?\+"
)
_intentos_fallidos: dict[uuid.UUID, list[float]] = {}


def _normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).upper()


def es_nombre_adulto(nombre: str | None) -> bool:
    if not nombre:
        return False
    return _PATRON_ADULTO.search(_normalizar(nombre)) is not None


def crear_token_desbloqueo(usuario_id: uuid.UUID) -> str:
    ahora = datetime.now(UTC)
    contenido = {
        "sub": str(usuario_id),
        "iat": ahora,
        "exp": ahora + timedelta(minutes=MINUTOS_DESBLOQUEO),
        "type": "desbloqueo",
    }
    return jwt.encode(contenido, configuracion.clave_secreta, algorithm=ALGORITMO)


def token_desbloqueo_valido(token: str | None, usuario_id: uuid.UUID) -> bool:
    if not token:
        return False
    try:
        contenido = jwt.decode(
            token,
            configuracion.clave_secreta,
            algorithms=[ALGORITMO],
            options={"require": ["sub", "exp"]},
        )
    except jwt.InvalidTokenError:
        return False
    return contenido.get("type") == "desbloqueo" and contenido.get("sub") == str(usuario_id)


def segundos_de_castigo(usuario_id: uuid.UUID) -> int:
    ahora = time.monotonic()
    recientes = [t for t in _intentos_fallidos.get(usuario_id, []) if ahora - t < SEGUNDOS_CASTIGO]
    _intentos_fallidos[usuario_id] = recientes
    if len(recientes) < MAXIMO_INTENTOS:
        return 0
    return int(SEGUNDOS_CASTIGO - (ahora - recientes[0])) + 1


def registrar_intento(usuario_id: uuid.UUID, exito: bool) -> None:
    if exito:
        _intentos_fallidos.pop(usuario_id, None)
    else:
        _intentos_fallidos.setdefault(usuario_id, []).append(time.monotonic())


def olvidar_intentos() -> None:
    _intentos_fallidos.clear()
