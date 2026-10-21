import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

_PREFIJOS = {
    "esp": "Español",
    "es": "Español",
    "cas": "Español de España",
    "ca": "Español de España",
    "lat": "Español latino",
    "sub": "Subtitulado",
    "su": "Subtitulado",
    "eng": "Inglés",
    "en": "Inglés",
}
_ETIQUETAS = {
    "dual": "Dual (Español e Inglés)",
    "lat": "Español latino",
    "latino": "Español latino",
    "esp": "Español",
    "es": "Español",
    "español": "Español",
    "cas": "Español de España",
    "castellano": "Español de España",
    "es-es": "Español de España",
    "sub": "Subtitulado",
    "subt": "Subtitulado",
    "subtitulado": "Subtitulado",
    "subtitulada": "Subtitulado",
    "eng": "Inglés",
    "en": "Inglés",
}
_CALIDADES = {
    "cam": "CAM",
    "hdts": "CAM",
    "ts": "CAM",
    "hd": "",
    "4k": "",
    "720p": "",
    "1080p": "",
    "480p": "",
}
_PREFERENCIA = [
    "Español latino",
    "Español",
    "Dual (Español e Inglés)",
    "",
    "Español de España",
    "Subtitulado",
    "Inglés",
]

_PREFIJO_CON_GUION = re.compile(r"^\s*([a-z]{2,3})\s*-\s*", re.IGNORECASE)
_PREFIJO_CON_ESPACIO = re.compile(r"^\s*(sub|esp|eng|cas|lat|dual)\s+", re.IGNORECASE)
_PARENTESIS_FINAL = re.compile(r"\s*[\(\[]([^()\[\]]{1,25})[\)\]]\s*$")
_CALIDAD_SUELTA = re.compile(r"\s+(\d{3,4}p|4k|hd|hdts|cam)\s*$", re.IGNORECASE)
_ANIO = re.compile(r"^(19\d{2}|20\d{2})$")


@dataclass(frozen=True)
class Titulo:
    titulo: str
    anio: int | None
    idioma: str
    calidad: str


def analizar(nombre: str) -> Titulo:
    texto = nombre.strip()
    idioma = ""
    calidad = ""
    con_guion = _PREFIJO_CON_GUION.match(texto)
    if con_guion and con_guion.group(1).lower() in _PREFIJOS:
        idioma = _PREFIJOS[con_guion.group(1).lower()]
        texto = texto[con_guion.end() :]
    else:
        con_espacio = _PREFIJO_CON_ESPACIO.match(texto)
        if con_espacio:
            clave = con_espacio.group(1).lower()
            idioma = _ETIQUETAS.get(clave, _PREFIJOS.get(clave, ""))
            texto = texto[con_espacio.end() :]
    anio = None
    while True:
        suelta = _CALIDAD_SUELTA.search(texto)
        if suelta:
            calidad = calidad or _CALIDADES.get(suelta.group(1).lower(), "")
            texto = texto[: suelta.start()]
            continue
        final = _PARENTESIS_FINAL.search(texto)
        if not final:
            break
        contenido = final.group(1).strip()
        clave = contenido.lower()
        if _ANIO.match(contenido) and anio is None:
            anio = int(contenido)
        elif clave in _ETIQUETAS:
            idioma = idioma or _ETIQUETAS[clave]
        elif clave in _CALIDADES:
            calidad = calidad or _CALIDADES[clave]
        elif clave.startswith("subtit"):
            idioma = idioma or "Subtitulado"
        else:
            break
        texto = texto[: final.start()]
    limpio = texto.strip(" -–·").strip()
    return Titulo(titulo=limpio or nombre.strip(), anio=anio, idioma=idioma, calidad=calidad)


def _clave(titulo: Titulo) -> str:
    descompuesto = unicodedata.normalize("NFKD", titulo.titulo.lower())
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-zĀ-￿]+", " ", sin_acentos).strip()


def _prioridad(idioma: str) -> int:
    return _PREFERENCIA.index(idioma) if idioma in _PREFERENCIA else len(_PREFERENCIA)


@dataclass
class Grupo:
    titulo: Titulo
    versiones: list[tuple[Any, Titulo]] = field(default_factory=list)

    @property
    def principal(self) -> Any:
        return self.versiones[0][0]


def agrupar(elementos: list[Any]) -> list[Grupo]:
    grupos: list[Grupo] = []
    por_clave: dict[tuple[str, int | None], list[Grupo]] = {}
    for elemento in elementos:
        titulo = analizar(elemento.nombre)
        clave = (_clave(titulo), titulo.anio)
        candidatos = por_clave.setdefault(clave, [])
        destino = next(
            (g for g in candidatos if all(t.idioma != titulo.idioma for _, t in g.versiones)),
            None,
        )
        if destino is None or not clave[0]:
            destino = Grupo(titulo=titulo)
            candidatos.append(destino)
            grupos.append(destino)
        destino.versiones.append((elemento, titulo))
    for grupo in grupos:
        grupo.versiones.sort(key=lambda version: _prioridad(version[1].idioma))
        grupo.titulo = grupo.versiones[0][1]
    return grupos
