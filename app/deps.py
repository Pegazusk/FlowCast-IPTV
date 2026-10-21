from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.db import obtener_sesion_bd
from app.models import Usuario

SesionBD = Annotated[AsyncSession, Depends(obtener_sesion_bd)]

_esquema_bearer = HTTPBearer(auto_error=False)


def _no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def obtener_usuario_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)],
    sesion_bd: SesionBD,
) -> Usuario:
    if credenciales is None:
        raise _no_autorizado("Falta el token de acceso")
    try:
        usuario_id = security.decodificar_token_acceso(credenciales.credentials)
    except jwt.ExpiredSignatureError:
        raise _no_autorizado("El token de acceso caducó") from None
    except jwt.InvalidTokenError:
        raise _no_autorizado("Token de acceso inválido") from None

    usuario = await sesion_bd.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        raise _no_autorizado("Usuario inexistente o desactivado")
    return usuario


UsuarioActual = Annotated[Usuario, Depends(obtener_usuario_actual)]


async def obtener_administrador(usuario: UsuarioActual) -> Usuario:
    if not usuario.es_administrador:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Solo para administradores"
        )
    return usuario


AdministradorActual = Annotated[Usuario, Depends(obtener_administrador)]
