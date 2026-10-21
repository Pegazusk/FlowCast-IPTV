import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import cifrado
from app.db import Base

if TYPE_CHECKING:
    from app.models.usuario import Usuario
    from app.services.xtream import InfoCuentaXtream


class ConexionXtream(Base):
    __tablename__ = "conexion_xtream"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    cuenta_proveedor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cuenta_proveedor.id", ondelete="SET NULL")
    )
    etiqueta: Mapped[str] = mapped_column(String(120))
    url_base_cifrada: Mapped[bytes]
    nombre_usuario_cifrado: Mapped[bytes]
    huella: Mapped[str]
    contrasena_cifrada: Mapped[bytes]

    estado_cuenta: Mapped[str] = mapped_column(String(20), server_default=text("'desconocido'"))
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_conexiones: Mapped[int | None]
    zona_horaria_servidor: Mapped[str | None]
    formatos_salida_permitidos: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    ultima_autenticacion_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    usuario: Mapped["Usuario"] = relationship()

    @classmethod
    def nueva(
        cls,
        *,
        usuario_id: uuid.UUID,
        etiqueta: str,
        url_base: str,
        nombre_usuario: str,
        contrasena: str,
    ) -> "ConexionXtream":

        return cls(
            usuario_id=usuario_id,
            etiqueta=etiqueta,
            url_base_cifrada=cifrado.cifrar(url_base),
            nombre_usuario_cifrado=cifrado.cifrar(nombre_usuario),
            huella=cifrado.calcular_huella(url_base, nombre_usuario),
            contrasena_cifrada=cifrado.cifrar(contrasena),
        )

    @property
    def url_base(self) -> str:
        return cifrado.descifrar(self.url_base_cifrada)

    @property
    def nombre_usuario(self) -> str:
        return cifrado.descifrar(self.nombre_usuario_cifrado)

    def actualizar_desde_info(self, info: "InfoCuentaXtream") -> None:
        self.estado_cuenta = info.estado_cuenta
        self.expira_en = info.expira_en
        self.max_conexiones = info.max_conexiones
        self.zona_horaria_servidor = info.zona_horaria_servidor
        self.formatos_salida_permitidos = info.formatos_salida_permitidos
        self.ultima_autenticacion_en = datetime.now(UTC)

    def __repr__(self) -> str:
        return (
            f"ConexionXtream(id={self.id}, etiqueta={self.etiqueta!r}, url_base={self.url_base!r})"
        )
