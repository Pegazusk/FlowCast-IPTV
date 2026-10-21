import logging

import httpx2 as httpx
from sqlalchemy import select

from app import cifrado
from app.db import FabricaSesiones
from app.models import ConexionXtream
from app.services import cache, xtream

SEGUNDOS_ESPERA = 120.0
SEGUNDOS_LISTAS = 300

registro = logging.getLogger("flowcast.precalentar")


async def precalentar() -> None:
    async with FabricaSesiones() as sesion_bd:
        conexiones = list((await sesion_bd.execute(select(ConexionXtream))).scalars())
    vistas: set[str] = set()
    async with httpx.AsyncClient(
        timeout=SEGUNDOS_ESPERA, headers=xtream.CABECERAS, follow_redirects=True
    ) as cliente:
        for conexion in conexiones:
            if conexion.huella in vistas:
                continue
            vistas.add(conexion.huella)
            credenciales = xtream.CredencialesXtream(
                url_base=conexion.url_base,
                nombre_usuario=conexion.nombre_usuario,
                contrasena=cifrado.descifrar(conexion.contrasena_cifrada),
            )
            await _precalentar_conexion(conexion, credenciales, cliente, conexiones)


async def _precalentar_conexion(conexion, credenciales, cliente, conexiones) -> None:
    gemelas = [c.id for c in conexiones if c.huella == conexion.huella]
    tareas = {
        "peliculas": xtream.obtener_peliculas(credenciales, None, cliente=cliente),
        "series": xtream.obtener_series(credenciales, None, cliente=cliente),
        "canales": xtream.obtener_canales(credenciales, None, cliente=cliente),
    }
    for nombre, tarea in tareas.items():
        try:
            lista = await tarea
        except (TimeoutError, xtream.ErrorXtream) as error:
            registro.warning("No se pudo precalentar %s: %s", nombre, error)
            continue
        for conexion_id in gemelas:
            cache.guardar_con_respaldo(
                f"conexion:{conexion_id}:{nombre}:todas", lista, SEGUNDOS_LISTAS
            )
        registro.warning("Precalentado %s: %d elementos", nombre, len(lista))
