import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PistasSerie(Base):
    __tablename__ = "pistas_serie"

    perfil_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfil.id", ondelete="CASCADE"), primary_key=True
    )
    conexion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conexion_xtream.id", ondelete="CASCADE"), primary_key=True
    )
    serie_id: Mapped[str] = mapped_column(primary_key=True)
    audio: Mapped[str | None] = mapped_column(String(40))
    subtitulos: Mapped[str | None] = mapped_column(String(40))
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
