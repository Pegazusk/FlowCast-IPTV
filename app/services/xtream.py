import base64
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx2 as httpx

from app.services import freno

TIEMPO_ESPERA_SEGUNDOS = 15.0
CABECERAS = {"User-Agent": "FlowCast/0.1"}

_ESTADOS = {
    "active": "activa",
    "expired": "expirada",
    "banned": "bloqueada",
    "disabled": "deshabilitada",
}


class ErrorXtream(Exception):
    pass


class CredencialesXtreamInvalidas(ErrorXtream):
    pass


class ProveedorNoDisponible(ErrorXtream):
    pass


@dataclass(frozen=True)
class InfoCuentaXtream:
    estado_cuenta: str
    expira_en: datetime | None
    max_conexiones: int | None
    conexiones_activas: int | None
    es_prueba: bool
    zona_horaria_servidor: str | None
    formatos_salida_permitidos: list[str]


def normalizar_url_base(url: str) -> str:
    url = url.strip()
    if url and "://" not in url:
        url = "http://" + url
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ValueError("La URL del servidor no es válida")
    return f"{partes.scheme}://{partes.netloc}"


async def validar_credenciales(
    url_base: str,
    nombre_usuario: str,
    contrasena: str,
    cliente: httpx.AsyncClient | None = None,
) -> InfoCuentaXtream:
    datos = await _llamar_player_api(url_base, nombre_usuario, contrasena, cliente=cliente)
    info_usuario = datos.get("user_info") if isinstance(datos, dict) else None
    if not isinstance(info_usuario, dict):
        raise ProveedorNoDisponible("La respuesta del proveedor no tiene el formato esperado")
    if str(info_usuario.get("auth")) != "1":
        raise CredencialesXtreamInvalidas("El proveedor rechazó el usuario o la contraseña")

    info_servidor = datos.get("server_info") or {}
    return InfoCuentaXtream(
        estado_cuenta=_ESTADOS.get(str(info_usuario.get("status", "")).lower(), "desconocido"),
        expira_en=_fecha_desde_unix(info_usuario.get("exp_date")),
        max_conexiones=_entero(info_usuario.get("max_connections")),
        conexiones_activas=_entero(info_usuario.get("active_cons")),
        es_prueba=str(info_usuario.get("is_trial")) == "1",
        zona_horaria_servidor=info_servidor.get("timezone") or None,
        formatos_salida_permitidos=[
            str(f) for f in info_usuario.get("allowed_output_formats") or []
        ],
    )


async def _llamar_player_api(
    url_base: str,
    nombre_usuario: str,
    contrasena: str,
    cliente: httpx.AsyncClient | None = None,
    **extra: str,
) -> Any:
    parametros = {"username": nombre_usuario, "password": contrasena, **extra}
    cliente_propio = cliente is None
    if cliente is None:
        cliente = httpx.AsyncClient(
            timeout=TIEMPO_ESPERA_SEGUNDOS, headers=CABECERAS, follow_redirects=True
        )
    try:
        async with freno.turno(url_base):
            respuesta = await cliente.get(f"{url_base}/player_api.php", params=parametros)
    except httpx.HTTPError as error:
        raise ProveedorNoDisponible(
            f"No se pudo conectar con el proveedor ({type(error).__name__})"
        ) from error
    finally:
        if cliente_propio:
            await cliente.aclose()

    if respuesta.status_code in (401, 403):
        raise CredencialesXtreamInvalidas("El proveedor rechazó el usuario o la contraseña")
    if respuesta.status_code != 200:
        raise ProveedorNoDisponible(f"El proveedor respondió HTTP {respuesta.status_code}")
    try:
        return respuesta.json()
    except ValueError as error:
        raise ProveedorNoDisponible("El proveedor no devolvió JSON") from error


def _fecha_desde_unix(valor: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(valor), tz=UTC)
    except (TypeError, ValueError):
        return None


def _entero(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


TipoContenido = Literal["en_vivo", "pelicula", "serie"]

_ACCION_CATEGORIAS = {
    "en_vivo": "get_live_categories",
    "pelicula": "get_vod_categories",
    "serie": "get_series_categories",
}


class ContenidoNoEncontrado(ErrorXtream):
    pass


@dataclass(frozen=True)
class CredencialesXtream:
    url_base: str
    nombre_usuario: str
    contrasena: str


@dataclass(frozen=True)
class Categoria:
    id: str
    nombre: str
    padre_id: str | None


@dataclass(frozen=True)
class Canal:
    id: str
    nombre: str
    icono: str | None
    categoria_id: str | None
    numero: int | None
    epg_id: str | None
    dias_catchup: int
    agregado_en: datetime | None = None


@dataclass(frozen=True)
class Pelicula:
    id: str
    nombre: str
    portada: str | None
    categoria_id: str | None
    calificacion: float | None
    extension: str | None
    agregado_en: datetime | None
    tmdb_id: str | None = None


@dataclass(frozen=True)
class FichaPelicula:
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


@dataclass(frozen=True)
class Serie:
    id: str
    nombre: str
    portada: str | None
    categoria_id: str | None
    calificacion: float | None
    sinopsis: str | None
    genero: str | None
    fecha_estreno: str | None
    fondo: str | None = None
    tmdb_id: str | None = None
    agregado_en: datetime | None = None


@dataclass(frozen=True)
class Episodio:
    id: str
    temporada: int
    numero: int
    titulo: str
    extension: str | None
    imagen: str | None
    sinopsis: str | None
    duracion_segundos: int | None


@dataclass(frozen=True)
class Temporada:
    numero: int
    nombre: str | None
    portada: str | None
    episodios: list[Episodio]


@dataclass(frozen=True)
class FichaSerie:
    serie: Serie
    director: str | None
    reparto: str | None
    fondo: str | None
    trailer_youtube: str | None
    temporadas: list[Temporada]


@dataclass(frozen=True)
class ProgramaEpg:
    titulo: str
    descripcion: str | None
    inicio: datetime
    fin: datetime
    en_emision: bool


async def obtener_categorias(
    credenciales: CredencialesXtream,
    tipo: TipoContenido,
    cliente: httpx.AsyncClient | None = None,
) -> list[Categoria]:
    datos = await _llamar_catalogo(credenciales, _ACCION_CATEGORIAS[tipo], cliente=cliente)
    return [
        Categoria(
            id=str(c.get("category_id")),
            nombre=_texto(c.get("category_name")) or "Sin nombre",
            padre_id=_id_opcional(c.get("parent_id")),
        )
        for c in _exigir_lista(datos)
    ]


async def obtener_canales(
    credenciales: CredencialesXtream,
    categoria_id: str | None = None,
    cliente: httpx.AsyncClient | None = None,
) -> list[Canal]:
    datos = await _llamar_catalogo(
        credenciales, "get_live_streams", cliente=cliente, **_filtro_categoria(categoria_id)
    )
    canales = []
    for c in _exigir_lista(datos):
        tiene_catchup = _entero(c.get("tv_archive")) == 1
        canales.append(
            Canal(
                id=str(c.get("stream_id")),
                nombre=_texto(c.get("name")) or "Sin nombre",
                icono=_texto(c.get("stream_icon")),
                categoria_id=_id_opcional(c.get("category_id")),
                numero=_entero(c.get("num")),
                epg_id=_texto(c.get("epg_channel_id")),
                dias_catchup=(_entero(c.get("tv_archive_duration")) or 0) if tiene_catchup else 0,
                agregado_en=_fecha_desde_unix(c.get("added")),
            )
        )
    return canales


async def obtener_peliculas(
    credenciales: CredencialesXtream,
    categoria_id: str | None = None,
    cliente: httpx.AsyncClient | None = None,
) -> list[Pelicula]:
    datos = await _llamar_catalogo(
        credenciales, "get_vod_streams", cliente=cliente, **_filtro_categoria(categoria_id)
    )
    return [_pelicula_desde(p) for p in _exigir_lista(datos)]


async def obtener_ficha_pelicula(
    credenciales: CredencialesXtream,
    pelicula_id: str,
    cliente: httpx.AsyncClient | None = None,
) -> FichaPelicula:
    datos = await _llamar_catalogo(
        credenciales, "get_vod_info", cliente=cliente, vod_id=pelicula_id
    )
    info = datos.get("info") if isinstance(datos, dict) else None
    datos_pelicula = datos.get("movie_data") if isinstance(datos, dict) else None
    if not isinstance(info, dict) or not isinstance(datos_pelicula, dict):
        raise ContenidoNoEncontrado("El proveedor no tiene esa película")
    pelicula = _pelicula_desde(
        {
            **datos_pelicula,
            "stream_icon": info.get("movie_image") or info.get("cover_big"),
            "rating": info.get("rating"),
        }
    )
    return FichaPelicula(
        pelicula=pelicula,
        sinopsis=_texto(info.get("plot") or info.get("description")),
        genero=_texto(info.get("genre")),
        director=_texto(info.get("director")),
        reparto=_texto(info.get("cast") or info.get("actors")),
        fecha_estreno=_texto(info.get("releasedate") or info.get("release_date")),
        duracion_segundos=_entero(info.get("duration_secs")),
        portada_grande=_texto(info.get("cover_big")),
        fondo=_primero(info.get("backdrop_path")),
        trailer_youtube=_texto(info.get("youtube_trailer")),
        tmdb_id=_texto(info.get("tmdb_id")),
    )


async def obtener_series(
    credenciales: CredencialesXtream,
    categoria_id: str | None = None,
    cliente: httpx.AsyncClient | None = None,
) -> list[Serie]:
    datos = await _llamar_catalogo(
        credenciales, "get_series", cliente=cliente, **_filtro_categoria(categoria_id)
    )
    return [_serie_desde(s, s.get("series_id")) for s in _exigir_lista(datos)]


async def obtener_ficha_serie(
    credenciales: CredencialesXtream,
    serie_id: str,
    cliente: httpx.AsyncClient | None = None,
) -> FichaSerie:
    datos = await _llamar_catalogo(
        credenciales, "get_series_info", cliente=cliente, series_id=serie_id
    )
    info = datos.get("info") if isinstance(datos, dict) else None
    if not isinstance(info, dict) or not info:
        raise ContenidoNoEncontrado("El proveedor no tiene esa serie")

    metadatos_temporada = {
        str(_entero(t.get("season_number"))): t
        for t in datos.get("seasons") or []
        if isinstance(t, dict)
    }
    temporadas = []
    for numero_texto, episodios_crudos in _iterar_temporadas(datos.get("episodes")):
        numero = _entero(numero_texto) or 0
        meta = metadatos_temporada.get(str(numero), {})
        temporadas.append(
            Temporada(
                numero=numero,
                nombre=_texto(meta.get("name")),
                portada=_texto(meta.get("cover") or meta.get("cover_big")),
                episodios=[
                    _episodio_desde(e, numero) for e in episodios_crudos if isinstance(e, dict)
                ],
            )
        )
    temporadas.sort(key=lambda t: t.numero)
    return FichaSerie(
        serie=_serie_desde(info, serie_id),
        director=_texto(info.get("director")),
        reparto=_texto(info.get("cast")),
        fondo=_primero(info.get("backdrop_path")),
        trailer_youtube=_texto(info.get("youtube_trailer")),
        temporadas=temporadas,
    )


async def obtener_epg(
    credenciales: CredencialesXtream,
    canal_id: str,
    limite: int = 10,
    cliente: httpx.AsyncClient | None = None,
) -> list[ProgramaEpg]:
    datos = await _llamar_catalogo(
        credenciales, "get_short_epg", cliente=cliente, stream_id=canal_id, limit=str(limite)
    )
    listado = datos.get("epg_listings") if isinstance(datos, dict) else None
    programas = []
    for p in listado or []:
        if not isinstance(p, dict):
            continue
        inicio = _fecha_desde_unix(p.get("start_timestamp"))
        fin = _fecha_desde_unix(p.get("stop_timestamp"))
        if inicio is None or fin is None:
            continue
        programas.append(
            ProgramaEpg(
                titulo=_texto_base64(p.get("title")) or "Sin título",
                descripcion=_descripcion_epg(p.get("description")),
                inicio=inicio,
                fin=fin,
                en_emision=str(p.get("now_playing")) == "1",
            )
        )
    return programas


async def _llamar_catalogo(
    credenciales: CredencialesXtream,
    accion: str,
    cliente: httpx.AsyncClient | None = None,
    **parametros: str,
) -> Any:
    datos = await _llamar_player_api(
        credenciales.url_base,
        credenciales.nombre_usuario,
        credenciales.contrasena,
        cliente=cliente,
        action=accion,
        **parametros,
    )
    info_usuario = datos.get("user_info") if isinstance(datos, dict) else None
    if isinstance(info_usuario, dict) and str(info_usuario.get("auth")) != "1":
        raise CredencialesXtreamInvalidas("El proveedor rechazó el usuario o la contraseña")
    return datos


def _pelicula_desde(p: dict[str, Any]) -> Pelicula:
    return Pelicula(
        id=str(p.get("stream_id")),
        nombre=_texto(p.get("name")) or "Sin nombre",
        portada=_texto(p.get("stream_icon")),
        categoria_id=_id_opcional(p.get("category_id")),
        calificacion=_flotante(p.get("rating")),
        extension=_texto(p.get("container_extension")),
        agregado_en=_fecha_desde_unix(p.get("added")),
        tmdb_id=_tmdb_id(p.get("tmdb_id")),
    )


def _serie_desde(s: dict[str, Any], serie_id: Any) -> Serie:
    return Serie(
        id=str(serie_id),
        nombre=_texto(s.get("name")) or "Sin nombre",
        portada=_texto(s.get("cover")),
        categoria_id=_id_opcional(s.get("category_id")),
        calificacion=_flotante(s.get("rating")),
        sinopsis=_texto(s.get("plot")),
        genero=_texto(s.get("genre")),
        fecha_estreno=_texto(s.get("releaseDate") or s.get("release_date")),
        fondo=_primero(s.get("backdrop_path")),
        tmdb_id=_tmdb_id(s.get("tmdb_id")),
        agregado_en=_fecha_desde_unix(s.get("last_modified")),
    )


def _episodio_desde(e: dict[str, Any], temporada: int) -> Episodio:
    info = e.get("info") if isinstance(e.get("info"), dict) else {}
    numero = _entero(e.get("episode_num")) or 0
    return Episodio(
        id=str(e.get("id")),
        temporada=_entero(e.get("season")) or temporada,
        numero=numero,
        titulo=_texto(e.get("title")) or f"Episodio {numero}",
        extension=_texto(e.get("container_extension")),
        imagen=_texto(info.get("movie_image")),
        sinopsis=_texto(info.get("plot")),
        duracion_segundos=_entero(info.get("duration_secs")),
    )


def _iterar_temporadas(episodios: Any) -> list[tuple[Any, list[Any]]]:
    if isinstance(episodios, dict):
        return [(numero, lista) for numero, lista in episodios.items() if isinstance(lista, list)]
    if isinstance(episodios, list):
        return [(i + 1, lista) for i, lista in enumerate(episodios) if isinstance(lista, list)]
    return []


def _exigir_lista(datos: Any) -> list[dict[str, Any]]:
    if not isinstance(datos, list):
        raise ProveedorNoDisponible("El proveedor no devolvió la lista esperada")
    return [elemento for elemento in datos if isinstance(elemento, dict)]


def _filtro_categoria(categoria_id: str | None) -> dict[str, str]:
    return {"category_id": categoria_id} if categoria_id else {}


def _tmdb_id(valor: Any) -> str | None:
    texto = _texto(valor)
    return texto if texto and texto.isdigit() and texto != "0" else None


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _id_opcional(valor: Any) -> str | None:
    texto = _texto(valor)
    return None if texto in (None, "0", "null") else texto


def _flotante(valor: Any) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _primero(valor: Any) -> str | None:
    if isinstance(valor, list):
        return _texto(valor[0]) if valor else None
    return _texto(valor)


_SIN_DESCRIPCION = {
    "no description info",
    "no description",
    "sin descripcion",
    "sin descripción",
    "n/a",
}


def _descripcion_epg(valor: Any) -> str | None:
    texto = _texto_base64(valor)
    return None if texto is None or texto.strip().lower() in _SIN_DESCRIPCION else texto


def _texto_base64(valor: Any) -> str | None:
    if not valor:
        return None
    try:
        return _texto(base64.b64decode(str(valor), validate=True).decode("utf-8", "replace"))
    except (ValueError, TypeError):
        return _texto(valor)


FormatoEnVivo = Literal["m3u8", "ts"]
_SEGMENTO_VALIDO = re.compile(r"^[A-Za-z0-9_-]+$")


def elegir_formato_en_vivo(
    formatos_permitidos: list[str] | None, preferido: str | None = None
) -> FormatoEnVivo:
    permitidos = {f.lower() for f in formatos_permitidos or []} & {"m3u8", "ts"}
    if preferido in ("m3u8", "ts") and (not permitidos or preferido in permitidos):
        return preferido
    if "m3u8" in permitidos or not permitidos:
        return "m3u8"
    return "ts"


def url_en_vivo(credenciales: CredencialesXtream, canal_id: str, formato: FormatoEnVivo) -> str:
    return f"{_ruta(credenciales, 'live')}/{_segmento(canal_id)}.{formato}"


def url_pelicula(credenciales: CredencialesXtream, pelicula_id: str, extension: str) -> str:
    return f"{_ruta(credenciales, 'movie')}/{_segmento(pelicula_id)}.{_segmento(extension)}"


def url_episodio(credenciales: CredencialesXtream, episodio_id: str, extension: str) -> str:
    return f"{_ruta(credenciales, 'series')}/{_segmento(episodio_id)}.{_segmento(extension)}"


def extension_por_firma(inicio: bytes) -> str | None:
    if inicio[:4] == b"\x1a\x45\xdf\xa3":
        return "mkv"
    if inicio[4:8] == b"ftyp":
        return "mp4"
    if inicio[:4] == b"RIFF":
        return "avi"
    if inicio[:1] == b"\x47":
        return "ts"
    return None


async def detectar_extension(url: str, *, cliente: httpx.AsyncClient) -> str | None:
    inicio = b""
    try:
        async with cliente.stream(
            "GET", url, headers={"Range": "bytes=0-15"}, timeout=10.0
        ) as respuesta:
            if respuesta.status_code >= 400:
                return None
            async for trozo in respuesta.aiter_bytes():
                inicio += trozo
                if len(inicio) >= 16:
                    break
    except httpx.HTTPError:
        return None
    return extension_por_firma(inicio[:16])


def _ruta(credenciales: CredencialesXtream, tipo: str) -> str:
    usuario = quote(credenciales.nombre_usuario, safe="")
    contrasena = quote(credenciales.contrasena, safe="")
    return f"{credenciales.url_base}/{tipo}/{usuario}/{contrasena}"


def _segmento(valor: str) -> str:
    if not _SEGMENTO_VALIDO.match(valor):
        raise ValueError(f"Identificador o extensión no válidos: {valor!r}")
    return valor
