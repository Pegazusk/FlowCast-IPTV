import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.xtream import normalizar_url_base


class SolicitudCrearConexion(BaseModel):
    etiqueta: str | None = Field(default=None, max_length=120)
    url_base: str = Field(min_length=3, max_length=500)
    nombre_usuario: str = Field(min_length=1, max_length=200)
    contrasena: str = Field(min_length=1, max_length=200)

    @field_validator("url_base")
    @classmethod
    def _normalizar_url(cls, valor: str) -> str:
        return normalizar_url_base(valor)


class RespuestaConexion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    etiqueta: str
    url_base: str
    nombre_usuario: str
    estado_cuenta: str
    expira_en: datetime | None
    max_conexiones: int | None
    zona_horaria_servidor: str | None
    formatos_salida_permitidos: list[str] | None
    ultima_autenticacion_en: datetime | None
    creado_en: datetime
