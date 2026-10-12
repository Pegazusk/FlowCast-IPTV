from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, Response

from app.deps import UsuarioActual
from app.schemas.musica import Album, AlbumConCanciones, Cancion, ResumenMusica
from app.services import musica

router = APIRouter(prefix="/musica", tags=["musica"])


def _url_portada(cancion: musica.Cancion) -> str | None:
    return f"/musica/canciones/{cancion.id}/portada" if cancion.tiene_portada else None


def _cancion(cancion: musica.Cancion) -> Cancion:
    return Cancion(
        id=cancion.id,
        titulo=cancion.titulo,
        artista=cancion.artista,
        album=cancion.album,
        album_id=cancion.album_id,
        numero_pista=cancion.numero_pista,
        duracion_segundos=cancion.duracion_segundos,
        anio=cancion.anio,
        genero=cancion.genero,
        url_audio=musica.url_audio(cancion),
        url_portada=_url_portada(cancion),
    )


def _album(album: musica.Album) -> Album:
    con_portada = next((c for c in album.canciones if c.tiene_portada), None)
    return Album(
        id=album.id,
        titulo=album.titulo,
        artista=album.artista,
        anio=album.anio,
        total_canciones=len(album.canciones),
        duracion_segundos=album.duracion_segundos,
        url_portada=_url_portada(con_portada) if con_portada else None,
    )


def _resumen(indice: musica.Indice) -> ResumenMusica:
    return ResumenMusica(
        carpeta_configurada=indice.carpeta is not None,
        total_canciones=len(indice.canciones),
        total_albumes=len(indice.albumes),
        escaneado_en=indice.escaneado_en,
    )


@router.get("", response_model=ResumenMusica)
async def resumen(_usuario: UsuarioActual) -> ResumenMusica:
    return _resumen(musica.obtener_indice())


@router.post("/reescanear", response_model=ResumenMusica)
async def reescanear(_usuario: UsuarioActual) -> ResumenMusica:
    return _resumen(musica.reescanear())


@router.get("/albumes", response_model=list[Album])
async def listar_albumes(_usuario: UsuarioActual) -> list[Album]:
    albumes = sorted(
        musica.obtener_indice().albumes.values(),
        key=lambda a: (a.artista.lower(), a.titulo.lower()),
    )
    return [_album(a) for a in albumes]


@router.get("/albumes/{album_id}", response_model=AlbumConCanciones)
async def ver_album(_usuario: UsuarioActual, album_id: str) -> AlbumConCanciones:
    album = musica.obtener_indice().albumes.get(album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Álbum no encontrado")
    return AlbumConCanciones(album=_album(album), canciones=[_cancion(c) for c in album.canciones])


@router.get("/canciones", response_model=list[Cancion])
async def listar_canciones(
    _usuario: UsuarioActual,
    buscar: str | None = Query(default=None, max_length=100),
    album_id: str | None = None,
) -> list[Cancion]:
    return [_cancion(c) for c in musica.buscar_canciones(buscar, album_id)]


@router.get("/canciones/{cancion_id}/audio")
async def audio(cancion_id: str, caduca: int, firma: str) -> FileResponse:
    if not musica.firma_valida(cancion_id, caduca, firma):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="URL de audio inválida o caducada")
    cancion = musica.obtener_indice().canciones.get(cancion_id)
    if cancion is None or not cancion.ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Canción no encontrada")
    return FileResponse(
        cancion.ruta, media_type=musica.tipo_mime(cancion), filename=cancion.ruta.name
    )


@router.get("/canciones/{cancion_id}/portada")
async def portada(cancion_id: str) -> Response:
    cancion = musica.obtener_indice().canciones.get(cancion_id)
    imagen = musica.portada_de(cancion) if cancion is not None else None
    if imagen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sin portada")
    datos, tipo = imagen
    return Response(
        content=datos, media_type=tipo, headers={"Cache-Control": "public, max-age=86400"}
    )
