from dataclasses import dataclass
from typing import Any

import httpx2 as httpx

from app.config import configuracion

URL_API = "https://api.themoviedb.org/3"
URL_FOTOS = "https://image.tmdb.org/t/p/w185"
TIEMPO_ESPERA_SEGUNDOS = 10.0
MAXIMO_ACTORES = 20


@dataclass(frozen=True)
class Actor:
    nombre: str
    personaje: str | None
    foto: str | None


def disponible() -> bool:
    return bool(configuracion.tmdb_clave_api)


async def reparto_pelicula(tmdb_id: str, cliente: httpx.AsyncClient | None = None) -> list[Actor]:
    if not disponible():
        return []
    parametros = {"api_key": configuracion.tmdb_clave_api, "language": "es-MX"}
    cliente_propio = cliente is None
    if cliente is None:
        cliente = httpx.AsyncClient(timeout=TIEMPO_ESPERA_SEGUNDOS)
    try:
        respuesta = await cliente.get(f"{URL_API}/movie/{tmdb_id}/credits", params=parametros)
    except httpx.HTTPError:
        return []
    finally:
        if cliente_propio:
            await cliente.aclose()
    if respuesta.status_code != 200:
        return []
    try:
        datos: Any = respuesta.json()
    except ValueError:
        return []
    actores = []
    for persona in (datos.get("cast") or [])[:MAXIMO_ACTORES]:
        nombre = str(persona.get("name") or "").strip()
        if not nombre:
            continue
        ruta_foto = persona.get("profile_path")
        actores.append(
            Actor(
                nombre=nombre,
                personaje=(str(persona.get("character")).strip() or None)
                if persona.get("character")
                else None,
                foto=f"{URL_FOTOS}{ruta_foto}" if ruta_foto else None,
            )
        )
    return actores


def reparto_desde_texto(texto: str | None) -> list[Actor]:
    if not texto:
        return []
    nombres = [n.strip() for n in texto.replace(";", ",").split(",")]
    return [Actor(nombre=n, personaje=None, foto=None) for n in nombres if n][:MAXIMO_ACTORES]


async def _obtener(ruta: str, cliente: httpx.AsyncClient | None) -> Any:
    parametros = {"api_key": configuracion.tmdb_clave_api}
    cliente_propio = cliente is None
    if cliente is None:
        cliente = httpx.AsyncClient(timeout=TIEMPO_ESPERA_SEGUNDOS)
    try:
        respuesta = await cliente.get(f"{URL_API}{ruta}", params=parametros)
    except httpx.HTTPError:
        return None
    finally:
        if cliente_propio:
            await cliente.aclose()
    if respuesta.status_code != 200:
        return None
    try:
        return respuesta.json()
    except ValueError:
        return None


def _por_pais(clasificaciones: dict[str, str]) -> str | None:
    if clasificaciones.get("MX"):
        return clasificaciones["MX"]
    if clasificaciones.get("US"):
        return f"{clasificaciones['US']} (EE. UU.)"
    return None


async def clasificacion(
    tipo: str, tmdb_id: str, cliente: httpx.AsyncClient | None = None
) -> str | None:
    if not disponible():
        return None
    encontradas: dict[str, str] = {}
    if tipo == "pelicula":
        datos = await _obtener(f"/movie/{tmdb_id}/release_dates", cliente)
        for pais in (datos or {}).get("results") or []:
            for estreno in pais.get("release_dates") or []:
                valor = str(estreno.get("certification") or "").strip()
                if valor and pais.get("iso_3166_1") not in encontradas:
                    encontradas[pais["iso_3166_1"]] = valor
    else:
        datos = await _obtener(f"/tv/{tmdb_id}/content_ratings", cliente)
        for pais in (datos or {}).get("results") or []:
            valor = str(pais.get("rating") or "").strip()
            if valor:
                encontradas[pais.get("iso_3166_1")] = valor
    return _por_pais(encontradas)
