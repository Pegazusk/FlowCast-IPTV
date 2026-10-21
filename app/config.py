from pathlib import Path

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

ARCHIVO_ENV = Path(__file__).resolve().parent.parent / ".env"


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ARCHIVO_ENV, env_file_encoding="utf-8", extra="ignore"
    )

    url_base_datos: PostgresDsn
    clave_secreta: str = Field(min_length=32)
    clave_cifrado: str = Field(min_length=44, max_length=44)
    minutos_token_acceso: int = 15
    dias_token_refresco: int = 30
    registro_abierto: bool = False
    precalentar_catalogo: bool = False
    confiar_proxy: bool = False
    conexion_inicial_etiqueta: str | None = None
    conexion_inicial_url: str | None = None
    conexion_inicial_usuario: str | None = None
    conexion_inicial_contrasena: str | None = None
    musica_carpeta: str | None = None
    tmdb_clave_api: str | None = None
    nombre_app: str = "FlowCast API"
    depuracion: bool = False
    documentacion_publica: bool = False
    origenes_permitidos: str = ""

    @property
    def lista_origenes(self) -> list[str]:
        return [
            origen.strip().rstrip("/")
            for origen in self.origenes_permitidos.split(",")
            if origen.strip()
        ]


configuracion = Configuracion()
