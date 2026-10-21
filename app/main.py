import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.config import configuracion
from app.db import motor
from app.deps import SesionBD
from app.routers import (
    administracion,
    autenticacion,
    biblioteca,
    catalogo,
    conexiones,
    control_parental,
    musica,
    perfiles,
    plataformas,
    reproduccion,
    resenas,
)
from app.routers.conexiones import cerrar_clientes
from app.services.precalentar import precalentar


@asynccontextmanager
async def ciclo_vida(_aplicacion: FastAPI) -> AsyncIterator[None]:
    async with motor.connect() as conexion:
        await conexion.execute(text("SELECT 1"))
    tarea = asyncio.create_task(precalentar()) if configuracion.precalentar_catalogo else None
    yield
    if tarea is not None:
        tarea.cancel()
    await cerrar_clientes()
    await motor.dispose()


aplicacion = FastAPI(
    title=configuracion.nombre_app,
    version="0.1.0",
    lifespan=ciclo_vida,
    debug=configuracion.depuracion,
    docs_url="/docs" if configuracion.documentacion_publica else None,
    redoc_url="/redoc" if configuracion.documentacion_publica else None,
    openapi_url="/openapi.json" if configuracion.documentacion_publica else None,
)

ORIGENES_DE_APPS_INSTALADAS = r"^(null|file://.*|app://.*)$"
CABECERAS_DE_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

aplicacion.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion.lista_origenes,
    allow_origin_regex=ORIGENES_DE_APPS_INSTALADAS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@aplicacion.middleware("http")
async def cabeceras_de_seguridad(
    peticion: Request, siguiente: Callable[[Request], Awaitable[Response]]
) -> Response:
    respuesta = await siguiente(peticion)
    for nombre, valor in CABECERAS_DE_SEGURIDAD.items():
        respuesta.headers.setdefault(nombre, valor)
    return respuesta


aplicacion.include_router(autenticacion.router)
aplicacion.include_router(conexiones.router)
aplicacion.include_router(catalogo.router)
aplicacion.include_router(reproduccion.router)
aplicacion.include_router(perfiles.router)
aplicacion.include_router(biblioteca.router)
aplicacion.include_router(resenas.router)
aplicacion.include_router(musica.router)
aplicacion.include_router(control_parental.router)
aplicacion.include_router(administracion.router)
aplicacion.include_router(plataformas.router)

PAGINA_ADMINISTRACION = Path(__file__).resolve().parent / "static" / "admin.html"


@aplicacion.get("/admin", include_in_schema=False)
async def pagina_administracion() -> FileResponse:
    return FileResponse(PAGINA_ADMINISTRACION, headers={"Cache-Control": "no-store"})


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
