import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProgresoReproduccion(Base):
    __tablename__ = "progreso_reproduccion"

    perfil_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfil.id", ondelete="CASCADE"), primary_key=True
    )
    conexion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conexion_xtream.id", ondelete="CASCADE"), primary_key=True
    )
    tipo_contenido: Mapped[str] = mapped_column(String(10), primary_key=True)
    stream_id: Mapped[str] = mapped_column(primary_key=True)
    serie_id: Mapped[str | None]
    titulo: Mapped[str]
    url_portada: Mapped[str | None]
    posicion_segundos: Mapped[float] = mapped_column(
        Numeric(10, 3, asdecimal=False), server_default=text("0")
    )
    duracion_segundos: Mapped[float | None] = mapped_column(Numeric(10, 3, asdecimal=False))
    completado: Mapped[bool] = mapped_column(server_default=text("false"))
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
