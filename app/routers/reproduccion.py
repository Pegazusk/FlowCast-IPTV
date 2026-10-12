from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.routers.catalogo import (
    SEGUNDOS_FICHAS,
    SEGUNDOS_LISTAS,
    ConexionPropia,
    Control,
    _categorias_bloqueadas,
    _consultar,
    _esta_bloqueado,
)
from app.routers.conexiones import ClienteHTTP
from app.schemas.reproduccion import RespuestaReproduccion
from app.services import xtream

router = APIRouter(prefix="/conexiones/{conexion_id}/reproducir", tags=["reproduccion"])

EXTENSION_POR_DEFECTO = "mp4"


async def _ficha_o_none(clave: str, llamada, tolerar_ausencia: bool):
    try:
        return await _consultar(clave, SEGUNDOS_FICHAS, llamada)
    except HTTPException as error:
        if tolerar_ausencia and error.status_code == status.HTTP_404_NOT_FOUND:
            return None
        raise


def _o_422(construir):
    try:
        return construir()
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from None


@router.get("/en-vivo/{canal_id}", response_model=RespuestaReproduccion)
async def reproducir_en_vivo(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    control: Control,
    canal_id: str,
    formato: Annotated[
        xtream.FormatoEnVivo | None,
        Query(description="m3u8 (HLS) o ts. Sin él se elige el mejor que permita el proveedor"),
    ] = None,
) -> RespuestaReproduccion:
    canales = await _consultar(
        contexto.clave("canales", "todas"),
        SEGUNDOS_LISTAS,
        lambda: xtream.obtener_canales(contexto.credenciales, None, cliente=cliente),
    )
    canal = next((c for c in canales if c.id == canal_id), None)
    if canal is not None:
        bloqueadas = await _categorias_bloqueadas(contexto, cliente, control.bloqueos, "en_vivo")
        control.exigir(_esta_bloqueado(canal, bloqueadas))
    elegido = xtream.elegir_formato_en_vivo(contexto.conexion.formatos_salida_permitidos, formato)
    url = _o_422(lambda: xtream.url_en_vivo(contexto.credenciales, canal_id, elegido))
    return RespuestaReproduccion(
        url=url, formato=elegido, tipo_contenido="en_vivo", contenido_id=canal_id
    )


@router.get("/peliculas/{pelicula_id}", response_model=RespuestaReproduccion)
async def reproducir_pelicula(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    control: Control,
    pelicula_id: str,
    extension: Annotated[
        str | None, Query(description="mp4, mkv... Si falta se consulta la ficha")
    ] = None,
) -> RespuestaReproduccion:
    ficha = await _ficha_o_none(
        contexto.clave("pelicula", pelicula_id),
        lambda: xtream.obtener_ficha_pelicula(contexto.credenciales, pelicula_id, cliente=cliente),
        tolerar_ausencia=extension is not None,
    )
    if ficha is not None:
        bloqueadas = await _categorias_bloqueadas(contexto, cliente, control.bloqueos, "pelicula")
        control.exigir(_esta_bloqueado(ficha.pelicula, bloqueadas))
    if extension is None:
        extension = ficha.pelicula.extension or EXTENSION_POR_DEFECTO
    url = _o_422(lambda: xtream.url_pelicula(contexto.credenciales, pelicula_id, extension))
    return RespuestaReproduccion(
        url=url, formato=extension, tipo_contenido="pelicula", contenido_id=pelicula_id
    )


@router.get("/series/{serie_id}/episodios/{episodio_id}", response_model=RespuestaReproduccion)
async def reproducir_episodio(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    control: Control,
    serie_id: str,
    episodio_id: str,
    extension: Annotated[
        str | None, Query(description="mp4, mkv... Si falta se busca en la ficha de la serie")
    ] = None,
) -> RespuestaReproduccion:
    ficha = await _ficha_o_none(
        contexto.clave("serie", serie_id),
        lambda: xtream.obtener_ficha_serie(contexto.credenciales, serie_id, cliente=cliente),
        tolerar_ausencia=extension is not None,
    )
    if ficha is not None:
        bloqueadas = await _categorias_bloqueadas(contexto, cliente, control.bloqueos, "serie")
        control.exigir(_esta_bloqueado(ficha.serie, bloqueadas))
    if extension is None:
        episodio = next(
            (
                e
                for temporada in ficha.temporadas
                for e in temporada.episodios
                if e.id == episodio_id
            ),
            None,
        )
        if episodio is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Ese episodio no pertenece a la serie"
            )
        extension = episodio.extension or EXTENSION_POR_DEFECTO
    url = _o_422(lambda: xtream.url_episodio(contexto.credenciales, episodio_id, extension))
    return RespuestaReproduccion(
        url=url, formato=extension, tipo_contenido="episodio", contenido_id=episodio_id
    )
