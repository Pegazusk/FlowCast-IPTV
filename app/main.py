from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.config import configuracion
from app.db import motor
from app.deps import SesionBD
from app.routers import (
    autenticacion,
    biblioteca,
    catalogo,
    conexiones,
    control_parental,
    musica,
    perfiles,
    reproduccion,
    resenas,
)


@asynccontextmanager
async def ciclo_vida(_aplicacion: FastAPI) -> AsyncIterator[None]:
    async with motor.connect() as conexion:
        await conexion.execute(text("SELECT 1"))
    yield
    await motor.dispose()


aplicacion = FastAPI(
    title=configuracion.nombre_app,
    version="0.1.0",
    lifespan=ciclo_vida,
    debug=configuracion.depuracion,
)

aplicacion.include_router(autenticacion.router)
aplicacion.include_router(conexiones.router)
aplicacion.include_router(catalogo.router)
aplicacion.include_router(reproduccion.router)
aplicacion.include_router(perfiles.router)
aplicacion.include_router(biblioteca.router)
aplicacion.include_router(resenas.router)
aplicacion.include_router(musica.router)
aplicacion.include_router(control_parental.router)


@aplicacion.get("/salud", tags=["salud"])
async def salud() -> dict[str, str]:
    return {"estado": "ok"}


@aplicacion.get("/salud/bd", tags=["salud"])
async def salud_bd(sesion_bd: SesionBD) -> dict[str, str]:
    try:
        await sesion_bd.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="PostgreSQL no responde") from error
    return {"estado": "ok", "base_datos": "ok"}
