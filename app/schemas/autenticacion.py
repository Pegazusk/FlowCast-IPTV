import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

PATRON_NOMBRE_USUARIO = r"^[a-z0-9._-]{3,40}$"
MAXIMO_DATOS_DISPOSITIVO = 25
ValorDispositivo = str | int | float | bool | None


def limpiar_dispositivo(valor: Any) -> dict[str, ValorDispositivo] | None:
    if not isinstance(valor, dict):
        return None
    limpio: dict[str, ValorDispositivo] = {}
    for clave, dato in list(valor.items())[:MAXIMO_DATOS_DISPOSITIVO]:
        if isinstance(dato, str):
            dato = dato[:200]
        elif not isinstance(dato, int | float | bool) and dato is not None:
            dato = str(dato)[:200]
        limpio[str(clave)[:40]] = dato
    return limpio


class SolicitudRegistro(BaseModel):
    correo: EmailStr
    contrasena: str = Field(min_length=8, max_length=128)
    nombre: str = Field(min_length=2, max_length=120)
    nombre_usuario: str | None = Field(default=None, pattern=PATRON_NOMBRE_USUARIO)
    nombre_dispositivo: str | None = Field(default=None, max_length=120)

    @field_validator("nombre_usuario", mode="before")
    @classmethod
    def _minusculas(cls, valor: str | None) -> str | None:
        return valor.strip().lower() if isinstance(valor, str) else valor


class SolicitudInicioSesion(BaseModel):
    usuario: str | None = Field(default=None, min_length=1, max_length=320)
    correo: str | None = Field(default=None, min_length=1, max_length=320)
    contrasena: str = Field(min_length=1, max_length=128)
    nombre_dispositivo: str | None = Field(default=None, max_length=120)
    dispositivo: dict[str, ValorDispositivo] | None = None

    @field_validator("dispositivo", mode="before")
    @classmethod
    def _dispositivo(cls, valor: Any) -> dict[str, ValorDispositivo] | None:
        return limpiar_dispositivo(valor)

    @model_validator(mode="after")
    def _requiere_usuario_o_correo(self) -> "SolicitudInicioSesion":
        if not (self.usuario or self.correo):
            raise ValueError("Escribe tu usuario o tu correo")
        return self

    @property
    def identificador(self) -> str:
        return (self.usuario or self.correo or "").strip().lower()


class SolicitudRefresco(BaseModel):
    token_refresco: str = Field(min_length=64, max_length=64)
    dispositivo: dict[str, ValorDispositivo] | None = None

    @field_validator("dispositivo", mode="before")
    @classmethod
    def _dispositivo(cls, valor: Any) -> dict[str, ValorDispositivo] | None:
        return limpiar_dispositivo(valor)


class RespuestaUsuario(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    correo: EmailStr
    nombre: str
    nombre_usuario: str | None
    es_administrador: bool
    creado_en: datetime


class RespuestaTokens(BaseModel):
    token_acceso: str
    token_refresco: str
    tipo_token: str = "bearer"
    expira_en_segundos: int
    usuario: RespuestaUsuario
