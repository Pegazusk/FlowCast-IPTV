import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TipoResena = Literal["en_vivo", "pelicula", "serie"]


class SolicitudResena(BaseModel):
    conexion_id: uuid.UUID
    tipo_contenido: TipoResena
    stream_id: str = Field(min_length=1, max_length=100)
    titulo: str = Field(min_length=1, max_length=500)
    calificacion: int = Field(ge=1, le=5, description="Estrellas, de 1 a 5")
    texto: str | None = Field(default=None, max_length=2000)


class RespuestaResena(BaseModel):
    id: int
    tipo_contenido: TipoResena
    stream_id: str
    titulo: str
    autor: str
    avatar: str
    calificacion: int
    texto: str | None
    actualizado_en: datetime
    es_mia: bool


class ResumenResenas(BaseModel):
    promedio: float | None
    total: int
    distribucion: dict[int, int]
    mia: RespuestaResena | None
    resenas: list[RespuestaResena]
