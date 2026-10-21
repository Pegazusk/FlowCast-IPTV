import asyncio
import getpass
import re
import sys

from sqlalchemy import func, select

from app import security
from app.db import FabricaSesiones, motor
from app.models import Perfil, Usuario
from app.schemas.administracion import correo_interno
from app.schemas.autenticacion import PATRON_NOMBRE_USUARIO


def pedir_nombre_usuario() -> str:
    while True:
        valor = input("Nombre de usuario del administrador: ").strip().lower()
        if re.fullmatch(PATRON_NOMBRE_USUARIO, valor):
            return valor
        print("Usa de 3 a 40 caracteres: minúsculas, números, punto, guion o guion bajo.")


def pedir_contrasena() -> str:
    while True:
        primera = getpass.getpass("Contraseña (mínimo 8): ")
        if len(primera) < 8:
            print("Debe tener al menos 8 caracteres.")
            continue
        if getpass.getpass("Repite la contraseña: ") == primera:
            return primera
        print("No coinciden, inténtalo de nuevo.")


async def buscar(sesion_bd, columna, valor: str) -> Usuario | None:
    consulta = select(Usuario).where(func.lower(columna) == valor.lower())
    return (await sesion_bd.execute(consulta)).scalar_one_or_none()


async def principal() -> int:
    print("Crear o promover un administrador de FlowCast\n")
    nombre_usuario = pedir_nombre_usuario()
    async with FabricaSesiones() as sesion_bd:
        usuario = await buscar(sesion_bd, Usuario.nombre_usuario, nombre_usuario)
        if usuario is None:
            correo = input(
                "Si ya tienes cuenta (por ejemplo de la app Android), escribe su correo; "
                "si no, deja vacío para crear una nueva: "
            ).strip()
            if correo:
                usuario = await buscar(sesion_bd, Usuario.correo, correo)
                if usuario is None:
                    print(f"No existe ninguna cuenta con el correo {correo}.")
                    return 1

        if usuario is not None:
            usuario.nombre_usuario = nombre_usuario
            usuario.es_administrador = True
            usuario.activo = True
            if input("¿Quieres cambiarle la contraseña? (s/N): ").strip().lower() == "s":
                usuario.hash_contrasena = security.generar_hash_contrasena(pedir_contrasena())
            accion = "promovida a administrador"
        else:
            nombre = ""
            while len(nombre) < 2:
                nombre = input("Nombre para mostrar: ").strip()
            usuario = Usuario(
                correo=correo_interno(nombre_usuario),
                hash_contrasena=security.generar_hash_contrasena(pedir_contrasena()),
                nombre=nombre[:120],
                nombre_usuario=nombre_usuario,
                es_administrador=True,
            )
            sesion_bd.add(usuario)
            await sesion_bd.flush()
            sesion_bd.add(Perfil(usuario_id=usuario.id, nombre=nombre[:80]))
            accion = "creada como administrador"

        await sesion_bd.commit()
    await motor.dispose()
    print(f"\nListo: la cuenta «{nombre_usuario}» fue {accion}.")
    print("Entra en http://<IP del backend>:8000/admin con ese usuario.")
    return 0


if __name__ == "__main__":
    if not sys.stdin.isatty():
        print("Este comando hace preguntas: córrelo en tu propia Terminal (Terminal.app o PyCharm).")
        sys.exit(2)
    try:
        sys.exit(asyncio.run(principal()))
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado, no se guardó nada.")
        sys.exit(1)
