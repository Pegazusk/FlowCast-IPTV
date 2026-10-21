import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.deps import SesionBD
from app.routers.catalogo import (
    Agrupar,
    ConexionPropia,
    Control,
    _agrupar,
    _categorias_bloqueadas,
    _lista_completa,
    _modelos,
    _sin_duplicados,
    _visibles,
)
from app.routers.conexiones import ClienteHTTP
from app.schemas import catalogo as esquemas
from app.services import cache, plataformas

router = APIRouter(prefix="/conexiones/{conexion_id}/plataformas", tags=["plataformas"])

SEGUNDOS_DISPONIBILIDAD = 600


class RespuestaPlataforma(BaseModel):
    clave: str
    nombre: str
    logo: str | None
    total_peliculas: int
    total_series: int


class ContenidoPlataforma(BaseModel):
    plataforma: RespuestaPlataforma
    peliculas: list[esquemas.Pelicula]
    series: list[esquemas.Serie]


async def _catalogo(
    contexto: ConexionPropia, cliente: Any, sesion_bd: SesionBD, control: Control
) -> dict[str, Any]:
    peliculas, series, disponibles, b_peliculas, b_series = await asyncio.gather(
        _lista_completa(contexto, cliente, "pelicula"),
        _lista_completa(contexto, cliente, "serie"),
        cache.obtener_o_calcular(
            "plataformas:disponibilidad",
            lambda: plataformas.disponibilidad(sesion_bd),
            SEGUNDOS_DISPONIBILIDAD,
        ),
        _categorias_bloqueadas(contexto, cliente, control.bloqueos, "pelicula"),
        _categorias_bloqueadas(contexto, cliente, control.bloqueos, "serie"),
    )
    return {
        "peliculas": _visibles(_sin_duplicados(peliculas), b_peliculas, control),
        "series": _visibles(_sin_duplicados(series), b_series, control),
        "disponibles": disponibles,
        "bloqueadas": {"pelicula": b_peliculas, "serie": b_series},
    }


def _claves(disponibles: dict, tipo: str, elemento: Any) -> list[str]:
    return disponibles.get((tipo, elemento.tmdb_id), []) if elemento.tmdb_id else []


def _resumen(conocida: Any, peliculas: int, series: int) -> RespuestaPlataforma:
    return RespuestaPlataforma(
        clave=conocida.clave,
        nombre=conocida.nombre,
        logo=conocida.logo,
        total_peliculas=peliculas,
        total_series=series,
    )


@router.get("", response_model=list[RespuestaPlataforma])
async def listar_plataformas(
    contexto: ConexionPropia, cliente: ClienteHTTP, sesion_bd: SesionBD, control: Control
) -> list[RespuestaPlataforma]:
    datos = await _catalogo(contexto, cliente, sesion_bd, control)
    conteo: dict[tuple[str, str], int] = {}
    for tipo, lista in (("pelicula", datos["peliculas"]), ("serie", datos["series"])):
        for elemento in lista:
            for clave in _claves(datos["disponibles"], tipo, elemento):
                conteo[(clave, tipo)] = conteo.get((clave, tipo), 0) + 1
    resultado = []
    for conocida in await plataformas.plataformas_conocidas(sesion_bd):
        peliculas = conteo.get((conocida.clave, "pelicula"), 0)
        series = conteo.get((conocida.clave, "serie"), 0)
        if peliculas or series:
            resultado.append(_resumen(conocida, peliculas, series))
    return resultado


@router.get("/{clave}", response_model=ContenidoPlataforma)
async def contenido_plataforma(
    clave: str,
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    sesion_bd: SesionBD,
    control: Control,
    agrupar: Agrupar = False,
) -> ContenidoPlataforma:
    conocida = next(
        (p for p in await plataformas.plataformas_conocidas(sesion_bd) if p.clave == clave), None
    )
    if conocida is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plataforma desconocida")
    datos = await _catalogo(contexto, cliente, sesion_bd, control)
    peliculas = [
        p for p in datos["peliculas"] if clave in _claves(datos["disponibles"], "pelicula", p)
    ]
    series = [s for s in datos["series"] if clave in _claves(datos["disponibles"], "serie", s)]
    g_peliculas = g_series = None
    if agrupar:
        peliculas, g_peliculas = _agrupar(peliculas)
        series, g_series = _agrupar(series)
    peliculas.sort(key=lambda p: p.agregado_en.timestamp() if p.agregado_en else 0, reverse=True)
    return ContenidoPlataforma(
        plataforma=_resumen(conocida, len(peliculas), len(series)),
        peliculas=_modelos(
            esquemas.Pelicula, peliculas, datos["bloqueadas"]["pelicula"], g_peliculas
        ),
        series=_modelos(esquemas.Serie, series, datos["bloqueadas"]["serie"], g_series),
    )
