from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, or_, select
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
from app.services import limite_acceso
from app.services.conexion_inicial import asegurar_conexion_inicial

router = APIRouter(prefix="/auth", tags=["autenticacion"])
_HASH_SENUELO = security.generar_hash_contrasena("contrasena-senuelo-no-se-usa")


def _credenciales_invalidas() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos"
    )


def _token_refresco_invalido() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de refresco inválido, caducado o ya usado",
    )


def ip_de(peticion: Request) -> str | None:
    if configuracion.confiar_proxy:
        reenviada = peticion.headers.get("x-forwarded-for")
        if reenviada:
            return reenviada.split(",")[-1].strip()[:64]
    return peticion.client.host[:64] if peticion.client else None


async def _abrir_sesion(
    sesion_bd: AsyncSession,
    usuario: Usuario,
    nombre_dispositivo: str | None,
    peticion: Request,
    dispositivo: dict[str, Any] | None = None,
    anterior: SesionAutenticacion | None = None,
) -> RespuestaTokens:
    token_refresco = security.generar_token_refresco()
    ahora = datetime.now(UTC)
    ip = ip_de(peticion)
    agente = (peticion.headers.get("user-agent") or "")[:300] or None
    sesion_bd.add(
        SesionAutenticacion(
            usuario_id=usuario.id,
            hash_token_refresco=security.calcular_hash_token_refresco(token_refresco),
            nombre_dispositivo=nombre_dispositivo,
            expira_en=security.caducidad_token_refresco(),
            iniciada_en=anterior.iniciada_en if anterior else ahora,
            ultimo_uso_en=ahora,
            ip_inicio=anterior.ip_inicio if anterior else ip,
            ip_ultima=ip,
            agente_usuario=agente or (anterior.agente_usuario if anterior else None),
            dispositivo=dispositivo or (anterior.dispositivo if anterior else {}) or {},
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
    datos: SolicitudRegistro, sesion_bd: SesionBD, cliente: ClienteHTTP, peticion: Request
) -> RespuestaTokens:
    if not configuracion.registro_abierto:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro está cerrado; pide una cuenta al administrador",
        )
    usuario = Usuario(
        correo=datos.correo,
        hash_contrasena=security.generar_hash_contrasena(datos.contrasena),
        nombre=datos.nombre,
        nombre_usuario=datos.nombre_usuario,
    )
    sesion_bd.add(usuario)
    try:
        await sesion_bd.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese correo o nombre de usuario ya está registrado",
        ) from None
    await sesion_bd.refresh(usuario)
    sesion_bd.add(Perfil(usuario_id=usuario.id, nombre=datos.nombre[:80]))
    await asegurar_conexion_inicial(sesion_bd, usuario, cliente)
    respuesta = await _abrir_sesion(sesion_bd, usuario, datos.nombre_dispositivo, peticion)
    await sesion_bd.commit()
    return respuesta


@router.post("/iniciar-sesion", response_model=RespuestaTokens)
async def iniciar_sesion(
    datos: SolicitudInicioSesion, sesion_bd: SesionBD, peticion: Request
) -> RespuestaTokens:
    identificador = datos.identificador
    ip = ip_de(peticion)
    espera = limite_acceso.segundos_de_espera(identificador, ip)
    if espera:
        minutos = max(1, round(espera / 60))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} min",
            headers={"Retry-After": str(espera)},
        )
    consulta = select(Usuario).where(
        or_(
            func.lower(Usuario.nombre_usuario) == identificador,
            func.lower(Usuario.correo) == identificador,
        )
    )
    usuario = (await sesion_bd.execute(consulta)).scalar_one_or_none()

    hash_a_comprobar = usuario.hash_contrasena if usuario is not None else _HASH_SENUELO
    contrasena_correcta = security.verificar_contrasena(datos.contrasena, hash_a_comprobar)
    if usuario is None or not contrasena_correcta:
        limite_acceso.registrar_fallo(identificador, ip)
        raise _credenciales_invalidas()
    limite_acceso.registrar_exito(identificador)
    if not usuario.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta desactivada")

    respuesta = await _abrir_sesion(
        sesion_bd, usuario, datos.nombre_dispositivo, peticion, datos.dispositivo
    )
    await sesion_bd.commit()
    return respuesta


@router.post("/refrescar", response_model=RespuestaTokens)
async def refrescar(
    datos: SolicitudRefresco, sesion_bd: SesionBD, peticion: Request
) -> RespuestaTokens:
    sesion = await _buscar_sesion_por_token(sesion_bd, datos.token_refresco)
    if sesion is None or sesion.revocado_en is not None or sesion.expira_en <= datetime.now(UTC):
        raise _token_refresco_invalido()

    usuario = await sesion_bd.get(Usuario, sesion.usuario_id)
    if usuario is None or not usuario.activo:
        raise _token_refresco_invalido()

    sesion.revocado_en = datetime.now(UTC)
    respuesta = await _abrir_sesion(
        sesion_bd, usuario, sesion.nombre_dispositivo, peticion, datos.dispositivo, sesion
    )
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
