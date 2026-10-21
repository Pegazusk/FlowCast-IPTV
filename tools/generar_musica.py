import shutil
import subprocess
from pathlib import Path

CARPETA = Path(__file__).parent / "medios" / "musica"
SEGUNDOS = 24

ALBUMES = [
    {
        "artista": "Los Faros",
        "album": "Marea alta",
        "anio": "2023",
        "genero": "Pop",
        "color": "0xD9F64B",
        "portada": "incrustada",
        "pistas": ["Puerto escondido", "Luz de tormenta", "Camino al mar"],
        "notas": (262, 330, 392, 523),
    },
    {
        "artista": "Nadia Río",
        "album": "Ciudad dormida",
        "anio": "2021",
        "genero": "Indie",
        "color": "0xF2B340",
        "portada": "carpeta",
        "pistas": ["Avenida norte", "Ventanas", "Última llamada"],
        "notas": (220, 277, 330, 440),
    },
    {
        "artista": "Eco Binario",
        "album": "Pulso",
        "anio": "2024",
        "genero": "Electrónica",
        "color": "0x3A4318",
        "portada": "ninguna",
        "pistas": ["Latido", "Señal", "Circuito"],
        "notas": (196, 247, 294, 392),
    },
]


def _ejecutar(argumentos: list[str]) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *argumentos], check=True)


def _melodia(notas: tuple[int, ...], desplazamiento: int) -> str:
    n1, n2, n3, n4 = (n * (1 + desplazamiento * 0.25) for n in notas)
    frecuencia = f"if(lt(mod(t,2),0.5),{n1},if(lt(mod(t,2),1),{n2},if(lt(mod(t,2),1.5),{n3},{n4})))"
    return f"0.35*sin(2*PI*t*{frecuencia})*(1-mod(t*2,1))"


def generar() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("Instala ffmpeg (brew install ffmpeg) para generar la música de muestra")
    for album in ALBUMES:
        carpeta = CARPETA / f"{album['artista']} - {album['album']}"
        carpeta.mkdir(parents=True, exist_ok=True)
        portada = carpeta / "cover.jpg"
        if album["portada"] != "ninguna":
            _ejecutar(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={album['color']}:s=600x600",
                    "-frames:v",
                    "1",
                    str(portada),
                ]
            )
        for numero, titulo in enumerate(album["pistas"], start=1):
            destino = carpeta / f"{numero:02d} - {titulo}.mp3"
            if destino.exists():
                continue
            etiquetas = [
                "-metadata",
                f"title={titulo}",
                "-metadata",
                f"artist={album['artista']}",
                "-metadata",
                f"album={album['album']}",
                "-metadata",
                f"album_artist={album['artista']}",
                "-metadata",
                f"track={numero}/{len(album['pistas'])}",
                "-metadata",
                f"date={album['anio']}",
                "-metadata",
                f"genre={album['genero']}",
            ]
            entradas = [
                "-f",
                "lavfi",
                "-i",
                f"aevalsrc=exprs='{_melodia(album['notas'], numero - 1)}':s=44100",
            ]
            mapeo: list[str] = []
            if album["portada"] == "incrustada":
                entradas += ["-i", str(portada)]
                mapeo = [
                    "-map",
                    "0:a",
                    "-map",
                    "1:v",
                    "-c:v",
                    "copy",
                    "-disposition:v",
                    "attached_pic",
                    "-metadata:s:v",
                    "title=Album cover",
                    "-metadata:s:v",
                    "comment=Cover (front)",
                ]
            _ejecutar(
                [
                    *entradas,
                    "-t",
                    str(SEGUNDOS),
                    *mapeo,
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "4",
                    "-id3v2_version",
                    "3",
                    *etiquetas,
                    str(destino),
                ]
            )
            print("generada:", destino.relative_to(CARPETA))
        if album["portada"] == "incrustada":
            portada.unlink(missing_ok=True)
    print("listo:", CARPETA)


if __name__ == "__main__":
    generar()
