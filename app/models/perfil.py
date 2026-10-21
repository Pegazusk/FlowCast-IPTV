import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Perfil(Base):
    __tablename__ = "perfil"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(80))
    avatar: Mapped[str] = mapped_column(String(40), server_default=text("'01'"))
    es_infantil: Mapped[bool] = mapped_column(server_default=text("false"))
    hash_pin_parental: Mapped[str | None]
    imagen_avatar: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    imagen_tipo: Mapped[str | None] = mapped_column(String(40))
    imagen_actualizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preferencias: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"Perfil(id={self.id}, nombre={self.nombre!r})"
