import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Resena(Base):
    __tablename__ = "resena"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    perfil_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("perfil.id", ondelete="CASCADE"))
    servidor_huella: Mapped[str] = mapped_column(String(64))
    tipo_contenido: Mapped[str] = mapped_column(String(10))
    stream_id: Mapped[str]
    titulo: Mapped[str]
    calificacion: Mapped[int] = mapped_column(SmallInteger)
    texto: Mapped[str | None]
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
