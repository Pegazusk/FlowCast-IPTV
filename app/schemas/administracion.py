import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.autenticacion import PATRON_NOMBRE_USUARIO
from app.services import xtream


def correo_interno(nombre_usuario: str) -> str:
    return f"{nombre_usuario}@usuarios.flowcast"


class SolicitudProveedor(BaseModel):
    predeterminado: bool = True
    cuenta_id: uuid.UUID | None = None
    url_base: str | None = Field(default=None, max_length=500)
    nombre_usuario: str | None = Field(default=None, max_length=200)
    contrasena: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _datos_completos(self) -> "SolicitudProveedor":
        if self.cuenta_id is not None:
            self.predeterminado = False
            return self
        if not self.predeterminado:
            if not (self.url_base and self.nombre_usuario and self.contrasena):
                raise ValueError("Escribe la URL, el usuario y la contraseña del proveedor")
            self.url_base = xtream.normalizar_url_base(self.url_base)
        return self


class SolicitudCrearUsuario(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    nombre_usuario: str = Field(pattern=PATRON_NOMBRE_USUARIO)
    contrasena: str = Field(min_length=8, max_length=128)
    correo: EmailStr | None = None
    es_administrador: bool = False
    proveedor: SolicitudProveedor = SolicitudProveedor()

    @field_validator("nombre_usuario", mode="before")
    @classmethod
    def _minusculas(cls, valor: str) -> str:
        return valor.strip().lower() if isinstance(valor, str) else valor

    @field_validator("correo", mode="before")
    @classmethod
    def _vacio_es_nulo(cls, valor: str | None) -> str | None:
        return (valor.strip() or None) if isinstance(valor, str) else valor


class SolicitudActualizarUsuario(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    nombre_usuario: str | None = Field(default=None, pattern=PATRON_NOMBRE_USUARIO)
    activo: bool | None = None
    es_administrador: bool | None = None
    contrasena: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("nombre_usuario", mode="before")
    @classmethod
    def _minusculas(cls, valor: str | None) -> str | None:
        return valor.strip().lower() if isinstance(valor, str) else valor


class RespuestaProveedor(BaseModel):
    id: uuid.UUID
    cuenta_id: uuid.UUID | None = None
    etiqueta: str
    servidor: str
    nombre_usuario: str
    estado_cuenta: str
    expira_en: datetime | None
    max_conexiones: int | None


class RespuestaUsuarioAdministrado(BaseModel):
    id: uuid.UUID
    nombre: str
    nombre_usuario: str | None
    correo: str
    activo: bool
    es_administrador: bool
    creado_en: datetime
    sesiones_activas: int
    proveedores: list[RespuestaProveedor]


class RespuestaSesionesCerradas(BaseModel):
    cerradas: int


class RespuestaSesionDispositivo(BaseModel):
    id: uuid.UUID
    nombre_dispositivo: str | None
    dispositivo: dict[str, Any]
    ip_inicio: str | None
    ip_ultima: str | None
    agente_usuario: str | None
    iniciada_en: datetime
    ultimo_uso_en: datetime
    expira_en: datetime


class SolicitudCuentaProveedor(BaseModel):
    etiqueta: str = Field(min_length=1, max_length=120)
    url_base: str = Field(min_length=3, max_length=500)
    nombre_usuario: str = Field(min_length=1, max_length=200)
    contrasena: str = Field(min_length=1, max_length=200)
    notas: str | None = Field(default=None, max_length=2000)
    predeterminada: bool = False
    validar: bool = True

    @field_validator("url_base")
    @classmethod
    def _url(cls, valor: str) -> str:
        return xtream.normalizar_url_base(valor)


class SolicitudActualizarCuentaProveedor(BaseModel):
    etiqueta: str | None = Field(default=None, min_length=1, max_length=120)
    url_base: str | None = Field(default=None, min_length=3, max_length=500)
    nombre_usuario: str | None = Field(default=None, min_length=1, max_length=200)
    contrasena: str | None = Field(default=None, max_length=200)
    notas: str | None = Field(default=None, max_length=2000)
    predeterminada: bool | None = None
    validar: bool = True

    @field_validator("url_base")
    @classmethod
    def _url(cls, valor: str | None) -> str | None:
        return xtream.normalizar_url_base(valor) if valor else valor

    @field_validator("contrasena")
    @classmethod
    def _vacia_es_nula(cls, valor: str | None) -> str | None:
        return valor or None


class RespuestaCuentaProveedor(BaseModel):
    id: uuid.UUID
    etiqueta: str
    url_base: str
    servidor: str
    nombre_usuario: str
    notas: str | None
    predeterminada: bool
    estado_cuenta: str
    expira_en: datetime | None
    max_conexiones: int | None
    conexiones_activas: int | None
    ultima_revision_en: datetime | None
    usuarios: list[str]
