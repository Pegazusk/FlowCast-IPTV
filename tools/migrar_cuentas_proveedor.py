import asyncio
from urllib.parse import urlsplit

from sqlalchemy import select, text

from app import cifrado
from app.config import configuracion
from app.db import FabricaSesiones, motor
from app.models import ConexionXtream, CuentaProveedor
from app.services import xtream

DDL = [
    """CREATE TABLE IF NOT EXISTS cuenta_proveedor (
        id                     uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
        etiqueta               varchar(120) NOT NULL,
        url_base_cifrada       bytea        NOT NULL,
        nombre_usuario_cifrado bytea        NOT NULL,
        contrasena_cifrada     bytea        NOT NULL,
        huella                 text         NOT NULL UNIQUE,
        notas                  text,
        predeterminada         boolean      NOT NULL DEFAULT false,
        estado_cuenta          varchar(20)  NOT NULL DEFAULT 'desconocido',
        expira_en              timestamptz,
        max_conexiones         integer,
        conexiones_activas     integer,
        ultima_revision_en     timestamptz,
        creado_en              timestamptz  NOT NULL DEFAULT now()
    )""",
    """ALTER TABLE conexion_xtream ADD COLUMN IF NOT EXISTS cuenta_proveedor_id uuid
        REFERENCES cuenta_proveedor(id) ON DELETE SET NULL""",
]


async def migrar() -> None:
    async with motor.begin() as conexion_bd:
        for sentencia in DDL:
            await conexion_bd.execute(text(sentencia))
    huella_predeterminada = None
    if configuracion.conexion_inicial_url and configuracion.conexion_inicial_usuario:
        huella_predeterminada = cifrado.calcular_huella(
            xtream.normalizar_url_base(configuracion.conexion_inicial_url),
            configuracion.conexion_inicial_usuario,
        )
    async with FabricaSesiones() as sesion_bd:
        cuentas = {c.huella: c for c in (await sesion_bd.execute(select(CuentaProveedor))).scalars()}
        conexiones = (await sesion_bd.execute(select(ConexionXtream))).scalars().all()
        creadas = ligadas = 0
        for conexion in conexiones:
            cuenta = cuentas.get(conexion.huella)
            if cuenta is None:
                es_predeterminada = conexion.huella == huella_predeterminada
                cuenta = CuentaProveedor(
                    etiqueta=(configuracion.conexion_inicial_etiqueta if es_predeterminada else None)
                    or conexion.etiqueta
                    or urlsplit(conexion.url_base).hostname
                    or "Proveedor",
                    url_base_cifrada=conexion.url_base_cifrada,
                    nombre_usuario_cifrado=conexion.nombre_usuario_cifrado,
                    contrasena_cifrada=conexion.contrasena_cifrada,
                    huella=conexion.huella,
                    predeterminada=es_predeterminada,
                    estado_cuenta=conexion.estado_cuenta,
                    expira_en=conexion.expira_en,
                    max_conexiones=conexion.max_conexiones,
                )
                sesion_bd.add(cuenta)
                await sesion_bd.flush()
                cuentas[cuenta.huella] = cuenta
                creadas += 1
            if conexion.cuenta_proveedor_id != cuenta.id:
                conexion.cuenta_proveedor_id = cuenta.id
                ligadas += 1
        await sesion_bd.commit()
        print(f"Cuentas de proveedor creadas: {creadas}; conexiones ligadas: {ligadas}")
        for cuenta in cuentas.values():
            print(f" - {cuenta.etiqueta} ({urlsplit(cuenta.url_base).hostname})"
                  f"{' · predeterminada' if cuenta.predeterminada else ''}")
    await motor.dispose()


if __name__ == "__main__":
    asyncio.run(migrar())
