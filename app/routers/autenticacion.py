from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import configuracion
from app.deps import SesionBD, UsuarioActual
from app.models import Perfil, SesionAutenticacion, Usuario
from app.routers.conexiones import ClienteHTTP
from app.schemas.autenticacion import (
    RespuestaTokens,
    RespuestaUsuario,
    SolicitudInicioSesion,
    SolicitudRefresco,
    SolicitudRegistro,
)
from app.services.conexion_inicial import asegurar_conexion_inicial

router = APIRouter(prefix="/auth", tags=["autenticacion"])
_HASH_SENUELO = security.generar_hash_contrasena("contrasena-senuelo-no-se-usa")


def _credenciales_invalidas() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Correo o contraseña incorrectos"
    )


def _token_refresco_invalido() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de refresco inválido, caducado o ya usado",
    )


async def _abrir_sesion(
    sesion_bd: AsyncSession, usuario: Usuario, nombre_dispositivo: str | None
) -> RespuestaTokens:
    token_refresco = security.generar_token_refresco()
    sesion_bd.add(
        SesionAutenticacion(
            usuario_id=usuario.id,
            hash_token_refresco=security.calcular_hash_token_refresco(token_refresco),
            nombre_dispositivo=nombre_dispositivo,
            expira_en=security.caducidad_token_refresco(),
        )
    )
    return RespuestaTokens(
        token_acceso=security.crear_token_acceso(usuario.id),
        token_refresco=token_refresco,
        expira_en_segundos=configuracion.minutos_token_acceso * 60,
        usuario=RespuestaUsuario.model_validate(usuario),
    )


async def _buscar_sesion_por_token(
    sesion_bd: AsyncSession, token_refresco: str
) -> SesionAutenticacion | None:
    hash_token = security.calcular_hash_token_refresco(token_refresco)
    consulta = select(SesionAutenticacion).where(
        SesionAutenticacion.hash_token_refresco == hash_token
    )
    return (await sesion_bd.execute(consulta)).scalar_one_or_none()


@router.post("/registrar", response_model=RespuestaTokens, status_code=status.HTTP_201_CREATED)
async def registrar(
    datos: SolicitudRegistro, sesion_bd: SesionBD, cliente: ClienteHTTP
) -> RespuestaTokens:
    usuario = Usuario(
        correo=datos.correo,
        hash_contrasena=security.generar_hash_contrasena(datos.contrasena),
        nombre=datos.nombre,
    )
    sesion_bd.add(usuario)
    try:
        await sesion_bd.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ese correo ya está registrado"
        ) from None
    await sesion_bd.refresh(usuario)
    sesion_bd.add(Perfil(usuario_id=usuario.id, nombre=datos.nombre[:80]))
    await asegurar_conexion_inicial(sesion_bd, usuario, cliente)
    respuesta = await _abrir_sesion(sesion_bd, usuario, datos.nombre_dispositivo)
    await sesion_bd.commit()
    return respuesta


@router.post("/iniciar-sesion", response_model=RespuestaTokens)
async def iniciar_sesion(datos: SolicitudInicioSesion, sesion_bd: SesionBD) -> RespuestaTokens:
    consulta = select(Usuario).where(func.lower(Usuario.correo) == datos.correo.lower())
    usuario = (await sesion_bd.execute(consulta)).scalar_one_or_none()

    hash_a_comprobar = usuario.hash_contrasena if usuario is not None else _HASH_SENUELO
    contrasena_correcta = security.verificar_contrasena(datos.contrasena, hash_a_comprobar)
    if usuario is None or not contrasena_correcta:
        raise _credenciales_invalidas()
    if not usuario.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta desactivada")

    respuesta = await _abrir_sesion(sesion_bd, usuario, datos.nombre_dispositivo)
    await sesion_bd.commit()
    return respuesta


@router.post("/refrescar", response_model=RespuestaTokens)
async def refrescar(datos: SolicitudRefresco, sesion_bd: SesionBD) -> RespuestaTokens:
    sesion = await _buscar_sesion_por_token(sesion_bd, datos.token_refresco)
    if sesion is None or sesion.revocado_en is not None or sesion.expira_en <= datetime.now(UTC):
        raise _token_refresco_invalido()

    usuario = await sesion_bd.get(Usuario, sesion.usuario_id)
    if usuario is None or not usuario.activo:
        raise _token_refresco_invalido()

    sesion.revocado_en = datetime.now(UTC)
    respuesta = await _abrir_sesion(sesion_bd, usuario, sesion.nombre_dispositivo)
    await sesion_bd.commit()
    return respuesta


@router.post("/cerrar-sesion", status_code=status.HTTP_204_NO_CONTENT)
async def cerrar_sesion(datos: SolicitudRefresco, sesion_bd: SesionBD) -> None:
    sesion = await _buscar_sesion_por_token(sesion_bd, datos.token_refresco)
    if sesion is not None and sesion.revocado_en is None:
        sesion.revocado_en = datetime.now(UTC)
        await sesion_bd.commit()


@router.get("/yo", response_model=RespuestaUsuario)
async def yo(usuario: UsuarioActual) -> RespuestaUsuario:
    return RespuestaUsuario.model_validate(usuario)
