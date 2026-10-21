import uuid
from typing import Literal

from pydantic import BaseModel, Field

PIN = Field(pattern=r"^\d{4}$", description="PIN de 4 dígitos")
TipoCategoria = Literal["en_vivo", "pelicula", "serie"]


class EstadoControlParental(BaseModel):
    tiene_pin: bool


class SolicitudPin(BaseModel):
    pin_nuevo: str = PIN
    pin_actual: str | None = None
    contrasena: str | None = None


class SolicitudQuitarPin(BaseModel):
    pin_actual: str | None = None
    contrasena: str | None = None


class SolicitudVerificarPin(BaseModel):
    pin: str = PIN


class RespuestaVerificarPin(BaseModel):
    valido: bool
    token_desbloqueo: str | None = None
    segundos_validez: int = 0


class CategoriaControl(BaseModel):
    tipo_contenido: TipoCategoria
    id: str
    nombre: str
    es_adulta: bool
    bloqueada: bool


class SolicitudBloqueoCategoria(BaseModel):
    conexion_id: uuid.UUID
    tipo_contenido: TipoCategoria
    categoria_id: str = Field(min_length=1, max_length=100)
    bloqueada: bool


class RespuestaBloqueoCategoria(BaseModel):
    tipo_contenido: TipoCategoria
    categoria_id: str
    bloqueada: bool
