from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Esquema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Categoria(_Esquema):
    id: str
    nombre: str
    total: int | None = None
    padre_id: str | None
    es_adulta: bool = False
    bloqueada: bool = False


class Canal(_Esquema):
    id: str
    nombre: str
    icono: str | None
    categoria_id: str | None
    numero: int | None
    epg_id: str | None
    dias_catchup: int
    bloqueada: bool = False


class Version(_Esquema):
    id: str
    idioma: str
    calidad: str | None = None


class Pelicula(_Esquema):
    id: str
    nombre: str
    portada: str | None
    categoria_id: str | None
    calificacion: float | None
    extension: str | None
    agregado_en: datetime | None
    bloqueada: bool = False
    titulo: str | None = None
    anio: int | None = None
    idioma: str | None = None
    versiones: list[Version] = []


class FichaPelicula(_Esquema):
    pelicula: Pelicula
    sinopsis: str | None
    genero: str | None
    director: str | None
    reparto: str | None
    fecha_estreno: str | None
    duracion_segundos: int | None
    portada_grande: str | None
    fondo: str | None
    trailer_youtube: str | None
    tmdb_id: str | None
    clasificacion: str | None = None


class Serie(_Esquema):
    id: str
    nombre: str
    portada: str | None
    categoria_id: str | None
    calificacion: float | None
    sinopsis: str | None
    genero: str | None
    fecha_estreno: str | None
    fondo: str | None = None
    bloqueada: bool = False
    titulo: str | None = None
    anio: int | None = None
    idioma: str | None = None
    versiones: list[Version] = []


class Episodio(_Esquema):
    id: str
    temporada: int
    numero: int
    titulo: str
    extension: str | None
    imagen: str | None
    sinopsis: str | None
    duracion_segundos: int | None


class Temporada(_Esquema):
    numero: int
    nombre: str | None
    portada: str | None
    episodios: list[Episodio]


class FichaSerie(_Esquema):
    serie: Serie
    director: str | None
    reparto: str | None
    fondo: str | None
    trailer_youtube: str | None
    temporadas: list[Temporada]
    clasificacion: str | None = None


class ProgramaEpg(_Esquema):
    titulo: str
    descripcion: str | None
    inicio: datetime
    fin: datetime
    en_emision: bool


class ResultadoBusqueda(_Esquema):
    canales: list[Canal]
    peliculas: list[Pelicula]
    series: list[Serie]
    total_canales: int = 0
    total_peliculas: int = 0
    total_series: int = 0


class Destacados(_Esquema):
    peliculas: list[Pelicula]
    series: list[Serie]


class Actor(_Esquema):
    nombre: str
    personaje: str | None
    foto: str | None


class Elenco(_Esquema):
    actores: list[Actor]
    fuente: str


class CreditosSerie(BaseModel):
    segundos: float | None = Field(default=None, ge=10, le=900)
