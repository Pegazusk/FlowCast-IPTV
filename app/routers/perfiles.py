import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import security
from app.deps import SesionBD, UsuarioActual
from app.models import Perfil
from app.schemas.perfiles import (
    RespuestaPerfil,
    SolicitudActualizarPerfil,
    SolicitudCrearPerfil,
    SolicitudVerificarPin,
)

router = APIRouter(prefix="/perfiles", tags=["perfiles"])

NOMBRE_PERFIL_INICIAL = "Principal"


async def obtener_perfil_propio(
    perfil_id: uuid.UUID, usuario: UsuarioActual, sesion_bd: SesionBD
) -> Perfil:
    consulta = select(Perfil).where(Perfil.id == perfil_id, Perfil.usuario_id == usuario.id)
    perfil = (await sesion_bd.execute(consulta)).scalar_one_or_none()
    if perfil is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Perfil no encontrado")
    return perfil


PerfilPropio = Annotated[Perfil, Depends(obtener_perfil_propio)]


def _respuesta(perfil: Perfil) -> RespuestaPerfil:
    return RespuestaPerfil(
        id=perfil.id,
        nombre=perfil.nombre,
        avatar=perfil.avatar,
        es_infantil=perfil.es_infantil,
        tiene_pin=perfil.hash_pin_parental is not None,
        url_imagen=_url_imagen(perfil),
        creado_en=perfil.creado_en,
    )


def _url_imagen(perfil: Perfil) -> str | None:
    if perfil.imagen_tipo is None:
        return None
    version = int(perfil.imagen_actualizada_en.timestamp()) if perfil.imagen_actualizada_en else 0
    return f"/perfiles/{perfil.id}/imagen?v={version}"


@router.get("", response_model=list[RespuestaPerfil])
async def listar_perfiles(usuario: UsuarioActual, sesion_bd: SesionBD) -> list[RespuestaPerfil]:
    consulta = select(Perfil).where(Perfil.usuario_id == usuario.id).order_by(Perfil.creado_en)
    perfiles = list((await sesion_bd.execute(consulta)).scalars())
    if not perfiles:
        inicial = Perfil(usuario_id=usuario.id, nombre=NOMBRE_PERFIL_INICIAL)
        sesion_bd.add(inicial)
        await sesion_bd.commit()
        await sesion_bd.refresh(inicial)
        perfiles = [inicial]
    return [_respuesta(p) for p in perfiles]


@router.post("", response_model=RespuestaPerfil, status_code=status.HTTP_201_CREATED)
async def crear_perfil(
    datos: SolicitudCrearPerfil, usuario: UsuarioActual, sesion_bd: SesionBD
) -> RespuestaPerfil:
    perfil = Perfil(
        usuario_id=usuario.id,
        nombre=datos.nombre,
        avatar=datos.avatar,
        es_infantil=datos.es_infantil,
        hash_pin_parental=security.generar_hash_contrasena(datos.pin) if datos.pin else None,
    )
    sesion_bd.add(perfil)
    try:
        await sesion_bd.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Ya tienes un perfil con ese nombre"
        ) from None
    await sesion_bd.refresh(perfil)
    await sesion_bd.commit()
    return _respuesta(perfil)


@router.get("/{perfil_id}", response_model=RespuestaPerfil)
async def ver_perfil(perfil: PerfilPropio) -> RespuestaPerfil:
    return _respuesta(perfil)


@router.patch("/{perfil_id}", response_model=RespuestaPerfil)
async def actualizar_perfil(
    datos: SolicitudActualizarPerfil, perfil: PerfilPropio, sesion_bd: SesionBD
) -> RespuestaPerfil:

    if datos.nombre is not None:
        perfil.nombre = datos.nombre
    if datos.avatar is not None:
        perfil.avatar = datos.avatar
    if datos.es_infantil is not None:
        perfil.es_infantil = datos.es_infantil
    if datos.quitar_pin:
        perfil.hash_pin_parental = None
    elif datos.pin is not None:
        perfil.hash_pin_parental = security.generar_hash_contrasena(datos.pin)
    try:
        await sesion_bd.commit()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Ya tienes un perfil con ese nombre"
        ) from None
    return _respuesta(perfil)


@router.delete("/{perfil_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_perfil(perfil: PerfilPropio, usuario: UsuarioActual, sesion_bd: SesionBD) -> None:
    total = (
        await sesion_bd.execute(
            select(func.count()).select_from(Perfil).where(Perfil.usuario_id == usuario.id)
        )
    ).scalar_one()
    if total <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No puedes eliminar el único perfil")
    await sesion_bd.delete(perfil)
    await sesion_bd.commit()


@router.post("/{perfil_id}/verificar-pin")
async def verificar_pin(datos: SolicitudVerificarPin, perfil: PerfilPropio) -> dict[str, bool]:
    if perfil.hash_pin_parental is None:
        return {"valido": True}
    return {"valido": security.verificar_contrasena(datos.pin, perfil.hash_pin_parental)}


TAMANO_MAXIMO_IMAGEN = 2 * 1024 * 1024
FIRMAS_IMAGEN = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}


def _tipo_imagen(datos: bytes) -> str | None:
    for firma, tipo in FIRMAS_IMAGEN.items():
        if datos.startswith(firma):
            return tipo
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.put("/{perfil_id}/imagen", response_model=RespuestaPerfil)
async def subir_imagen(
    archivo: UploadFile, perfil: PerfilPropio, sesion_bd: SesionBD
) -> RespuestaPerfil:
    datos = await archivo.read(TAMANO_MAXIMO_IMAGEN + 1)
    if len(datos) > TAMANO_MAXIMO_IMAGEN:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, detail="La imagen no puede superar 2 MB"
        )
    tipo = _tipo_imagen(datos)
    if tipo is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Solo se admiten imágenes JPEG, PNG o WebP",
        )
    perfil.imagen_avatar = datos
    perfil.imagen_tipo = tipo
    perfil.imagen_actualizada_en = datetime.now(UTC)
    await sesion_bd.commit()
    await sesion_bd.refresh(perfil, attribute_names=["imagen_tipo", "imagen_actualizada_en"])
    return _respuesta(perfil)


@router.get("/{perfil_id}/imagen")
async def ver_imagen(perfil: PerfilPropio, sesion_bd: SesionBD) -> Response:
    fila = (
        await sesion_bd.execute(
            select(Perfil.imagen_avatar, Perfil.imagen_tipo).where(Perfil.id == perfil.id)
        )
    ).one()
    if fila.imagen_avatar is None or fila.imagen_tipo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El perfil no tiene imagen")
    return Response(
        content=fila.imagen_avatar,
        media_type=fila.imagen_tipo,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.delete("/{perfil_id}/imagen", response_model=RespuestaPerfil)
async def quitar_imagen(perfil: PerfilPropio, sesion_bd: SesionBD) -> RespuestaPerfil:
    perfil.imagen_avatar = None
    perfil.imagen_tipo = None
    perfil.imagen_actualizada_en = None
    await sesion_bd.commit()
    return _respuesta(perfil)
