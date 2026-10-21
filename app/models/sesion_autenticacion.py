import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.usuario import Usuario


class SesionAutenticacion(Base):
    __tablename__ = "sesion_autenticacion"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    hash_token_refresco: Mapped[str] = mapped_column(unique=True)
    nombre_dispositivo: Mapped[str | None] = mapped_column(String(120))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    iniciada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    ultimo_uso_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    ip_inicio: Mapped[str | None]
    ip_ultima: Mapped[str | None]
    agente_usuario: Mapped[str | None]
    dispositivo: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))

    usuario: Mapped["Usuario"] = relationship(back_populates="sesiones")

    def __repr__(self) -> str:
        return (
            f"SesionAutenticacion(id={self.id}, usuario_id={self.usuario_id}, "
            f"dispositivo={self.nombre_dispositivo!r})"
        )
