import re
import unicodedata
from typing import Any

TRADUCCIONES = {
    "new releases": "Estrenos",
    "new releases cam": "Estrenos en cine (CAM)",
    "action": "Acción",
    "animation": "Animación",
    "anime": "Anime",
    "anime (popular)": "Anime",
    "adventure": "Aventura",
    "biografico bio": "Biografías",
    "biography": "Biografías",
    "classics": "Clásicos",
    "comedy": "Comedia",
    "comedy drama": "Comedia dramática",
    "concerts": "Conciertos",
    "crime": "Crimen",
    "documentary": "Documentales",
    "drama": "Drama",
    "epoca": "De época",
    "family": "Familia",
    "fantasy": "Fantasía",
    "guerra war": "Bélicas",
    "horror": "Terror",
    "terror": "Terror",
    "kids": "Infantiles",
    "latinas": "Latinas",
    "latinas peru": "Latinas de Perú",
    "mexicanas": "Mexicanas",
    "martial arts": "Artes marciales",
    "musical": "Musicales",
    "navidad holiday": "Navidad",
    "religion": "Religión",
    "romance": "Romance",
    "romance comedy": "Comedia romántica",
    "sports": "Deportes",
    "sports events": "Eventos deportivos",
    "sci fi": "Ciencia ficción",
    "superheroes": "Superhéroes",
    "suspense": "Suspenso",
    "thriller": "Suspenso",
    "mystery": "Misterio",
    "tv movies": "Películas para TV",
    "tv shows": "Programas de TV",
    "western": "Western",
    "doramas": "Doramas",
    "k-drama": "Doramas",
    "doramas bl": "Doramas BL",
    "novelas": "Novelas",
    "novelas colombia": "Novelas colombianas",
    "novelas latinas": "Novelas latinas",
    "novelas mexico": "Novelas mexicanas",
    "novelas turcas": "Novelas turcas",
    "novelas usa": "Novelas de Estados Unidos",
    "realities": "Realities",
    "retro": "Retro",
    "xxx": "Adultos",
}


def _clave(nombre: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", nombre.lower())
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip()


def traducir(nombre: str) -> str:
    return TRADUCCIONES.get(_clave(nombre), nombre.strip())


def unir(categorias: list[Any]) -> list[Any]:
    unidas: dict[str, Any] = {}
    for categoria in categorias:
        nombre = traducir(categoria.nombre)
        existente = unidas.get(_clave(nombre))
        if existente is None:
            unidas[_clave(nombre)] = categoria.model_copy(update={"nombre": nombre})
            continue
        existente.id = f"{existente.id},{categoria.id}"
        existente.es_adulta = existente.es_adulta or categoria.es_adulta
        existente.bloqueada = existente.bloqueada or categoria.bloqueada
        if existente.total is not None or categoria.total is not None:
            existente.total = (existente.total or 0) + (categoria.total or 0)
    return list(unidas.values())
