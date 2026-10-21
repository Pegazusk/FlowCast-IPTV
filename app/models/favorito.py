import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Favorito(Base):
    __tablename__ = "favorito"

    perfil_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfil.id", ondelete="CASCADE"), primary_key=True
    )
    conexion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conexion_xtream.id", ondelete="CASCADE"), primary_key=True
    )
    tipo_contenido: Mapped[str] = mapped_column(String(10), primary_key=True)
    stream_id: Mapped[str] = mapped_column(primary_key=True)
    titulo: Mapped[str]
    url_portada: Mapped[str | None]
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
