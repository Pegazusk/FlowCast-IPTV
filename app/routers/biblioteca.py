import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import SesionBD, UsuarioActual
from app.models import ConexionXtream, Favorito, Historial, ProgresoReproduccion, Usuario
from app.routers.catalogo import quitar_bloqueados
from app.routers.conexiones import ClienteHTTP
from app.routers.perfiles import PerfilPropio
from app.schemas.biblioteca import (
    RespuestaFavorito,
    RespuestaHistorial,
    RespuestaProgreso,
    SolicitudFavorito,
    SolicitudHistorial,
    SolicitudProgreso,
    TipoFavorito,
    TipoHistorial,
    TipoProgreso,
)

router = APIRouter(prefix="/perfiles/{perfil_id}", tags=["biblioteca"])

UMBRAL_COMPLETADO = 0.95
VENTANA_HISTORIAL = timedelta(minutes=10)
Limite = Annotated[int, Query(ge=1, le=500)]
FiltroConexion = Annotated[uuid.UUID | None, Query(description="Solo contenido de esa conexión")]


async def _exigir_conexion_propia(
    sesion_bd: AsyncSession, usuario: Usuario, conexion_id: uuid.UUID
) -> None:
    consulta = select(ConexionXtream.id).where(
        ConexionXtream.id == conexion_id, ConexionXtream.usuario_id == usuario.id
    )
    if (await sesion_bd.execute(consulta)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conexión no encontrada")


@router.get("/favoritos", response_model=list[RespuestaFavorito])
async def listar_favoritos(
    perfil: PerfilPropio,
    usuario: UsuarioActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
    tipo_contenido: TipoFavorito | None = None,
    conexion_id: FiltroConexion = None,
) -> list[RespuestaFavorito]:
    consulta = select(Favorito).where(Favorito.perfil_id == perfil.id)
    if tipo_contenido is not None:
        consulta = consulta.where(Favorito.tipo_contenido == tipo_contenido)
    if conexion_id is not None:
        consulta = consulta.where(Favorito.conexion_id == conexion_id)
    favoritos = (await sesion_bd.execute(consulta.order_by(Favorito.creado_en.desc()))).scalars()
    visibles = await quitar_bloqueados(list(favoritos), usuario, sesion_bd, cliente)
    return [RespuestaFavorito.model_validate(f) for f in visibles]


@router.put("/favoritos", response_model=RespuestaFavorito)
async def marcar_favorito(
    datos: SolicitudFavorito, perfil: PerfilPropio, usuario: UsuarioActual, sesion_bd: SesionBD
) -> RespuestaFavorito:
    await _exigir_conexion_propia(sesion_bd, usuario, datos.conexion_id)
    clave = (perfil.id, datos.conexion_id, datos.tipo_contenido, datos.stream_id)
    favorito = await sesion_bd.get(Favorito, clave)
    if favorito is None:
        favorito = Favorito(perfil_id=perfil.id, **datos.model_dump())
        sesion_bd.add(favorito)
    else:
        favorito.titulo, favorito.url_portada = datos.titulo, datos.url_portada
    await sesion_bd.commit()
    await sesion_bd.refresh(favorito)
    return RespuestaFavorito.model_validate(favorito)


@router.delete(
    "/favoritos/{conexion_id}/{tipo_contenido}/{stream_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def quitar_favorito(
    perfil: PerfilPropio,
    sesion_bd: SesionBD,
    conexion_id: uuid.UUID,
    tipo_contenido: TipoFavorito,
    stream_id: str,
) -> None:
    favorito = await sesion_bd.get(Favorito, (perfil.id, conexion_id, tipo_contenido, stream_id))
    if favorito is not None:
        await sesion_bd.delete(favorito)
        await sesion_bd.commit()


@router.get("/progreso", response_model=list[RespuestaProgreso])
async def listar_continuar_viendo(
    perfil: PerfilPropio,
    usuario: UsuarioActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
    conexion_id: FiltroConexion = None,
    limite: Limite = 50,
) -> list[RespuestaProgreso]:
    consulta = select(ProgresoReproduccion).where(
        ProgresoReproduccion.perfil_id == perfil.id, ProgresoReproduccion.completado.is_(False)
    )
    if conexion_id is not None:
        consulta = consulta.where(ProgresoReproduccion.conexion_id == conexion_id)
    consulta = consulta.order_by(ProgresoReproduccion.actualizado_en.desc()).limit(limite)
    progresos = list((await sesion_bd.execute(consulta)).scalars())
    visibles = await quitar_bloqueados(progresos, usuario, sesion_bd, cliente)
    return [RespuestaProgreso.model_validate(p) for p in visibles]


@router.put("/progreso", response_model=RespuestaProgreso)
async def guardar_progreso(
    datos: SolicitudProgreso, perfil: PerfilPropio, usuario: UsuarioActual, sesion_bd: SesionBD
) -> RespuestaProgreso:
    await _exigir_conexion_propia(sesion_bd, usuario, datos.conexion_id)
    if datos.completado is not None:
        completado = datos.completado
    else:
        completado = (
            datos.duracion_segundos is not None
            and datos.posicion_segundos / datos.duracion_segundos >= UMBRAL_COMPLETADO
        )
    clave = (perfil.id, datos.conexion_id, datos.tipo_contenido, datos.stream_id)
    progreso = await sesion_bd.get(ProgresoReproduccion, clave)
    if progreso is None:
        progreso = ProgresoReproduccion(
            perfil_id=perfil.id, **datos.model_dump(exclude={"completado"})
        )
        sesion_bd.add(progreso)
    else:
        for campo, valor in datos.model_dump(
            exclude={"completado", "conexion_id", "tipo_contenido", "stream_id"}
        ).items():
            setattr(progreso, campo, valor)
    progreso.completado = completado
    progreso.actualizado_en = datetime.now(UTC)
    await sesion_bd.commit()
    await sesion_bd.refresh(progreso)
    return RespuestaProgreso.model_validate(progreso)


@router.get(
    "/progreso/{conexion_id}/{tipo_contenido}/{stream_id}", response_model=RespuestaProgreso
)
async def ver_progreso(
    perfil: PerfilPropio,
    sesion_bd: SesionBD,
    conexion_id: uuid.UUID,
    tipo_contenido: TipoProgreso,
    stream_id: str,
) -> RespuestaProgreso:
    progreso = await sesion_bd.get(
        ProgresoReproduccion, (perfil.id, conexion_id, tipo_contenido, stream_id)
    )
    if progreso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sin progreso guardado")
    return RespuestaProgreso.model_validate(progreso)


@router.delete(
    "/progreso/{conexion_id}/{tipo_contenido}/{stream_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def borrar_progreso(
    perfil: PerfilPropio,
    sesion_bd: SesionBD,
    conexion_id: uuid.UUID,
    tipo_contenido: TipoProgreso,
    stream_id: str,
) -> None:
    progreso = await sesion_bd.get(
        ProgresoReproduccion, (perfil.id, conexion_id, tipo_contenido, stream_id)
    )
    if progreso is not None:
        await sesion_bd.delete(progreso)
        await sesion_bd.commit()


@router.get("/historial", response_model=list[RespuestaHistorial])
async def listar_historial(
    perfil: PerfilPropio,
    usuario: UsuarioActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
    conexion_id: FiltroConexion = None,
    tipo_contenido: TipoHistorial | None = None,
    limite: Limite = 50,
) -> list[RespuestaHistorial]:
    consulta = select(Historial).where(Historial.perfil_id == perfil.id)
    if conexion_id is not None:
        consulta = consulta.where(Historial.conexion_id == conexion_id)
    if tipo_contenido is not None:
        consulta = consulta.where(Historial.tipo_contenido == tipo_contenido)
    consulta = consulta.order_by(Historial.reproducido_en.desc(), Historial.id.desc()).limit(limite)
    entradas = list((await sesion_bd.execute(consulta)).scalars())
    visibles = await quitar_bloqueados(entradas, usuario, sesion_bd, cliente)
    return [RespuestaHistorial.model_validate(h) for h in visibles]


@router.post("/historial", response_model=RespuestaHistorial, status_code=status.HTTP_201_CREATED)
async def registrar_reproduccion(
    datos: SolicitudHistorial, perfil: PerfilPropio, usuario: UsuarioActual, sesion_bd: SesionBD
) -> RespuestaHistorial:
    await _exigir_conexion_propia(sesion_bd, usuario, datos.conexion_id)
    ahora = datetime.now(UTC)
    reciente = (
        await sesion_bd.execute(
            select(Historial)
            .where(
                Historial.perfil_id == perfil.id,
                Historial.conexion_id == datos.conexion_id,
                Historial.tipo_contenido == datos.tipo_contenido,
                Historial.stream_id == datos.stream_id,
                Historial.reproducido_en >= ahora - VENTANA_HISTORIAL,
            )
            .order_by(Historial.reproducido_en.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if reciente is not None:
        reciente.reproducido_en = ahora
        entrada = reciente
    else:
        entrada = Historial(perfil_id=perfil.id, **datos.model_dump())
        sesion_bd.add(entrada)
    await sesion_bd.commit()
    await sesion_bd.refresh(entrada)
    return RespuestaHistorial.model_validate(entrada)


@router.delete("/historial/{entrada_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_entrada_historial(
    perfil: PerfilPropio, sesion_bd: SesionBD, entrada_id: int
) -> None:
    await sesion_bd.execute(
        delete(Historial).where(Historial.id == entrada_id, Historial.perfil_id == perfil.id)
    )
    await sesion_bd.commit()


@router.delete("/historial", status_code=status.HTTP_204_NO_CONTENT)
async def vaciar_historial(perfil: PerfilPropio, sesion_bd: SesionBD) -> None:
    await sesion_bd.execute(delete(Historial).where(Historial.perfil_id == perfil.id))
    await sesion_bd.commit()
