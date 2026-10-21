from pydantic import BaseModel


class Cancion(BaseModel):
    id: str
    titulo: str
    artista: str
    album: str
    album_id: str
    numero_pista: int | None
    duracion_segundos: float | None
    anio: int | None
    genero: str | None
    url_audio: str
    url_portada: str | None


class Album(BaseModel):
    id: str
    titulo: str
    artista: str
    anio: int | None
    total_canciones: int
    duracion_segundos: float
    url_portada: str | None


class AlbumConCanciones(BaseModel):
    album: Album
    canciones: list[Cancion]


class ResumenMusica(BaseModel):
    carpeta_configurada: bool
    total_canciones: int
    total_albumes: int
    escaneado_en: float
