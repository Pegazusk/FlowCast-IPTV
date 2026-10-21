import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2 as httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import configuracion
from app.models import DisponibilidadTmdb, Plataforma
from app.services import tmdb

REGION = "MX"
URL_LOGOS = "https://image.tmdb.org/t/p/w300"
GRUPOS_TMDB = ("flatrate", "free", "ads")
CONSULTAS_SIMULTANEAS = 8
DIAS_VIGENCIA = 7
TAMANO_LOTE = 200

REGLAS = (
    ("netflix", "Netflix", lambda n: "netflix" in n),
    ("paramount", "Paramount+", lambda n: "paramount" in n),
    ("disney", "Disney+", lambda n: "disney" in n or n.startswith("star+") or n == "star plus"),
    ("max", "Max", lambda n: n in ("max", "hbo max") or n.startswith(("max ", "hbo"))),
    ("apple", "Apple TV+", lambda n: "apple tv" in n),
    ("prime", "Prime Video", lambda n: "amazon prime video" in n or n == "prime video"),
    ("vix", "ViX", lambda n: n.startswith("vix")),
    ("claro", "Claro video", lambda n: "claro video" in n),
    ("crunchyroll", "Crunchyroll", lambda n: "crunchyroll" in n),
    ("mubi", "MUBI", lambda n: n.startswith("mubi")),
    ("pluto", "Pluto TV", lambda n: "pluto tv" in n),
    ("mercadoplay", "Mercado Play", lambda n: "mercado play" in n),
)


def clasificar(nombre_proveedor: str) -> str | None:
    nombre = nombre_proveedor.strip().lower()
    for clave, _nombre, coincide in REGLAS:
        if coincide(nombre):
            return clave
    return None


def nombre_de(clave: str) -> str:
    return next((nombre for c, nombre, _ in REGLAS if c == clave), clave)


def claves_de_respuesta(datos: dict[str, Any]) -> set[str]:
    region = (datos.get("results") or {}).get(REGION) or {}
    claves = set()
    for grupo in GRUPOS_TMDB:
        for proveedor in region.get(grupo) or []:
            clave = clasificar(str(proveedor.get("provider_name") or ""))
            if clave:
                claves.add(clave)
    return claves


async def _pedir(cliente: httpx.AsyncClient, ruta: str, parametros: dict[str, Any]) -> Any:
    for _intento in range(5):
        try:
            respuesta = await cliente.get(f"{tmdb.URL_API}{ruta}", params=parametros)
        except httpx.HTTPError:
            await asyncio.sleep(2)
            continue
        if respuesta.status_code == 429:
            await asyncio.sleep(float(respuesta.headers.get("retry-after", "2")))
            continue
        if respuesta.status_code == 404:
            return {}
        if respuesta.status_code != 200:
            return None
        return respuesta.json()
    return None


async def actualizar_catalogo_plataformas(
    sesion_bd: AsyncSession, cliente: httpx.AsyncClient
) -> int:
    mejores: dict[str, tuple[int, str | None]] = {}
    for tipo in ("movie", "tv"):
        datos = await _pedir(
            cliente,
            f"/watch/providers/{tipo}",
            {"api_key": configuracion.tmdb_clave_api, "watch_region": REGION},
        )
        for proveedor in (datos or {}).get("results") or []:
            clave = clasificar(str(proveedor.get("provider_name") or ""))
            if not clave:
                continue
            prioridad = int((proveedor.get("display_priorities") or {}).get(REGION, 1000))
            logo = proveedor.get("logo_path")
            if clave not in mejores or prioridad < mejores[clave][0]:
                mejores[clave] = (prioridad, f"{URL_LOGOS}{logo}" if logo else None)
    for clave, (orden, logo) in mejores.items():
        await sesion_bd.execute(
            insert(Plataforma)
            .values(clave=clave, nombre=nombre_de(clave), logo=logo, orden=orden)
            .on_conflict_do_update(
                index_elements=[Plataforma.clave],
                set_={"nombre": nombre_de(clave), "logo": logo, "orden": orden},
            )
        )
    await sesion_bd.commit()
    return len(mejores)


async def pendientes(
    sesion_bd: AsyncSession, titulos: Iterable[tuple[str, str]], dias: int = DIAS_VIGENCIA
) -> list[tuple[str, str]]:
    limite = datetime.now(UTC) - timedelta(days=dias)
    filas = await sesion_bd.execute(
        select(DisponibilidadTmdb.tipo_contenido, DisponibilidadTmdb.tmdb_id).where(
            DisponibilidadTmdb.consultado_en >= limite
        )
    )
    recientes = {(tipo, tmdb_id) for tipo, tmdb_id in filas.all()}
    return sorted({titulo for titulo in titulos if titulo not in recientes})


async def _guardar(sesion_bd: AsyncSession, lote: list[tuple[str, str, list[str]]]) -> None:
    if not lote:
        return
    consulta = insert(DisponibilidadTmdb).values(
        [
            {"tipo_contenido": tipo, "tmdb_id": tmdb_id, "plataformas": claves}
            for tipo, tmdb_id, claves in lote
        ]
    )
    await sesion_bd.execute(
        consulta.on_conflict_do_update(
            index_elements=[DisponibilidadTmdb.tipo_contenido, DisponibilidadTmdb.tmdb_id],
            set_={"plataformas": consulta.excluded.plataformas, "consultado_en": datetime.now(UTC)},
        )
    )
    await sesion_bd.commit()


async def sincronizar(
    sesion_bd: AsyncSession,
    titulos: list[tuple[str, str]],
    cliente: httpx.AsyncClient,
    avisar: Callable[[int, int], None] | None = None,
) -> int:
    semaforo = asyncio.Semaphore(CONSULTAS_SIMULTANEAS)
    lote: list[tuple[str, str, list[str]]] = []
    hechos = 0

    async def consultar(tipo: str, tmdb_id: str) -> tuple[str, str, list[str]] | None:
        ruta = "movie" if tipo == "pelicula" else "tv"
        async with semaforo:
            datos = await _pedir(
                cliente,
                f"/{ruta}/{tmdb_id}/watch/providers",
                {"api_key": configuracion.tmdb_clave_api},
            )
        if datos is None:
            return None
        return tipo, tmdb_id, sorted(claves_de_respuesta(datos))

    for inicio in range(0, len(titulos), TAMANO_LOTE):
        tramo = titulos[inicio : inicio + TAMANO_LOTE]
        resultados = await asyncio.gather(*(consultar(tipo, tmdb_id) for tipo, tmdb_id in tramo))
        lote = [resultado for resultado in resultados if resultado is not None]
        await _guardar(sesion_bd, lote)
        hechos += len(tramo)
        if avisar:
            avisar(hechos, len(titulos))
    return hechos


async def disponibilidad(sesion_bd: AsyncSession) -> dict[tuple[str, str], list[str]]:
    filas = await sesion_bd.execute(
        select(
            DisponibilidadTmdb.tipo_contenido,
            DisponibilidadTmdb.tmdb_id,
            DisponibilidadTmdb.plataformas,
        ).where(DisponibilidadTmdb.plataformas != [])
    )
    return {(tipo, tmdb_id): claves for tipo, tmdb_id, claves in filas.all()}


async def plataformas_conocidas(sesion_bd: AsyncSession) -> list[Plataforma]:
    filas = await sesion_bd.execute(select(Plataforma).order_by(Plataforma.orden))
    return list(filas.scalars())
