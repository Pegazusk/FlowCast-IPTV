import base64
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

app = FastAPI(title="Proveedor Xtream simulado")

USUARIO, CONTRASENA = "demo", "demo"
PORTADA = "https://picsum.photos/seed/{semilla}/300/450"
FONDO = "https://picsum.photos/seed/{semilla}/1280/720"
CARPETA_MEDIOS = Path(__file__).parent / "medios"
VIDEO_PELICULA = CARPETA_MEDIOS / "pelicula.mp4"
VIDEO_EPISODIO = CARPETA_MEDIOS / "episodio.mp4"
STREAM_EN_VIVO = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"


def _generar_video(destino: Path, segundos: int) -> None:
    if destino.exists():
        return
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Instala ffmpeg (brew install ffmpeg) para generar los vídeos de prueba")
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            str(segundos),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            str(destino),
        ],
        check=True,
    )


_generar_video(VIDEO_PELICULA, 120)
_generar_video(VIDEO_EPISODIO, 90)

CATEGORIAS_PELICULAS = {
    "1": "New Releases",
    "2": "Acción",
    "3": "Drama",
    "4": "Comedia",
    "5": "Animación",
    "6": "Terror",
    "7": "Solo Adultos XXX",
}
CATEGORIAS_SERIES = {
    "10": "Drama",
    "11": "Sci Fi",
    "12": "Comedia",
    "13": "Novelas",
    "14": "Erótico +18",
}
CATEGORIAS_CANALES = {
    "20": "Noticias",
    "21": "Deportes",
    "22": "Infantil",
    "23": "Películas 24h",
    "24": "Adultos XXX",
}

TITULOS_PELICULAS = [
    "Ciudad en llamas",
    "El último viaje",
    "Sombras del norte",
    "La casa del lago",
    "Operación Delta",
    "Noches de verano",
    "El código perdido",
    "Más allá del mar",
    "Horizonte rojo",
    "La promesa",
    "Tormenta silenciosa",
    "El guardián",
    "Luz de luna",
    "Ruta 66",
    "El despertar",
    "Fuego cruzado",
    "La última carta",
    "Cielo abierto",
    "Vértigo urbano",
    "El jardín secreto",
    "Instinto",
    "La deuda",
    "Mar de fondo",
    "Punto ciego",
    "El pacto",
    "Rumbo norte",
    "Alma de hierro",
    "Eco",
    "La cita",
    "Valle oscuro",
    "Travesía",
    "El faro",
    "Juego final",
    "Raíces",
    "El puente",
    "Desierto azul",
    "La fuga",
    "Capitán Nadie",
    "Ciudad dormida",
    "Ritmo",
    "Nieve negra",
    "Amanecer",
    "Las huellas",
    "El coleccionista",
    "Isla perdida",
    "El mensajero",
    "Tierra firme",
    "Latidos",
]
TITULOS_SERIES = [
    "Linternas",
    "Al este del Edén",
    "Tres Gracias",
    "La torre",
    "Código 9",
    "Marea alta",
    "El cartel del sur",
    "Nómadas",
    "Estación Central",
    "La academia",
    "Vecinos",
    "El laboratorio",
    "Herencia",
    "Puerto Escondido",
    "Fronteras",
    "Las cuatro estaciones",
]
NOMBRES_CANALES = {
    "20": [
        "Noticias 24",
        "Canal Informativo",
        "Mundo Hoy",
        "Actualidad HD",
        "Prensa TV",
        "Reporte Global",
    ],
    "21": ["Deportes Uno", "Fútbol Total", "Arena HD", "Motor TV", "Básquet Live", "Olimpo Sports"],
    "22": ["Peques TV", "Dibujos HD", "Aventura Kids", "Cuentos", "Juega", "Mundo Animal"],
    "23": [
        "Cine Clásico",
        "Cine Acción",
        "Cine Familiar",
        "Cine Terror",
        "Cine Comedia",
        "Estrenos 24h",
    ],
    "24": ["Noche Roja", "Privé TV", "Pasión 24h"],
}
SINOPSIS = (
    "Una historia inventada para probar FlowCast: personajes, giros y un final que nadie espera. "
    "Este texto existe solo para comprobar cómo se ve la sinopsis en la ficha."
)


def _peliculas() -> list[dict[str, Any]]:
    lista = []
    for indice, titulo in enumerate(TITULOS_PELICULAS):
        categoria = list(CATEGORIAS_PELICULAS)[indice % len(CATEGORIAS_PELICULAS)]
        stream_id = 500 + indice
        lista.append(
            {
                "num": indice + 1,
                "name": titulo,
                "stream_type": "movie",
                "stream_id": stream_id,
                "stream_icon": PORTADA.format(semilla=f"pel{stream_id}"),
                "rating": f"{5 + (indice % 5)}.{indice % 10}",
                "rating_5based": 3.5,
                "added": str(1_700_000_000 + indice * 86_400),
                "category_id": categoria,
                "container_extension": "mp4",
                "custom_sid": "",
                "direct_source": "",
            }
        )
    return lista


def _series() -> list[dict[str, Any]]:
    lista = []
    for indice, titulo in enumerate(TITULOS_SERIES):
        categoria = list(CATEGORIAS_SERIES)[indice % len(CATEGORIAS_SERIES)]
        series_id = 900 + indice
        lista.append(
            {
                "num": indice + 1,
                "name": titulo,
                "series_id": series_id,
                "cover": PORTADA.format(semilla=f"ser{series_id}"),
                "plot": SINOPSIS,
                "cast": "Ana Torres, Luis Peña",
                "director": "M. Ruiz",
                "genre": CATEGORIAS_SERIES[categoria],
                "releaseDate": f"20{20 + indice % 6}-03-01",
                "last_modified": "1700000000",
                "rating": f"{6 + indice % 4}",
                "rating_5based": 4,
                "backdrop_path": [FONDO.format(semilla=f"ser{series_id}")],
                "youtube_trailer": "",
                "episode_run_time": "45",
                "category_id": categoria,
            }
        )
    return lista


def _canales() -> list[dict[str, Any]]:
    lista, numero = [], 1
    for categoria, nombres in NOMBRES_CANALES.items():
        for nombre in nombres:
            stream_id = 100 + numero
            lista.append(
                {
                    "num": numero,
                    "name": nombre,
                    "stream_type": "live",
                    "stream_id": stream_id,
                    "stream_icon": f"https://picsum.photos/seed/can{stream_id}/200/200",
                    "epg_channel_id": f"canal{stream_id}.sim",
                    "added": "1700000000",
                    "category_id": categoria,
                    "custom_sid": "",
                    "tv_archive": 1 if numero % 2 else 0,
                    "direct_source": "",
                    "tv_archive_duration": 3,
                }
            )
            numero += 1
    return lista


PELICULAS, SERIES, CANALES = _peliculas(), _series(), _canales()


def _categorias(diccionario: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"category_id": id_, "category_name": nombre, "parent_id": 0}
        for id_, nombre in diccionario.items()
    ]


def _b64(texto: str) -> str:
    return base64.b64encode(texto.encode()).decode()


@app.get("/player_api.php")
def player_api(
    username: str = "",
    password: str = "",
    action: str | None = None,
    category_id: str | None = None,
    vod_id: str | None = None,
    series_id: str | None = None,
    stream_id: str | None = None,
    limit: int = Query(10),
) -> Any:
    if username != USUARIO or password != CONTRASENA:
        return {"user_info": {"auth": 0}}
    if action is None:
        return {
            "user_info": {
                "username": USUARIO,
                "auth": 1,
                "status": "Active",
                "exp_date": str(int(time.time()) + 90 * 86_400),
                "is_trial": "0",
                "active_cons": "0",
                "max_connections": "3",
                "allowed_output_formats": ["m3u8", "ts"],
            },
            "server_info": {
                "url": "simulado",
                "port": "8090",
                "https_port": "8090",
                "server_protocol": "http",
                "timezone": "America/Mexico_City",
                "timestamp_now": int(time.time()),
            },
        }
    if action == "get_live_categories":
        return _categorias(CATEGORIAS_CANALES)
    if action == "get_vod_categories":
        return _categorias(CATEGORIAS_PELICULAS)
    if action == "get_series_categories":
        return _categorias(CATEGORIAS_SERIES)
    if action == "get_live_streams":
        return [c for c in CANALES if category_id is None or c["category_id"] == category_id]
    if action == "get_vod_streams":
        return [p for p in PELICULAS if category_id is None or p["category_id"] == category_id]
    if action == "get_series":
        return [s for s in SERIES if category_id is None or s["category_id"] == category_id]
    if action == "get_vod_info":
        pelicula = next((p for p in PELICULAS if str(p["stream_id"]) == vod_id), None)
        if pelicula is None:
            return {"info": [], "movie_data": []}
        return {
            "info": {
                "tmdb_id": 1000 + pelicula["stream_id"],
                "name": pelicula["name"],
                "movie_image": pelicula["stream_icon"],
                "cover_big": pelicula["stream_icon"],
                "releasedate": "2024-05-10",
                "youtube_trailer": "",
                "director": "M. Ruiz",
                "actors": "Ana Torres, Luis Peña, Sofía Mena",
                "cast": "Ana Torres, Luis Peña, Sofía Mena",
                "description": SINOPSIS,
                "plot": SINOPSIS,
                "age": "13",
                "country": "México",
                "genre": CATEGORIAS_PELICULAS[pelicula["category_id"]],
                "backdrop_path": [FONDO.format(semilla=f"pel{pelicula['stream_id']}")],
                "duration_secs": 5400,
                "duration": "01:30:00",
                "rating": pelicula["rating"],
            },
            "movie_data": {
                "stream_id": pelicula["stream_id"],
                "name": pelicula["name"],
                "added": pelicula["added"],
                "category_id": pelicula["category_id"],
                "container_extension": "mp4",
                "custom_sid": "",
                "direct_source": "",
            },
        }
    if action == "get_series_info":
        serie = next((s for s in SERIES if str(s["series_id"]) == series_id), None)
        if serie is None:
            return {"seasons": [], "info": [], "episodes": []}
        episodios = {
            str(temporada): [
                {
                    "id": f"{serie['series_id']}{temporada}{numero:02d}",
                    "episode_num": numero,
                    "title": f"Episodio {numero}: {['El inicio', 'La huida', 'Secretos', 'El regreso'][numero - 1]}",
                    "container_extension": "mp4",
                    "season": temporada,
                    "info": {
                        "movie_image": f"https://picsum.photos/seed/ep{serie['series_id']}{temporada}{numero}/640/360",
                        "plot": SINOPSIS,
                        "duration_secs": 2500,
                        "duration": "00:41:40",
                        "rating": "7",
                    },
                    "custom_sid": "",
                    "added": "1700000000",
                    "direct_source": "",
                }
                for numero in range(1, 5)
            ]
            for temporada in (1, 2)
        }
        return {
            "seasons": [
                {
                    "air_date": f"202{t}-01-01",
                    "episode_count": 4,
                    "id": t,
                    "name": f"Temporada {t}",
                    "overview": "",
                    "season_number": t,
                    "cover": serie["cover"],
                    "cover_big": serie["cover"],
                }
                for t in (1, 2)
            ],
            "info": {k: v for k, v in serie.items() if k not in ("num", "series_id")},
            "episodes": episodios,
        }
    if action == "get_short_epg":
        ahora = int(time.time())
        programas = []
        for i in range(limit):
            inicio = ahora - 1200 + i * 1800
            programas.append(
                {
                    "id": str(i),
                    "epg_id": "1",
                    "title": _b64(f"Programa {i + 1} del canal {stream_id}"),
                    "lang": "es",
                    "start": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(inicio)),
                    "end": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(inicio + 1800)),
                    "description": _b64("Descripción de prueba del programa."),
                    "channel_id": f"canal{stream_id}.sim",
                    "start_timestamp": str(inicio),
                    "stop_timestamp": str(inicio + 1800),
                    "now_playing": 1 if i == 0 else 0,
                    "has_archive": 0,
                }
            )
        return {"epg_listings": programas}
    return JSONResponse(status_code=404, content={"error": f"action desconocido: {action}"})


@app.get("/movie/{usuario}/{contrasena}/{archivo}")
def pelicula(usuario: str, contrasena: str, archivo: str) -> FileResponse:
    return FileResponse(VIDEO_PELICULA, media_type="video/mp4")


@app.get("/series/{usuario}/{contrasena}/{archivo}")
def episodio(usuario: str, contrasena: str, archivo: str) -> FileResponse:
    return FileResponse(VIDEO_EPISODIO, media_type="video/mp4")


@app.get("/live/{usuario}/{contrasena}/{archivo}")
def canal(usuario: str, contrasena: str, archivo: str) -> RedirectResponse:
    return RedirectResponse(STREAM_EN_VIVO)
