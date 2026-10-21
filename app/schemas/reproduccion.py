from typing import Literal

from pydantic import BaseModel


class RespuestaReproduccion(BaseModel):
    url: str
    formato: str
    tipo_contenido: Literal["en_vivo", "pelicula", "episodio"]
    contenido_id: str
    user_agent: str = "FlowCast/0.1"
