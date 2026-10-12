import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import SesionBD, UsuarioActual
from app.models import ConexionXtream, Perfil, Resena, Usuario
from app.routers.perfiles import PerfilPropio
from app.schemas.resenas import RespuestaResena, ResumenResenas, SolicitudResena, TipoResena

router = APIRouter(prefix="/perfiles/{perfil_id}/resenas", tags=["resenas"])


async def _huella_servidor(
    sesion_bd: AsyncSession, usuario: Usuario, conexion_id: uuid.UUID
) -> str:
    consulta = select(ConexionXtream).where(
        ConexionXtream.id == conexion_id, ConexionXtream.usuario_id == usuario.id
    )
    conexion = (await sesion_bd.execute(consulta)).scalar_one_or_none()
    if conexion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conexión no encontrada")
    url_normalizada = conexion.url_base.strip().rstrip("/").lower()
    return hashlib.sha256(url_normalizada.encode()).hexdigest()


def _respuesta(resena: Resena, perfil_autor: Perfil, perfil_lector: Perfil) -> RespuestaResena:
    return RespuestaResena(
        id=resena.id,
        tipo_contenido=resena.tipo_contenido,
        stream_id=resena.stream_id,
        titulo=resena.titulo,
        autor=perfil_autor.nombre,
        avatar=perfil_autor.avatar,
        calificacion=resena.calificacion,
        texto=resena.texto,
        actualizado_en=resena.actualizado_en,
        es_mia=resena.perfil_id == perfil_lector.id,
    )


@router.get("/{conexion_id}/{tipo_contenido}/{stream_id}", response_model=ResumenResenas)
async def ver_resenas(
    perfil: PerfilPropio,
    usuario: UsuarioActual,
    sesion_bd: SesionBD,
    conexion_id: uuid.UUID,
    tipo_contenido: TipoResena,
    stream_id: str,
) -> ResumenResenas:
    huella = await _huella_servidor(sesion_bd, usuario, conexion_id)
    consulta = (
        select(Resena, Perfil)
        .join(Perfil, Perfil.id == Resena.perfil_id)
        .where(
            Resena.servidor_huella == huella,
            Resena.tipo_contenido == tipo_contenido,
            Resena.stream_id == stream_id,
        )
        .order_by(Resena.actualizado_en.desc())
    )
    filas = (await sesion_bd.execute(consulta)).all()
    resenas = [_respuesta(resena, autor, perfil) for resena, autor in filas]
    distribucion = {estrellas: 0 for estrellas in range(1, 6)}
    for resena in resenas:
        distribucion[resena.calificacion] += 1
    promedio = round(sum(r.calificacion for r in resenas) / len(resenas), 1) if resenas else None
    return ResumenResenas(
        promedio=promedio,
        total=len(resenas),
        distribucion=distribucion,
        mia=next((r for r in resenas if r.es_mia), None),
        resenas=resenas,
    )


@router.put("", response_model=RespuestaResena)
async def guardar_resena(
    datos: SolicitudResena, perfil: PerfilPropio, usuario: UsuarioActual, sesion_bd: SesionBD
) -> RespuestaResena:
    huella = await _huella_servidor(sesion_bd, usuario, datos.conexion_id)
    consulta = select(Resena).where(
        Resena.perfil_id == perfil.id,
        Resena.servidor_huella == huella,
        Resena.tipo_contenido == datos.tipo_contenido,
        Resena.stream_id == datos.stream_id,
    )
    resena = (await sesion_bd.execute(consulta)).scalar_one_or_none()
    if resena is None:
        resena = Resena(
            perfil_id=perfil.id,
            servidor_huella=huella,
            tipo_contenido=datos.tipo_contenido,
            stream_id=datos.stream_id,
        )
        sesion_bd.add(resena)
    resena.titulo = datos.titulo
    resena.calificacion = datos.calificacion
    resena.texto = datos.texto.strip() if datos.texto and datos.texto.strip() else None
    resena.actualizado_en = datetime.now(UTC)
    await sesion_bd.commit()
    await sesion_bd.refresh(resena)
    return _respuesta(resena, perfil, perfil)


@router.delete(
    "/{conexion_id}/{tipo_contenido}/{stream_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def borrar_resena(
    perfil: PerfilPropio,
    usuario: UsuarioActual,
    sesion_bd: SesionBD,
    conexion_id: uuid.UUID,
    tipo_contenido: TipoResena,
    stream_id: str,
) -> None:
    huella = await _huella_servidor(sesion_bd, usuario, conexion_id)
    consulta = select(Resena).where(
        Resena.perfil_id == perfil.id,
        Resena.servidor_huella == huella,
        Resena.tipo_contenido == tipo_contenido,
        Resena.stream_id == stream_id,
    )
    resena = (await sesion_bd.execute(consulta)).scalar_one_or_none()
    if resena is not None:
        await sesion_bd.delete(resena)
        await sesion_bd.commit()


@router.get("", response_model=list[RespuestaResena])
async def mis_resenas(perfil: PerfilPropio, sesion_bd: SesionBD) -> list[RespuestaResena]:
    consulta = (
        select(Resena).where(Resena.perfil_id == perfil.id).order_by(Resena.actualizado_en.desc())
    )
    resenas = (await sesion_bd.execute(consulta)).scalars()
    return [_respuesta(r, perfil, perfil) for r in resenas]
