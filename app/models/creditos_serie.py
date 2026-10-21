import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CreditosSerie(Base):
    __tablename__ = "creditos_serie"

    conexion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conexion_xtream.id", ondelete="CASCADE"), primary_key=True
    )
    serie_id: Mapped[str] = mapped_column(primary_key=True)
    segundos: Mapped[float]
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
