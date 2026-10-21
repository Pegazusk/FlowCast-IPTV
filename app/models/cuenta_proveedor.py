import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app import cifrado
from app.db import Base

if TYPE_CHECKING:
    from app.services.xtream import InfoCuentaXtream


class CuentaProveedor(Base):
    __tablename__ = "cuenta_proveedor"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    etiqueta: Mapped[str] = mapped_column(String(120))
    url_base_cifrada: Mapped[bytes]
    nombre_usuario_cifrado: Mapped[bytes]
    contrasena_cifrada: Mapped[bytes]
    huella: Mapped[str] = mapped_column(unique=True)
    notas: Mapped[str | None] = mapped_column(Text)
    predeterminada: Mapped[bool] = mapped_column(server_default=text("false"))
    estado_cuenta: Mapped[str] = mapped_column(String(20), server_default=text("'desconocido'"))
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_conexiones: Mapped[int | None]
    conexiones_activas: Mapped[int | None]
    ultima_revision_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    @property
    def url_base(self) -> str:
        return cifrado.descifrar(self.url_base_cifrada)

    @property
    def nombre_usuario(self) -> str:
        return cifrado.descifrar(self.nombre_usuario_cifrado)

    @property
    def contrasena(self) -> str:
        return cifrado.descifrar(self.contrasena_cifrada)

    def poner_credenciales(self, url_base: str, nombre_usuario: str, contrasena: str) -> None:
        self.url_base_cifrada = cifrado.cifrar(url_base)
        self.nombre_usuario_cifrado = cifrado.cifrar(nombre_usuario)
        self.contrasena_cifrada = cifrado.cifrar(contrasena)
        self.huella = cifrado.calcular_huella(url_base, nombre_usuario)

    def actualizar_desde_info(self, info: "InfoCuentaXtream") -> None:
        self.estado_cuenta = info.estado_cuenta
        self.expira_en = info.expira_en
        self.max_conexiones = info.max_conexiones
        self.conexiones_activas = info.conexiones_activas
        self.ultima_revision_en = datetime.now(UTC)
