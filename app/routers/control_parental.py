import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app import security
from app.deps import SesionBD, UsuarioActual
from app.models import CategoriaBloqueada, Usuario
from app.routers.catalogo import (
    SEGUNDOS_LISTAS,
    _consultar,
    cargar_bloqueos,
    obtener_conexion_propia,
)
from app.routers.conexiones import ClienteHTTP
from app.schemas.control_parental import (
    CategoriaControl,
    EstadoControlParental,
    RespuestaBloqueoCategoria,
    RespuestaVerificarPin,
    SolicitudBloqueoCategoria,
    SolicitudPin,
    SolicitudQuitarPin,
    SolicitudVerificarPin,
)
from app.services import control_parental, xtream

router = APIRouter(prefix="/control-parental", tags=["control-parental"])


def _estado(usuario: Usuario) -> EstadoControlParental:
    return EstadoControlParental(tiene_pin=usuario.hash_pin_parental is not None)


def _autorizar_cambio(usuario: Usuario, pin_actual: str | None, contrasena: str | None) -> None:
    if usuario.hash_pin_parental is None:
        return
    if pin_actual and security.verificar_contrasena(pin_actual, usuario.hash_pin_parental):
        return
    if contrasena and security.verificar_contrasena(contrasena, usuario.hash_contrasena):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail="Para cambiar el PIN escribe el PIN actual o la contraseña de la cuenta",
    )


@router.get("", response_model=EstadoControlParental)
async def estado(usuario: UsuarioActual) -> EstadoControlParental:
    return _estado(usuario)


@router.put("/pin", response_model=EstadoControlParental)
async def guardar_pin(
    datos: SolicitudPin, usuario: UsuarioActual, sesion_bd: SesionBD
) -> EstadoControlParental:
    _autorizar_cambio(usuario, datos.pin_actual, datos.contrasena)
    usuario.hash_pin_parental = security.generar_hash_contrasena(datos.pin_nuevo)
    await sesion_bd.commit()
    control_parental.registrar_intento(usuario.id, exito=True)
    return _estado(usuario)


@router.post("/pin/quitar", response_model=EstadoControlParental)
async def quitar_pin(
    datos: SolicitudQuitarPin, usuario: UsuarioActual, sesion_bd: SesionBD
) -> EstadoControlParental:
    if usuario.hash_pin_parental is None:
        return _estado(usuario)
    _autorizar_cambio(usuario, datos.pin_actual, datos.contrasena)
    usuario.hash_pin_parental = None
    await sesion_bd.commit()
    return _estado(usuario)


@router.post("/pin/verificar", response_model=RespuestaVerificarPin)
async def verificar_pin(
    datos: SolicitudVerificarPin, usuario: UsuarioActual
) -> RespuestaVerificarPin:
    if usuario.hash_pin_parental is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="La cuenta no tiene PIN parental")
    castigo = control_parental.segundos_de_castigo(usuario.id)
    if castigo:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos. Espera {castigo} segundos",
        )
    valido = security.verificar_contrasena(datos.pin, usuario.hash_pin_parental)
    control_parental.registrar_intento(usuario.id, exito=valido)
    if not valido:
        return RespuestaVerificarPin(valido=False)
    return RespuestaVerificarPin(
        valido=True,
        token_desbloqueo=control_parental.crear_token_desbloqueo(usuario.id),
        segundos_validez=control_parental.MINUTOS_DESBLOQUEO * 60,
    )


@router.get("/categorias", response_model=list[CategoriaControl])
async def listar_categorias(
    usuario: UsuarioActual,
    sesion_bd: SesionBD,
    cliente: ClienteHTTP,
    conexion_id: Annotated[uuid.UUID, Query()],
) -> list[CategoriaControl]:
    contexto = await obtener_conexion_propia(conexion_id, usuario, sesion_bd)
    bloqueos = await cargar_bloqueos(sesion_bd, usuario.id, conexion_id)
    resultado: list[CategoriaControl] = []
    for tipo in ("en_vivo", "pelicula", "serie"):
        categorias = await _consultar(
            contexto.clave("categorias", tipo),
            SEGUNDOS_LISTAS,
            lambda tipo=tipo: xtream.obtener_categorias(
                contexto.credenciales, tipo, cliente=cliente
            ),
        )
        for categoria in categorias:
            es_adulta = control_parental.es_nombre_adulto(categoria.nombre)
            resultado.append(
                CategoriaControl(
                    tipo_contenido=tipo,
                    id=categoria.id,
                    nombre=categoria.nombre,
                    es_adulta=es_adulta,
                    bloqueada=bloqueos.get((tipo, categoria.id), es_adulta),
                )
            )
    return resultado


@router.put("/categorias", response_model=RespuestaBloqueoCategoria)
async def bloquear_categoria(
    datos: SolicitudBloqueoCategoria, usuario: UsuarioActual, sesion_bd: SesionBD
) -> RespuestaBloqueoCategoria:
    await obtener_conexion_propia(datos.conexion_id, usuario, sesion_bd)
    clave = (usuario.id, datos.conexion_id, datos.tipo_contenido, datos.categoria_id)
    fila = await sesion_bd.get(CategoriaBloqueada, clave)
    if fila is None:
        fila = CategoriaBloqueada(
            usuario_id=usuario.id,
            conexion_id=datos.conexion_id,
            tipo_contenido=datos.tipo_contenido,
            categoria_id=datos.categoria_id,
            bloqueada=datos.bloqueada,
        )
        sesion_bd.add(fila)
    else:
        fila.bloqueada = datos.bloqueada
    await sesion_bd.commit()
    return RespuestaBloqueoCategoria(
        tipo_contenido=datos.tipo_contenido,
        categoria_id=datos.categoria_id,
        bloqueada=datos.bloqueada,
    )


@router.get("/categorias/bloqueadas", response_model=list[RespuestaBloqueoCategoria])
async def listar_bloqueos_manuales(
    usuario: UsuarioActual, sesion_bd: SesionBD, conexion_id: Annotated[uuid.UUID, Query()]
) -> list[RespuestaBloqueoCategoria]:
    filas = (
        await sesion_bd.execute(
            select(CategoriaBloqueada).where(
                CategoriaBloqueada.usuario_id == usuario.id,
                CategoriaBloqueada.conexion_id == conexion_id,
            )
        )
    ).scalars()
    return [
        RespuestaBloqueoCategoria(
            tipo_contenido=f.tipo_contenido, categoria_id=f.categoria_id, bloqueada=f.bloqueada
        )
        for f in filas
    ]
