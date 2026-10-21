import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PIN = Field(default=None, pattern=r"^\d{4}$", description="PIN parental de 4 dígitos")


PantallaInicial = Literal["inicio", "en-vivo", "peliculas", "series", "mi-lista", "seguir"]


class Preferencias(BaseModel):
    letra_grande: bool = False
    pantalla_inicial: PantallaInicial = "inicio"


class SolicitudCrearPerfil(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    avatar: str = Field(default="01", max_length=40)
    es_infantil: bool = False
    pin: str | None = PIN


class SolicitudActualizarPerfil(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=80)
    avatar: str | None = Field(default=None, max_length=40)
    es_infantil: bool | None = None
    pin: str | None = PIN
    quitar_pin: bool = False
    preferencias: Preferencias | None = None


class SolicitudVerificarPin(BaseModel):
    pin: str = Field(pattern=r"^\d{4}$")


class RespuestaPerfil(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    avatar: str
    es_infantil: bool
    tiene_pin: bool
    url_imagen: str | None = None
    preferencias: Preferencias = Preferencias()
    creado_en: datetime
