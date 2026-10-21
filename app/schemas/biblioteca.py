import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TipoFavorito = Literal["en_vivo", "pelicula", "serie"]
TipoProgreso = Literal["pelicula", "episodio"]
TipoHistorial = Literal["en_vivo", "pelicula", "episodio"]


class _Contenido(BaseModel):
    conexion_id: uuid.UUID
    stream_id: str = Field(min_length=1, max_length=100)
    titulo: str = Field(min_length=1, max_length=500)
    url_portada: str | None = Field(default=None, max_length=1000)


class SolicitudFavorito(_Contenido):
    tipo_contenido: TipoFavorito


class RespuestaFavorito(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conexion_id: uuid.UUID
    tipo_contenido: TipoFavorito
    stream_id: str
    titulo: str
    url_portada: str | None
    creado_en: datetime


class SolicitudProgreso(_Contenido):
    tipo_contenido: TipoProgreso
    serie_id: str | None = Field(default=None, max_length=100)
    posicion_segundos: float = Field(ge=0)
    duracion_segundos: float | None = Field(default=None, gt=0)
    completado: bool | None = None

    @model_validator(mode="after")
    def _episodio_requiere_serie(self) -> "SolicitudProgreso":
        if self.tipo_contenido == "episodio" and not self.serie_id:
            raise ValueError("un episodio necesita serie_id")
        if self.duracion_segundos is not None and self.posicion_segundos > self.duracion_segundos:
            raise ValueError("posicion_segundos no puede superar duracion_segundos")
        return self


class RespuestaProgreso(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conexion_id: uuid.UUID
    tipo_contenido: TipoProgreso
    stream_id: str
    serie_id: str | None
    titulo: str
    url_portada: str | None
    posicion_segundos: float
    duracion_segundos: float | None
    completado: bool
    actualizado_en: datetime


class SolicitudHistorial(_Contenido):
    tipo_contenido: TipoHistorial


class RespuestaHistorial(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conexion_id: uuid.UUID
    tipo_contenido: TipoHistorial
    stream_id: str
    titulo: str
    url_portada: str | None
    reproducido_en: datetime


class PistasSerie(BaseModel):
    audio: str | None = Field(default=None, max_length=40)
    subtitulos: str | None = Field(default=None, max_length=40)
