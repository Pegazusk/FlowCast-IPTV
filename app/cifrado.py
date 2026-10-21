import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import configuracion

_fernet = Fernet(configuracion.clave_cifrado)


def cifrar(texto: str) -> bytes:
    return _fernet.encrypt(texto.encode())


def descifrar(datos: bytes) -> str:
    try:
        return _fernet.decrypt(datos).decode()
    except InvalidToken as error:
        raise ValueError("Datos cifrados inválidos o clave de cifrado incorrecta") from error


def calcular_huella(url_base: str, nombre_usuario: str) -> str:
    return hashlib.sha256(f"{url_base}\n{nombre_usuario}".encode()).hexdigest()
