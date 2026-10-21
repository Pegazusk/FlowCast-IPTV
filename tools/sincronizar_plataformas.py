import asyncio
import sys
import time
from datetime import UTC, datetime

import httpx2 as httpx

from app.config import configuracion
from app.db import FabricaSesiones, motor
from app.services import plataformas, tmdb, xtream


def credenciales_del_env() -> xtream.CredencialesXtream:
    return xtream.CredencialesXtream(
        url_base=xtream.normalizar_url_base(configuracion.conexion_inicial_url),
        nombre_usuario=configuracion.conexion_inicial_usuario,
        contrasena=configuracion.conexion_inicial_contrasena,
    )


async def principal() -> int:
    if not tmdb.disponible():
        print("Falta TMDB_CLAVE_API en el .env")
        return 1
    inicio = time.monotonic()
    print(f"=== Sincronización del {datetime.now(UTC).astimezone():%Y-%m-%d %H:%M} ===", flush=True)
    credenciales = credenciales_del_env()
    async with httpx.AsyncClient(
        timeout=xtream.TIEMPO_ESPERA_SEGUNDOS * 4, headers=xtream.CABECERAS, follow_redirects=True
    ) as cliente_proveedor:
        peliculas = await xtream.obtener_peliculas(credenciales, None, cliente=cliente_proveedor)
        series = await xtream.obtener_series(credenciales, None, cliente=cliente_proveedor)
    titulos = {("pelicula", p.tmdb_id) for p in peliculas if p.tmdb_id}
    titulos |= {("serie", s.tmdb_id) for s in series if s.tmdb_id}
    print(
        f"Catálogo: {len(peliculas)} películas y {len(series)} series; "
        f"{len(titulos)} títulos distintos con tmdb_id"
    )

    def avisar(hechos: int, total: int) -> None:
        if hechos % 1000 < plataformas.TAMANO_LOTE or hechos == total:
            minutos = (time.monotonic() - inicio) / 60
            print(f"  {hechos}/{total} consultados ({minutos:.1f} min)", flush=True)

    async with FabricaSesiones() as sesion_bd, httpx.AsyncClient(timeout=20) as cliente_tmdb:
        conocidas = await plataformas.actualizar_catalogo_plataformas(sesion_bd, cliente_tmdb)
        print(f"Plataformas de México reconocidas en TMDB: {conocidas}")
        faltan = await plataformas.pendientes(sesion_bd, titulos)
        print(
            f"Por consultar (nuevos o de hace más de {plataformas.DIAS_VIGENCIA} días): {len(faltan)}"
        )
        await plataformas.sincronizar(sesion_bd, faltan, cliente_tmdb, avisar)
        disponibles = await plataformas.disponibilidad(sesion_bd)
    await motor.dispose()

    conteo: dict[str, int] = {}
    for claves in disponibles.values():
        for clave in claves:
            conteo[clave] = conteo.get(clave, 0) + 1
    print(f"\nListo en {(time.monotonic() - inicio) / 60:.1f} min. Títulos por plataforma:")
    for clave, total in sorted(conteo.items(), key=lambda par: -par[1]):
        print(f"  {plataformas.nombre_de(clave):14} {total}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
