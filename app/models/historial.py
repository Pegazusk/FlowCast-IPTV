import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Historial(Base):
    __tablename__ = "historial"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    perfil_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("perfil.id", ondelete="CASCADE"))
    conexion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conexion_xtream.id", ondelete="CASCADE")
    )
    tipo_contenido: Mapped[str] = mapped_column(String(10))
    stream_id: Mapped[str]
    titulo: Mapped[str]
    url_portada: Mapped[str | None]
    reproducido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
