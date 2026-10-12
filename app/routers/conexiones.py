import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

import httpx2 as httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import cifrado
from app.deps import SesionBD, UsuarioActual
from app.models import ConexionXtream, Usuario
from app.schemas.conexiones import RespuestaConexion, SolicitudCrearConexion
from app.services import cache, xtream
from app.services.conexion_inicial import asegurar_conexion_inicial

router = APIRouter(prefix="/conexiones", tags=["conexiones"])


async def obtener_cliente_http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        timeout=xtream.TIEMPO_ESPERA_SEGUNDOS, headers=xtream.CABECERAS, follow_redirects=True
    ) as cliente:
        yield cliente


ClienteHTTP = Annotated[httpx.AsyncClient, Depends(obtener_cliente_http)]


async def _validar_con_proveedor(
    cliente: httpx.AsyncClient, url_base: str, nombre_usuario: str, contrasena: str
) -> xtream.InfoCuentaXtream:
    try:
        return await xtream.validar_credenciales(
            url_base, nombre_usuario, contrasena, cliente=cliente
        )
    except xtream.CredencialesXtreamInvalidas as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(error)) from None
    except xtream.ProveedorNoDisponible as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None


def _aplicar_info(conexion: ConexionXtream, info: xtream.InfoCuentaXtream) -> None:
    conexion.estado_cuenta = info.estado_cuenta
    conexion.expira_en = info.expira_en
    conexion.max_conexiones = info.max_conexiones
    conexion.zona_horaria_servidor = info.zona_horaria_servidor
    conexion.formatos_salida_permitidos = info.formatos_salida_permitidos
    conexion.ultima_autenticacion_en = datetime.now(UTC)


async def _buscar_conexion_propia(
    sesion_bd: AsyncSession, usuario: Usuario, conexion_id: uuid.UUID
) -> ConexionXtream:
    consulta = select(ConexionXtream).where(
        ConexionXtream.id == conexion_id, ConexionXtream.usuario_id == usuario.id
    )
    conexion = (await sesion_bd.execute(consulta)).scalar_one_or_none()
    if conexion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conexión no encontrada")
    return conexion


@router.post("", response_model=RespuestaConexion, status_code=status.HTTP_201_CREATED)
async def crear_conexion(
    datos: SolicitudCrearConexion, usuario: UsuarioActual, sesion_bd: SesionBD, cliente: ClienteHTTP
) -> RespuestaConexion:
    info = await _validar_con_proveedor(
        cliente, datos.url_base, datos.nombre_usuario, datos.contrasena
    )
    conexion = ConexionXtream.nueva(
        usuario_id=usuario.id,
        etiqueta=datos.etiqueta or urlsplit(datos.url_base).hostname or datos.url_base,
        url_base=datos.url_base,
        nombre_usuario=datos.nombre_usuario,
        contrasena=datos.contrasena,
    )
    _aplicar_info(conexion, info)
    sesion_bd.add(conexion)
    try:
        await sesion_bd.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Esa cuenta del proveedor ya está registrada"
        ) from None
    await sesion_bd.refresh(conexion)
    await sesion_bd.commit()
    return RespuestaConexion.model_validate(conexion)


@router.get("", response_model=list[RespuestaConexion])
async def listar_conexiones(
    usuario: UsuarioActual, sesion_bd: SesionBD, cliente: ClienteHTTP
) -> list[RespuestaConexion]:
    if await asegurar_conexion_inicial(sesion_bd, usuario, cliente) is not None:
        await sesion_bd.commit()
    consulta = (
        select(ConexionXtream)
        .where(ConexionXtream.usuario_id == usuario.id)
        .order_by(ConexionXtream.creado_en)
    )
    conexiones = (await sesion_bd.execute(consulta)).scalars()
    return [RespuestaConexion.model_validate(conexion) for conexion in conexiones]


@router.get("/{conexion_id}", response_model=RespuestaConexion)
async def ver_conexion(
    conexion_id: uuid.UUID, usuario: UsuarioActual, sesion_bd: SesionBD
) -> RespuestaConexion:
    conexion = await _buscar_conexion_propia(sesion_bd, usuario, conexion_id)
    return RespuestaConexion.model_validate(conexion)


@router.post("/{conexion_id}/revalidar", response_model=RespuestaConexion)
async def revalidar_conexion(
    conexion_id: uuid.UUID, usuario: UsuarioActual, sesion_bd: SesionBD, cliente: ClienteHTTP
) -> RespuestaConexion:
    conexion = await _buscar_conexion_propia(sesion_bd, usuario, conexion_id)
    contrasena = cifrado.descifrar(conexion.contrasena_cifrada)
    try:
        info = await xtream.validar_credenciales(
            conexion.url_base, conexion.nombre_usuario, contrasena, cliente=cliente
        )
    except xtream.CredencialesXtreamInvalidas:
        conexion.estado_cuenta = "deshabilitada"
    except xtream.ProveedorNoDisponible as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None
    else:
        _aplicar_info(conexion, info)
    await sesion_bd.commit()
    return RespuestaConexion.model_validate(conexion)


@router.delete("/{conexion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_conexion(
    conexion_id: uuid.UUID, usuario: UsuarioActual, sesion_bd: SesionBD
) -> None:
    conexion = await _buscar_conexion_propia(sesion_bd, usuario, conexion_id)
    await sesion_bd.delete(conexion)
    await sesion_bd.commit()
    cache.invalidar(f"conexion:{conexion_id}:")


@router.post("/{conexion_id}/actualizar", status_code=status.HTTP_204_NO_CONTENT)
async def actualizar_catalogo(
    conexion_id: uuid.UUID, usuario: UsuarioActual, sesion_bd: SesionBD
) -> None:
    consulta = select(ConexionXtream.id).where(
        ConexionXtream.id == conexion_id, ConexionXtream.usuario_id == usuario.id
    )
    if (await sesion_bd.execute(consulta)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conexión no encontrada")
    cache.invalidar(f"conexion:{conexion_id}:")
