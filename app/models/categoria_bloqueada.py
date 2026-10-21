import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CategoriaBloqueada(Base):
    __tablename__ = "categoria_bloqueada"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    conexion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conexion_xtream.id", ondelete="CASCADE"), primary_key=True
    )
    tipo_contenido: Mapped[str] = mapped_column(String(10), primary_key=True)
    categoria_id: Mapped[str] = mapped_column(primary_key=True)
    bloqueada: Mapped[bool]
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
