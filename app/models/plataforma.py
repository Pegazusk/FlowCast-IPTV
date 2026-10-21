from datetime import datetime

from sqlalchemy import ARRAY, DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Plataforma(Base):
    __tablename__ = "plataforma"

    clave: Mapped[str] = mapped_column(String(30), primary_key=True)
    nombre: Mapped[str]
    logo: Mapped[str | None]
    orden: Mapped[int] = mapped_column(server_default=text("1000"))


class DisponibilidadTmdb(Base):
    __tablename__ = "disponibilidad_tmdb"

    tipo_contenido: Mapped[str] = mapped_column(String(10), primary_key=True)
    tmdb_id: Mapped[str] = mapped_column(primary_key=True)
    plataformas: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    consultado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
