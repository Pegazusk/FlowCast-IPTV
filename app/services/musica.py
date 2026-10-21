import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4

from app.config import configuracion

EXTENSIONES = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".wav", ".aac"}
TIPOS_MIME = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
}
NOMBRES_PORTADA = (
    "cover.jpg",
    "cover.png",
    "folder.jpg",
    "folder.png",
    "portada.jpg",
    "portada.png",
)
SEGUNDOS_FIRMA = 24 * 3600


@dataclass(frozen=True)
class Cancion:
    id: str
    titulo: str
    artista: str
    album: str
    album_id: str
    numero_pista: int | None
    duracion_segundos: float | None
    anio: int | None
    genero: str | None
    ruta: Path
    tiene_portada: bool


@dataclass(frozen=True)
class Album:
    id: str
    titulo: str
    artista: str
    anio: int | None
    canciones: tuple[Cancion, ...]

    @property
    def duracion_segundos(self) -> float:
        return sum(c.duracion_segundos or 0 for c in self.canciones)

    @property
    def tiene_portada(self) -> bool:
        return any(c.tiene_portada for c in self.canciones)


@dataclass(frozen=True)
class Indice:
    carpeta: Path | None
    canciones: dict[str, Cancion]
    albumes: dict[str, Album]
    escaneado_en: float


_indice: Indice | None = None
_candado = threading.Lock()


def carpeta_configurada() -> Path | None:
    if not configuracion.musica_carpeta:
        return None
    ruta = Path(configuracion.musica_carpeta).expanduser()
    if not ruta.is_absolute():
        ruta = Path(__file__).resolve().parent.parent.parent / ruta
    return ruta if ruta.is_dir() else None


def _id_de(texto: str) -> str:
    return hashlib.sha1(texto.encode()).hexdigest()[:16]


def _primero(etiquetas: object, clave: str) -> str | None:
    try:
        valor = etiquetas.get(clave)
    except (KeyError, ValueError):
        return None
    if not valor:
        return None
    texto = str(valor[0] if isinstance(valor, list) else valor).strip()
    return texto or None


def _entero(texto: str | None) -> int | None:
    if not texto:
        return None
    try:
        return int(texto.split("/")[0][:4])
    except ValueError:
        return None


def _portada_incrustada(ruta: Path) -> tuple[bytes, str] | None:
    try:
        sufijo = ruta.suffix.lower()
        if sufijo == ".mp3":
            imagenes = ID3(ruta).getall("APIC")
            if imagenes:
                return bytes(imagenes[0].data), imagenes[0].mime or "image/jpeg"
        elif sufijo == ".flac":
            imagenes = FLAC(ruta).pictures
            if imagenes:
                return bytes(imagenes[0].data), imagenes[0].mime or "image/jpeg"
        elif sufijo == ".m4a":
            covr = (MP4(ruta).tags or {}).get("covr")
            if covr:
                return bytes(covr[0]), "image/png" if covr[0].imageformat == 14 else "image/jpeg"
    except (mutagen.MutagenError, OSError):
        return None
    return None


def _portada_en_carpeta(ruta: Path) -> Path | None:
    for nombre in NOMBRES_PORTADA:
        candidata = ruta.parent / nombre
        if candidata.is_file():
            return candidata
    return None


def _leer_cancion(ruta: Path, carpeta: Path) -> Cancion | None:
    try:
        archivo = mutagen.File(ruta, easy=True)
    except (mutagen.MutagenError, OSError):
        return None
    if archivo is None:
        return None
    etiquetas = archivo.tags or {}
    nombre = ruta.stem
    numero = _entero(_primero(etiquetas, "tracknumber"))
    titulo = _primero(etiquetas, "title")
    if titulo is None:
        partes = nombre.split(" - ", 1)
        if len(partes) == 2 and partes[0].strip().isdigit():
            numero = numero or int(partes[0])
            titulo = partes[1].strip()
        else:
            titulo = nombre
    carpeta_padre = ruta.parent.name if ruta.parent != carpeta else ""
    partes_carpeta = carpeta_padre.split(" - ", 1)
    artista = (
        _primero(etiquetas, "albumartist")
        or _primero(etiquetas, "artist")
        or (partes_carpeta[0].strip() if len(partes_carpeta) == 2 else "Artista desconocido")
    )
    album = _primero(etiquetas, "album") or (
        partes_carpeta[1].strip() if len(partes_carpeta) == 2 else (carpeta_padre or "Sin álbum")
    )
    duracion = getattr(getattr(archivo, "info", None), "length", None)
    tiene_portada = _portada_incrustada(ruta) is not None or _portada_en_carpeta(ruta) is not None
    relativa = str(ruta.relative_to(carpeta))
    return Cancion(
        id=_id_de(relativa),
        titulo=titulo,
        artista=artista,
        album=album,
        album_id=_id_de(f"{artista.lower()}\n{album.lower()}"),
        numero_pista=numero,
        duracion_segundos=round(float(duracion), 1) if duracion else None,
        anio=_entero(_primero(etiquetas, "date")),
        genero=_primero(etiquetas, "genre"),
        ruta=ruta,
        tiene_portada=tiene_portada,
    )


def reescanear() -> Indice:
    global _indice
    carpeta = carpeta_configurada()
    canciones: dict[str, Cancion] = {}
    if carpeta is not None:
        for ruta in sorted(carpeta.rglob("*")):
            if (
                ruta.is_file()
                and ruta.suffix.lower() in EXTENSIONES
                and not ruta.name.startswith(".")
            ):
                cancion = _leer_cancion(ruta, carpeta)
                if cancion is not None:
                    canciones[cancion.id] = cancion
    por_album: dict[str, list[Cancion]] = {}
    for cancion in canciones.values():
        por_album.setdefault(cancion.album_id, []).append(cancion)
    albumes = {}
    for album_id, lista in por_album.items():
        lista.sort(key=lambda c: (c.numero_pista or 9999, c.titulo.lower()))
        primera = lista[0]
        anio = next((c.anio for c in lista if c.anio), None)
        albumes[album_id] = Album(album_id, primera.album, primera.artista, anio, tuple(lista))
    with _candado:
        _indice = Indice(carpeta, canciones, albumes, time.time())
    return _indice


def obtener_indice() -> Indice:
    with _candado:
        actual = _indice
    return actual if actual is not None else reescanear()


def buscar_canciones(texto: str | None = None, album_id: str | None = None) -> list[Cancion]:
    indice = obtener_indice()
    lista = list(indice.canciones.values())
    if album_id:
        lista = [c for c in lista if c.album_id == album_id]
    if texto:
        necesidad = texto.lower()
        lista = [
            c
            for c in lista
            if necesidad in c.titulo.lower()
            or necesidad in c.artista.lower()
            or necesidad in c.album.lower()
        ]
    lista.sort(key=lambda c: (c.artista.lower(), c.album.lower(), c.numero_pista or 9999, c.titulo))
    return lista


def portada_de(cancion: Cancion) -> tuple[bytes, str] | None:
    incrustada = _portada_incrustada(cancion.ruta)
    if incrustada is not None:
        return incrustada
    archivo = _portada_en_carpeta(cancion.ruta)
    if archivo is None:
        return None
    tipo = "image/png" if archivo.suffix.lower() == ".png" else "image/jpeg"
    return archivo.read_bytes(), tipo


def tipo_mime(cancion: Cancion) -> str:
    return TIPOS_MIME.get(cancion.ruta.suffix.lower(), "application/octet-stream")


def _firma(cancion_id: str, caduca: int) -> str:
    mensaje = f"{cancion_id}:{caduca}".encode()
    return hmac.new(configuracion.clave_secreta.encode(), mensaje, hashlib.sha256).hexdigest()


def url_audio(cancion: Cancion) -> str:
    caduca = int(time.time()) + SEGUNDOS_FIRMA
    return (
        f"/musica/canciones/{cancion.id}/audio?caduca={caduca}&firma={_firma(cancion.id, caduca)}"
    )


def firma_valida(cancion_id: str, caduca: int, firma: str) -> bool:
    if caduca < time.time():
        return False
    return hmac.compare_digest(_firma(cancion_id, caduca), firma)
