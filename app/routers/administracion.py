import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx2 as httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import cifrado, security
from app.config import configuracion
from app.deps import AdministradorActual, SesionBD
from app.models import ConexionXtream, CuentaProveedor, Perfil, SesionAutenticacion, Usuario
from app.routers.conexiones import ClienteHTTP
from app.schemas.administracion import (
    RespuestaCuentaProveedor,
    RespuestaProveedor,
    RespuestaSesionDispositivo,
    RespuestaSesionesCerradas,
    RespuestaUsuarioAdministrado,
    SolicitudActualizarCuentaProveedor,
    SolicitudActualizarUsuario,
    SolicitudCrearUsuario,
    SolicitudCuentaProveedor,
    SolicitudProveedor,
    correo_interno,
)
from app.services import cache, conexion_inicial, xtream
from app.services.conexion_inicial import esta_configurada

router = APIRouter(prefix="/admin/api", tags=["administracion"])


def _proveedor(conexion: ConexionXtream) -> RespuestaProveedor:
    return RespuestaProveedor(
        id=conexion.id,
        etiqueta=conexion.etiqueta,
        servidor=urlsplit(conexion.url_base).hostname or conexion.url_base,
        nombre_usuario=conexion.nombre_usuario,
        estado_cuenta=conexion.estado_cuenta,
        expira_en=conexion.expira_en,
        max_conexiones=conexion.max_conexiones,
        cuenta_id=conexion.cuenta_proveedor_id,
    )


async def _describir(
    sesion_bd: AsyncSession, usuarios: list[Usuario]
) -> list[RespuestaUsuarioAdministrado]:
    ids = [usuario.id for usuario in usuarios]
    if not ids:
        return []
    ahora = datetime.now(UTC)
    consulta_sesiones = (
        select(SesionAutenticacion.usuario_id, func.count())
        .where(
            SesionAutenticacion.usuario_id.in_(ids),
            SesionAutenticacion.revocado_en.is_(None),
            SesionAutenticacion.expira_en > ahora,
        )
        .group_by(SesionAutenticacion.usuario_id)
    )
    sesiones = dict((await sesion_bd.execute(consulta_sesiones)).all())
    consulta_conexiones = (
        select(ConexionXtream)
        .where(ConexionXtream.usuario_id.in_(ids))
        .order_by(ConexionXtream.creado_en)
    )
    proveedores: dict[uuid.UUID, list[RespuestaProveedor]] = {}
    for conexion in (await sesion_bd.execute(consulta_conexiones)).scalars():
        proveedores.setdefault(conexion.usuario_id, []).append(_proveedor(conexion))
    return [
        RespuestaUsuarioAdministrado(
            id=usuario.id,
            nombre=usuario.nombre,
            nombre_usuario=usuario.nombre_usuario,
            correo=usuario.correo,
            activo=usuario.activo,
            es_administrador=usuario.es_administrador,
            creado_en=usuario.creado_en,
            sesiones_activas=sesiones.get(usuario.id, 0),
            proveedores=proveedores.get(usuario.id, []),
        )
        for usuario in usuarios
    ]


async def _buscar_usuario(sesion_bd: AsyncSession, usuario_id: uuid.UUID) -> Usuario:
    usuario = await sesion_bd.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return usuario


async def _cerrar_sesiones(sesion_bd: AsyncSession, usuario_id: uuid.UUID) -> int:
    resultado = await sesion_bd.execute(
        update(SesionAutenticacion)
        .where(
            SesionAutenticacion.usuario_id == usuario_id,
            SesionAutenticacion.revocado_en.is_(None),
        )
        .values(revocado_en=datetime.now(UTC))
    )
    return resultado.rowcount or 0


def _servidor(url_base: str) -> str:
    return urlsplit(url_base).hostname or url_base


async def _validar(cuenta: CuentaProveedor, cliente: httpx.AsyncClient) -> xtream.InfoCuentaXtream:
    try:
        return await xtream.validar_credenciales(
            cuenta.url_base, cuenta.nombre_usuario, cuenta.contrasena, cliente=cliente
        )
    except xtream.CredencialesXtreamInvalidas as error:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"El proveedor rechazó la cuenta: {error}"
        ) from None
    except xtream.ProveedorNoDisponible as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None


async def _cuenta_por_huella(sesion_bd: AsyncSession, huella: str) -> CuentaProveedor | None:
    consulta = select(CuentaProveedor).where(CuentaProveedor.huella == huella)
    return (await sesion_bd.execute(consulta)).scalar_one_or_none()


async def _cuenta_por_credenciales(
    sesion_bd: AsyncSession,
    url_base: str,
    nombre_usuario: str,
    contrasena: str,
    etiqueta: str | None = None,
    predeterminada: bool = False,
) -> CuentaProveedor:
    existente = await _cuenta_por_huella(
        sesion_bd, cifrado.calcular_huella(url_base, nombre_usuario)
    )
    if existente is not None:
        if existente.contrasena != contrasena:
            existente.poner_credenciales(url_base, nombre_usuario, contrasena)
        return existente
    cuenta = CuentaProveedor(
        etiqueta=etiqueta or _servidor(url_base), predeterminada=predeterminada
    )
    cuenta.poner_credenciales(url_base, nombre_usuario, contrasena)
    sesion_bd.add(cuenta)
    await sesion_bd.flush()
    return cuenta


async def _cuenta_predeterminada(sesion_bd: AsyncSession) -> CuentaProveedor:
    cuenta = await conexion_inicial.cuenta_predeterminada(sesion_bd)
    if cuenta is not None:
        return cuenta
    if not esta_configurada():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No hay cuenta de proveedor predeterminada; elige una o créala",
        )
    return await _cuenta_por_credenciales(
        sesion_bd,
        xtream.normalizar_url_base(configuracion.conexion_inicial_url),
        configuracion.conexion_inicial_usuario,
        configuracion.conexion_inicial_contrasena,
        etiqueta=configuracion.conexion_inicial_etiqueta,
        predeterminada=True,
    )


async def _resolver_cuenta(sesion_bd: AsyncSession, datos: SolicitudProveedor) -> CuentaProveedor:
    if datos.cuenta_id is not None:
        cuenta = await sesion_bd.get(CuentaProveedor, datos.cuenta_id)
        if cuenta is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Cuenta de proveedor no encontrada"
            )
        return cuenta
    if datos.predeterminado:
        return await _cuenta_predeterminada(sesion_bd)
    return await _cuenta_por_credenciales(
        sesion_bd, datos.url_base, datos.nombre_usuario, datos.contrasena
    )


async def _asignar_proveedor(
    sesion_bd: AsyncSession,
    usuario: Usuario,
    datos: SolicitudProveedor,
    cliente: httpx.AsyncClient,
) -> None:
    cuenta = await _resolver_cuenta(sesion_bd, datos)
    info = await _validar(cuenta, cliente)
    cuenta.actualizar_desde_info(info)
    anteriores = select(ConexionXtream.id).where(ConexionXtream.usuario_id == usuario.id)
    for (conexion_id,) in (await sesion_bd.execute(anteriores)).all():
        cache.invalidar(f"conexion:{conexion_id}:")
    await sesion_bd.execute(delete(ConexionXtream).where(ConexionXtream.usuario_id == usuario.id))
    conexion = ConexionXtream.nueva(
        usuario_id=usuario.id,
        etiqueta=cuenta.etiqueta,
        url_base=cuenta.url_base,
        nombre_usuario=cuenta.nombre_usuario,
        contrasena=cuenta.contrasena,
    )
    conexion.cuenta_proveedor_id = cuenta.id
    conexion.actualizar_desde_info(info)
    sesion_bd.add(conexion)


def _repetido() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT, detail="Ese nombre de usuario o correo ya existe"
    )


@router.get("/usuarios", response_model=list[RespuestaUsuarioAdministrado])
async def listar_usuarios(
    _administrador: AdministradorActual, sesion_bd: SesionBD
) -> list[RespuestaUsuarioAdministrado]:
    consulta = select(Usuario).order_by(Usuario.creado_en)
    return await _describir(sesion_bd, list((await sesion_bd.execute(consulta)).scalars()))


@router.post(
    "/usuarios", response_model=RespuestaUsuarioAdministrado, status_code=status.HTTP_201_CREATED
)
async def crear_usuario(
    datos: SolicitudCrearUsuario,
    _administrador: AdministradorActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
) -> RespuestaUsuarioAdministrado:
    usuario = Usuario(
        correo=datos.correo or correo_interno(datos.nombre_usuario),
        hash_contrasena=security.generar_hash_contrasena(datos.contrasena),
        nombre=datos.nombre,
        nombre_usuario=datos.nombre_usuario,
        es_administrador=datos.es_administrador,
    )
    sesion_bd.add(usuario)
    try:
        await sesion_bd.flush()
    except IntegrityError:
        raise _repetido() from None
    await sesion_bd.refresh(usuario)
    sesion_bd.add(Perfil(usuario_id=usuario.id, nombre=datos.nombre[:80]))
    await _asignar_proveedor(sesion_bd, usuario, datos.proveedor, cliente)
    await sesion_bd.commit()
    return (await _describir(sesion_bd, [usuario]))[0]


@router.patch("/usuarios/{usuario_id}", response_model=RespuestaUsuarioAdministrado)
async def actualizar_usuario(
    usuario_id: uuid.UUID,
    datos: SolicitudActualizarUsuario,
    administrador: AdministradorActual,
    sesion_bd: SesionBD,
) -> RespuestaUsuarioAdministrado:
    usuario = await _buscar_usuario(sesion_bd, usuario_id)
    es_uno_mismo = usuario.id == administrador.id
    if es_uno_mismo and (datos.activo is False or datos.es_administrador is False):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivarte ni quitarte el permiso de administrador",
        )
    if datos.nombre is not None:
        usuario.nombre = datos.nombre
    if datos.nombre_usuario is not None:
        usuario.nombre_usuario = datos.nombre_usuario
    if datos.es_administrador is not None:
        usuario.es_administrador = datos.es_administrador
    if datos.activo is not None:
        usuario.activo = datos.activo
        if not datos.activo:
            await _cerrar_sesiones(sesion_bd, usuario.id)
    if datos.contrasena is not None:
        usuario.hash_contrasena = security.generar_hash_contrasena(datos.contrasena)
        if not es_uno_mismo:
            await _cerrar_sesiones(sesion_bd, usuario.id)
    try:
        await sesion_bd.flush()
    except IntegrityError:
        raise _repetido() from None
    await sesion_bd.commit()
    return (await _describir(sesion_bd, [usuario]))[0]


@router.put("/usuarios/{usuario_id}/proveedor", response_model=RespuestaUsuarioAdministrado)
async def cambiar_proveedor(
    usuario_id: uuid.UUID,
    datos: SolicitudProveedor,
    _administrador: AdministradorActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
) -> RespuestaUsuarioAdministrado:
    usuario = await _buscar_usuario(sesion_bd, usuario_id)
    await _asignar_proveedor(sesion_bd, usuario, datos, cliente)
    await sesion_bd.commit()
    return (await _describir(sesion_bd, [usuario]))[0]


@router.post("/usuarios/{usuario_id}/cerrar-sesiones", response_model=RespuestaSesionesCerradas)
async def cerrar_sesiones(
    usuario_id: uuid.UUID, _administrador: AdministradorActual, sesion_bd: SesionBD
) -> RespuestaSesionesCerradas:
    usuario = await _buscar_usuario(sesion_bd, usuario_id)
    cerradas = await _cerrar_sesiones(sesion_bd, usuario.id)
    await sesion_bd.commit()
    return RespuestaSesionesCerradas(cerradas=cerradas)


@router.get("/usuarios/{usuario_id}/sesiones", response_model=list[RespuestaSesionDispositivo])
async def sesiones_del_usuario(
    usuario_id: uuid.UUID, _administrador: AdministradorActual, sesion_bd: SesionBD
) -> list[RespuestaSesionDispositivo]:
    await _buscar_usuario(sesion_bd, usuario_id)
    consulta = (
        select(SesionAutenticacion)
        .where(
            SesionAutenticacion.usuario_id == usuario_id,
            SesionAutenticacion.revocado_en.is_(None),
            SesionAutenticacion.expira_en > datetime.now(UTC),
        )
        .order_by(SesionAutenticacion.ultimo_uso_en.desc())
    )
    return [
        RespuestaSesionDispositivo(
            id=sesion.id,
            nombre_dispositivo=sesion.nombre_dispositivo,
            dispositivo=sesion.dispositivo or {},
            ip_inicio=sesion.ip_inicio,
            ip_ultima=sesion.ip_ultima,
            agente_usuario=sesion.agente_usuario,
            iniciada_en=sesion.iniciada_en,
            ultimo_uso_en=sesion.ultimo_uso_en,
            expira_en=sesion.expira_en,
        )
        for sesion in (await sesion_bd.execute(consulta)).scalars()
    ]


@router.post("/sesiones/{sesion_id}/cerrar", response_model=RespuestaSesionesCerradas)
async def cerrar_una_sesion(
    sesion_id: uuid.UUID, _administrador: AdministradorActual, sesion_bd: SesionBD
) -> RespuestaSesionesCerradas:
    resultado = await sesion_bd.execute(
        update(SesionAutenticacion)
        .where(SesionAutenticacion.id == sesion_id, SesionAutenticacion.revocado_en.is_(None))
        .values(revocado_en=datetime.now(UTC))
    )
    await sesion_bd.commit()
    if not resultado.rowcount:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Esa sesión no existe o ya estaba cerrada"
        )
    return RespuestaSesionesCerradas(cerradas=resultado.rowcount)


async def _describir_cuentas(
    sesion_bd: AsyncSession, cuentas: list[CuentaProveedor]
) -> list[RespuestaCuentaProveedor]:
    consulta = (
        select(ConexionXtream.cuenta_proveedor_id, Usuario.nombre_usuario, Usuario.nombre)
        .join(Usuario, Usuario.id == ConexionXtream.usuario_id)
        .where(ConexionXtream.cuenta_proveedor_id.in_([c.id for c in cuentas]))
        .order_by(Usuario.nombre)
    )
    usuarios: dict[uuid.UUID, list[str]] = {}
    for cuenta_id, nombre_usuario, nombre in (await sesion_bd.execute(consulta)).all():
        usuarios.setdefault(cuenta_id, []).append(nombre_usuario or nombre)
    return [
        RespuestaCuentaProveedor(
            id=cuenta.id,
            etiqueta=cuenta.etiqueta,
            url_base=cuenta.url_base,
            servidor=_servidor(cuenta.url_base),
            nombre_usuario=cuenta.nombre_usuario,
            notas=cuenta.notas,
            predeterminada=cuenta.predeterminada,
            estado_cuenta=cuenta.estado_cuenta,
            expira_en=cuenta.expira_en,
            max_conexiones=cuenta.max_conexiones,
            conexiones_activas=cuenta.conexiones_activas,
            ultima_revision_en=cuenta.ultima_revision_en,
            usuarios=usuarios.get(cuenta.id, []),
        )
        for cuenta in cuentas
    ]


async def _buscar_cuenta(sesion_bd: AsyncSession, cuenta_id: uuid.UUID) -> CuentaProveedor:
    cuenta = await sesion_bd.get(CuentaProveedor, cuenta_id)
    if cuenta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cuenta de proveedor no encontrada")
    return cuenta


async def _solo_una_predeterminada(sesion_bd: AsyncSession, cuenta: CuentaProveedor) -> None:
    await sesion_bd.execute(
        update(CuentaProveedor).where(CuentaProveedor.id != cuenta.id).values(predeterminada=False)
    )


async def _propagar(
    sesion_bd: AsyncSession, cuenta: CuentaProveedor, info: xtream.InfoCuentaXtream | None
) -> None:
    consulta = select(ConexionXtream).where(ConexionXtream.cuenta_proveedor_id == cuenta.id)
    for conexion in (await sesion_bd.execute(consulta)).scalars():
        conexion.etiqueta = cuenta.etiqueta
        conexion.url_base_cifrada = cuenta.url_base_cifrada
        conexion.nombre_usuario_cifrado = cuenta.nombre_usuario_cifrado
        conexion.contrasena_cifrada = cuenta.contrasena_cifrada
        conexion.huella = cuenta.huella
        if info is not None:
            conexion.actualizar_desde_info(info)
        cache.invalidar(f"conexion:{conexion.id}:")


def _cuenta_repetida() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT, detail="Ya existe una cuenta con esa URL y ese usuario"
    )


@router.get("/proveedores", response_model=list[RespuestaCuentaProveedor])
async def listar_cuentas_proveedor(
    _administrador: AdministradorActual, sesion_bd: SesionBD
) -> list[RespuestaCuentaProveedor]:
    consulta = select(CuentaProveedor).order_by(
        CuentaProveedor.predeterminada.desc(), CuentaProveedor.etiqueta
    )
    return await _describir_cuentas(sesion_bd, list((await sesion_bd.execute(consulta)).scalars()))


@router.post(
    "/proveedores", response_model=RespuestaCuentaProveedor, status_code=status.HTTP_201_CREATED
)
async def crear_cuenta_proveedor(
    datos: SolicitudCuentaProveedor,
    _administrador: AdministradorActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
) -> RespuestaCuentaProveedor:
    if await _cuenta_por_huella(
        sesion_bd, cifrado.calcular_huella(datos.url_base, datos.nombre_usuario)
    ):
        raise _cuenta_repetida()
    cuenta = CuentaProveedor(
        etiqueta=datos.etiqueta, notas=datos.notas, predeterminada=datos.predeterminada
    )
    cuenta.poner_credenciales(datos.url_base, datos.nombre_usuario, datos.contrasena)
    if datos.validar:
        cuenta.actualizar_desde_info(await _validar(cuenta, cliente))
    sesion_bd.add(cuenta)
    await sesion_bd.flush()
    if cuenta.predeterminada:
        await _solo_una_predeterminada(sesion_bd, cuenta)
    await sesion_bd.commit()
    return (await _describir_cuentas(sesion_bd, [cuenta]))[0]


@router.patch("/proveedores/{cuenta_id}", response_model=RespuestaCuentaProveedor)
async def actualizar_cuenta_proveedor(
    cuenta_id: uuid.UUID,
    datos: SolicitudActualizarCuentaProveedor,
    _administrador: AdministradorActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
) -> RespuestaCuentaProveedor:
    cuenta = await _buscar_cuenta(sesion_bd, cuenta_id)
    url_base = datos.url_base or cuenta.url_base
    nombre_usuario = datos.nombre_usuario or cuenta.nombre_usuario
    contrasena = datos.contrasena or cuenta.contrasena
    cambian_credenciales = (url_base, nombre_usuario, contrasena) != (
        cuenta.url_base,
        cuenta.nombre_usuario,
        cuenta.contrasena,
    )
    if cambian_credenciales:
        otra = await _cuenta_por_huella(
            sesion_bd, cifrado.calcular_huella(url_base, nombre_usuario)
        )
        if otra is not None and otra.id != cuenta.id:
            raise _cuenta_repetida()
        cuenta.poner_credenciales(url_base, nombre_usuario, contrasena)
    info = None
    if cambian_credenciales and datos.validar:
        info = await _validar(cuenta, cliente)
        cuenta.actualizar_desde_info(info)
    if datos.etiqueta is not None:
        cuenta.etiqueta = datos.etiqueta
    if datos.notas is not None:
        cuenta.notas = datos.notas or None
    if datos.predeterminada is not None:
        cuenta.predeterminada = datos.predeterminada
        if datos.predeterminada:
            await _solo_una_predeterminada(sesion_bd, cuenta)
    await _propagar(sesion_bd, cuenta, info)
    try:
        await sesion_bd.commit()
    except IntegrityError:
        raise _cuenta_repetida() from None
    return (await _describir_cuentas(sesion_bd, [cuenta]))[0]


@router.post("/proveedores/{cuenta_id}/revisar", response_model=RespuestaCuentaProveedor)
async def revisar_cuenta_proveedor(
    cuenta_id: uuid.UUID,
    _administrador: AdministradorActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
) -> RespuestaCuentaProveedor:
    cuenta = await _buscar_cuenta(sesion_bd, cuenta_id)
    info = await _validar(cuenta, cliente)
    cuenta.actualizar_desde_info(info)
    await _propagar(sesion_bd, cuenta, info)
    await sesion_bd.commit()
    return (await _describir_cuentas(sesion_bd, [cuenta]))[0]


@router.delete("/proveedores/{cuenta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_cuenta_proveedor(
    cuenta_id: uuid.UUID, _administrador: AdministradorActual, sesion_bd: SesionBD
) -> None:
    cuenta = await _buscar_cuenta(sesion_bd, cuenta_id)
    usuarios = (await _describir_cuentas(sesion_bd, [cuenta]))[0].usuarios
    if usuarios:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar: la usan {', '.join(usuarios)}",
        )
    await sesion_bd.delete(cuenta)
    await sesion_bd.commit()
