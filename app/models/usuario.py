import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.sesion_autenticacion import SesionAutenticacion


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    correo: Mapped[str]
    hash_contrasena: Mapped[str]
    hash_pin_parental: Mapped[str | None]
    nombre: Mapped[str] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(server_default=text("true"))
    nombre_usuario: Mapped[str | None]
    es_administrador: Mapped[bool] = mapped_column(server_default=text("false"))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    sesiones: Mapped[list["SesionAutenticacion"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"Usuario(id={self.id}, correo={self.correo!r})"
