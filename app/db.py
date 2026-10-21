from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import configuracion

motor = create_async_engine(
    str(configuracion.url_base_datos),
    echo=configuracion.depuracion,
    pool_pre_ping=True,
)


FabricaSesiones = async_sessionmaker(motor, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def obtener_sesion_bd() -> AsyncIterator[AsyncSession]:
    async with FabricaSesiones() as sesion_bd:
        yield sesion_bd
