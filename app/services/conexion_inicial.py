from urllib.parse import urlsplit

import httpx2 as httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import configuracion
from app.models import ConexionXtream, CuentaProveedor, Usuario
from app.services import xtream


def esta_configurada() -> bool:
    return bool(
        configuracion.conexion_inicial_url
        and configuracion.conexion_inicial_usuario
        and configuracion.conexion_inicial_contrasena
    )


async def cuenta_predeterminada(sesion_bd: AsyncSession) -> CuentaProveedor | None:
    consulta = select(CuentaProveedor).where(CuentaProveedor.predeterminada.is_(True)).limit(1)
    return (await sesion_bd.execute(consulta)).scalar_one_or_none()


async def asegurar_conexion_inicial(
    sesion_bd: AsyncSession, usuario: Usuario, cliente: httpx.AsyncClient
) -> ConexionXtream | None:
    cuenta = await cuenta_predeterminada(sesion_bd)
    if cuenta is None and not esta_configurada():
        return None
    if cuenta is not None:
        url_base, nombre_usuario, contrasena = (
            cuenta.url_base,
            cuenta.nombre_usuario,
            cuenta.contrasena,
        )
    else:
        url_base = xtream.normalizar_url_base(configuracion.conexion_inicial_url)
        nombre_usuario = configuracion.conexion_inicial_usuario
        contrasena = configuracion.conexion_inicial_contrasena

    consulta = select(ConexionXtream.id).where(ConexionXtream.usuario_id == usuario.id).limit(1)
    if (await sesion_bd.execute(consulta)).first() is not None:
        return None

    conexion = ConexionXtream.nueva(
        usuario_id=usuario.id,
        etiqueta=(cuenta.etiqueta if cuenta else configuracion.conexion_inicial_etiqueta)
        or urlsplit(url_base).hostname
        or url_base,
        url_base=url_base,
        nombre_usuario=nombre_usuario,
        contrasena=contrasena,
    )
    if cuenta is not None:
        conexion.cuenta_proveedor_id = cuenta.id
    try:
        info = await xtream.validar_credenciales(
            url_base, nombre_usuario, contrasena, cliente=cliente
        )
        conexion.actualizar_desde_info(info)
    except xtream.ErrorXtream:
        pass
    sesion_bd.add(conexion)
    await sesion_bd.flush()
    return conexion
