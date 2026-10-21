import asyncio
import re
import unicodedata
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select

from app import cifrado
from app.deps import SesionBD, UsuarioActual
from app.models import CategoriaBloqueada, ConexionXtream, CreditosSerie, Usuario
from app.routers.conexiones import (
    ClienteHTTP,
)
from app.schemas import catalogo as esquemas
from app.services import cache, control_parental, titulos, tmdb, xtream
from app.services import categorias as categorias_unidas

router = APIRouter(prefix="/conexiones/{conexion_id}", tags=["catalogo"])

SEGUNDOS_LISTAS = 300
SEGUNDOS_FICHAS = 900
SEGUNDOS_EPG = 300


@dataclass(frozen=True)
class ContextoConexion:
    conexion: ConexionXtream
    credenciales: xtream.CredencialesXtream

    def clave(self, *partes: Any) -> str:
        return ":".join(["conexion", str(self.conexion.id), *map(str, partes)])


async def obtener_conexion_propia(
    conexion_id: uuid.UUID, usuario: UsuarioActual, sesion_bd: SesionBD
) -> ContextoConexion:
    consulta = select(ConexionXtream).where(
        ConexionXtream.id == conexion_id, ConexionXtream.usuario_id == usuario.id
    )
    conexion = (await sesion_bd.execute(consulta)).scalar_one_or_none()
    if conexion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conexión no encontrada")
    credenciales = xtream.CredencialesXtream(
        url_base=conexion.url_base,
        nombre_usuario=conexion.nombre_usuario,
        contrasena=cifrado.descifrar(conexion.contrasena_cifrada),
    )
    return ContextoConexion(conexion=conexion, credenciales=credenciales)


ConexionPropia = Annotated[ContextoConexion, Depends(obtener_conexion_propia)]


async def cargar_bloqueos(
    sesion_bd: Any, usuario_id: uuid.UUID, conexion_id: uuid.UUID
) -> dict[tuple[str, str], bool]:
    filas = (
        await sesion_bd.execute(
            select(CategoriaBloqueada).where(
                CategoriaBloqueada.usuario_id == usuario_id,
                CategoriaBloqueada.conexion_id == conexion_id,
            )
        )
    ).scalars()
    return {(f.tipo_contenido, f.categoria_id): f.bloqueada for f in filas}


Desbloqueo = Annotated[str | None, Header(alias="X-Desbloqueo-Parental")]


@dataclass
class ControlParental:
    usuario: Usuario
    bloqueos: dict[tuple[str, str], bool]
    desbloqueado: bool

    def exigir(self, bloqueado: bool) -> None:
        if not bloqueado or self.desbloqueado:
            return
        if self.usuario.hash_pin_parental is None:
            raise HTTPException(
                status.HTTP_423_LOCKED,
                detail={
                    "codigo": "pin_no_configurado",
                    "mensaje": "Contenido bloqueado. Crea un PIN parental en Configuración para verlo",
                },
            )
        raise HTTPException(
            status.HTTP_423_LOCKED,
            detail={
                "codigo": "pin_requerido",
                "mensaje": "Este contenido requiere el PIN parental",
            },
        )


async def obtener_control(
    conexion_id: uuid.UUID,
    usuario: UsuarioActual,
    sesion_bd: SesionBD,
    desbloqueo: Desbloqueo = None,
) -> ControlParental:
    bloqueos = await cargar_bloqueos(sesion_bd, usuario.id, conexion_id)
    desbloqueado = (
        usuario.hash_pin_parental is not None
        and control_parental.token_desbloqueo_valido(desbloqueo, usuario.id)
    )
    return ControlParental(usuario, bloqueos, desbloqueado)


Control = Annotated[ControlParental, Depends(obtener_control)]


async def _categorias_bloqueadas(
    contexto: ContextoConexion, cliente: Any, bloqueos: dict[tuple[str, str], bool], tipo: str
) -> set[str]:
    categorias = await _consultar(
        contexto.clave("categorias", tipo),
        SEGUNDOS_LISTAS,
        lambda: xtream.obtener_categorias(contexto.credenciales, tipo, cliente=cliente),
    )
    return {
        c.id
        for c in categorias
        if bloqueos.get((tipo, c.id), control_parental.es_nombre_adulto(c.nombre))
    }


def _esta_bloqueado(elemento: Any, bloqueadas: set[str]) -> bool:
    return elemento.categoria_id in bloqueadas or control_parental.es_nombre_adulto(elemento.nombre)


def _marcar(modelos: list[Any], elementos: list[Any], bloqueadas: set[str]) -> list[Any]:
    for modelo, elemento in zip(modelos, elementos, strict=True):
        modelo.bloqueada = _esta_bloqueado(elemento, bloqueadas)
    return modelos


def _visibles(elementos: list[Any], bloqueadas: set[str], control: ControlParental) -> list[Any]:
    if control.desbloqueado:
        return elementos
    return [e for e in elementos if not _esta_bloqueado(e, bloqueadas)]


class _FiltroConexion:
    def __init__(
        self, contexto: ContextoConexion, bloqueos: dict[tuple[str, str], bool], cliente: Any
    ):
        self.contexto = contexto
        self.bloqueos = bloqueos
        self.cliente = cliente
        self.cargado: dict[str, tuple[dict[str, Any], set[str]]] = {}

    async def _cargar(self, tipo: str) -> tuple[dict[str, Any], set[str]]:
        if tipo not in self.cargado:
            lectores = {
                "en_vivo": ("canales", xtream.obtener_canales),
                "pelicula": ("peliculas", xtream.obtener_peliculas),
                "serie": ("series", xtream.obtener_series),
            }
            nombre, leer = lectores[tipo]
            elementos = await _consultar(
                self.contexto.clave(nombre, "todas"),
                SEGUNDOS_LISTAS,
                lambda: leer(self.contexto.credenciales, None, cliente=self.cliente),
            )
            bloqueadas = await _categorias_bloqueadas(
                self.contexto, self.cliente, self.bloqueos, tipo
            )
            self.cargado[tipo] = ({e.id: e for e in elementos}, bloqueadas)
        return self.cargado[tipo]

    async def bloqueada(self, entrada: Any) -> bool:
        if control_parental.es_nombre_adulto(entrada.titulo):
            return True
        tipo = entrada.tipo_contenido
        objetivo = entrada.stream_id
        if tipo == "episodio":
            tipo, objetivo = "serie", getattr(entrada, "serie_id", None)
        if tipo not in ("en_vivo", "pelicula", "serie") or objetivo is None:
            return False
        try:
            indice, bloqueadas = await self._cargar(tipo)
        except HTTPException:
            return False
        elemento = indice.get(str(objetivo))
        return elemento is not None and _esta_bloqueado(elemento, bloqueadas)


async def quitar_bloqueados(
    entradas: list[Any], usuario: Usuario, sesion_bd: Any, cliente: Any
) -> list[Any]:
    filtros: dict[uuid.UUID, _FiltroConexion | None] = {}
    visibles: list[Any] = []
    for entrada in entradas:
        if entrada.conexion_id not in filtros:
            try:
                contexto = await obtener_conexion_propia(entrada.conexion_id, usuario, sesion_bd)
            except HTTPException:
                filtros[entrada.conexion_id] = None
            else:
                bloqueos = await cargar_bloqueos(sesion_bd, usuario.id, entrada.conexion_id)
                filtros[entrada.conexion_id] = _FiltroConexion(contexto, bloqueos, cliente)
        filtro = filtros[entrada.conexion_id]
        if filtro is None or not await filtro.bloqueada(entrada):
            visibles.append(entrada)
    return visibles


FiltroCategoria = Annotated[str | None, Query(description="Id de categoría; sin él, todo")]
Limite = Annotated[int | None, Query(ge=1, le=1000, description="Devolver solo los primeros N")]
Desde = Annotated[int, Query(ge=0, description="Saltar los primeros N (para pedir por páginas)")]


OrdenLista = Literal[
    "proveedor", "agregadas", "nombre", "nombre_desc", "calificacion", "nuevas", "antiguas"
]
Orden = Annotated[OrdenLista, Query(description="Cómo ordenar la lista antes de paginarla")]
_PREFIJO_IDIOMA = re.compile(
    r"^\s*(?:[a-z]{2,3}\s*-\s*|(?:sub|esp|eng|cas|dual)\s+)", re.IGNORECASE
)
_SIGNOS_INICIALES = re.compile(r"^[\W_]+")
_ANIO_EN_NOMBRE = re.compile(r"\((19\d{2}|20\d{2})\)")


def _clave_nombre(elemento: Any) -> str:
    return _SIGNOS_INICIALES.sub("", _normalizar(_PREFIJO_IDIOMA.sub("", elemento.nombre)))


def _anio(elemento: Any) -> int | None:
    fecha = getattr(elemento, "fecha_estreno", None) or ""
    if fecha[:4].isdigit():
        return int(fecha[:4])
    encontrado = _ANIO_EN_NOMBRE.search(elemento.nombre)
    return int(encontrado.group(1)) if encontrado else None


def _ordenar(elementos: list[Any], orden: str) -> list[Any]:
    if orden == "nombre":
        return sorted(elementos, key=_clave_nombre)
    if orden == "nombre_desc":
        return sorted(elementos, key=_clave_nombre, reverse=True)
    if orden == "calificacion":
        return sorted(elementos, key=lambda e: getattr(e, "calificacion", None) or 0, reverse=True)
    if orden == "agregadas":
        return sorted(
            elementos,
            key=lambda e: (
                getattr(e, "agregado_en", None).timestamp()
                if getattr(e, "agregado_en", None)
                else 0
            ),
            reverse=True,
        )
    if orden in ("nuevas", "antiguas"):
        con_anio = [e for e in elementos if _anio(e) is not None]
        sin_anio = [e for e in elementos if _anio(e) is None]
        return sorted(con_anio, key=_anio, reverse=orden == "nuevas") + sin_anio
    return elementos


Agrupar = Annotated[
    bool, Query(description="Unir en un solo título las versiones de idioma (Esp, Sub, Eng…)")
]


def _agrupar(elementos: list[Any]) -> tuple[list[Any], dict[str, titulos.Grupo]]:
    representantes = []
    grupos: dict[str, titulos.Grupo] = {}
    for grupo in titulos.agrupar(elementos):
        principal = grupo.principal
        if len(grupo.versiones) > 1:
            todos = [elemento for elemento, _ in grupo.versiones]
            calificaciones = [e.calificacion for e in todos if getattr(e, "calificacion", None)]
            fechas = [e.agregado_en for e in todos if getattr(e, "agregado_en", None)]
            cambios: dict[str, Any] = {}
            if calificaciones:
                cambios["calificacion"] = max(calificaciones)
            if fechas:
                cambios["agregado_en"] = max(fechas)
            if not getattr(principal, "portada", None):
                cambios["portada"] = next((e.portada for e in todos if e.portada), None)
            principal = replace(principal, **cambios)
        representantes.append(principal)
        grupos[principal.id] = grupo
    return representantes, grupos


def _modelos(
    clase: Any,
    elementos: list[Any],
    bloqueadas: set[str],
    grupos: dict[str, titulos.Grupo] | None = None,
) -> list[Any]:
    modelos = []
    for elemento in elementos:
        modelo = clase.model_validate(elemento)
        analisis = titulos.analizar(elemento.nombre)
        modelo.titulo, modelo.anio = analisis.titulo, analisis.anio
        modelo.idioma = analisis.idioma or None
        grupo = grupos.get(elemento.id) if grupos else None
        if grupo and len(grupo.versiones) > 1:
            modelo.versiones = [
                esquemas.Version(id=e.id, idioma=v.idioma or "Original", calidad=v.calidad or None)
                for e, v in grupo.versiones
            ]
        modelos.append(modelo)
    return _marcar(modelos, elementos, bloqueadas)


def _pagina(elementos: list[Any], desde: int, limite: int | None) -> list[Any]:
    return elementos[desde : desde + limite if limite else None]


async def _consultar(clave: str, segundos: int, llamada: Callable[[], Awaitable[Any]]) -> Any:
    obtener = (
        cache.obtener_con_respaldo if segundos == SEGUNDOS_LISTAS else cache.obtener_o_calcular
    )
    try:
        return await obtener(clave, llamada, segundos)
    except xtream.ContenidoNoEncontrado as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from None
    except xtream.CredencialesXtreamInvalidas:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="El proveedor rechazó las credenciales de esta conexión; revalídala o corrígela",
        ) from None
    except xtream.ProveedorNoDisponible as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None


@router.get("/categorias", response_model=list[esquemas.Categoria])
async def listar_categorias(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    tipo: Annotated[xtream.TipoContenido, Query(description="en_vivo, pelicula o serie")],
    control: Control,
    con_totales: Annotated[
        bool, Query(description="Añadir cuántos elementos tiene cada una")
    ] = False,
    unir: Annotated[
        bool,
        Query(description="Traducir al español y juntar las repetidas (ids separados por coma)"),
    ] = False,
) -> list[esquemas.Categoria]:
    categorias = await _consultar(
        contexto.clave("categorias", tipo),
        SEGUNDOS_LISTAS,
        lambda: xtream.obtener_categorias(contexto.credenciales, tipo, cliente=cliente),
    )
    resultado = [esquemas.Categoria.model_validate(c) for c in categorias]
    for modelo in resultado:
        modelo.es_adulta = control_parental.es_nombre_adulto(modelo.nombre)
        modelo.bloqueada = control.bloqueos.get((tipo, modelo.id), modelo.es_adulta)
    if con_totales:
        elementos = await _lista_completa(contexto, cliente, tipo)
        conteo = Counter(str(getattr(e, "categoria_id", None)) for e in elementos)
        for categoria in resultado:
            categoria.total = conteo.get(categoria.id, 0)
    if unir and tipo != "en_vivo":
        return categorias_unidas.unir(resultado)
    return resultado


def _ids(categoria_id: str | None) -> list[str]:
    return [parte for parte in (categoria_id or "").split(",") if parte]


async def _de_categorias(
    contexto: ContextoConexion, cliente: Any, tipo: str, ruta: str, categoria_id: str | None
) -> list[Any]:
    ids = _ids(categoria_id)
    if len(ids) > 1:
        elegidas = set(ids)
        todas = await _lista_completa(contexto, cliente, tipo)
        return [e for e in todas if str(getattr(e, "categoria_id", None)) in elegidas]
    obtener = {
        "en_vivo": xtream.obtener_canales,
        "pelicula": xtream.obtener_peliculas,
        "serie": xtream.obtener_series,
    }[tipo]
    return await _consultar(
        contexto.clave(ruta, categoria_id or "todas"),
        SEGUNDOS_LISTAS,
        lambda: obtener(contexto.credenciales, categoria_id, cliente=cliente),
    )


async def _lista_completa(contexto: ContextoConexion, cliente: Any, tipo: str) -> list[Any]:
    if tipo == "en_vivo":
        return await _consultar(
            contexto.clave("canales", "todas"),
            SEGUNDOS_LISTAS,
            lambda: xtream.obtener_canales(contexto.credenciales, None, cliente=cliente),
        )
    if tipo == "pelicula":
        return await _consultar(
            contexto.clave("peliculas", "todas"),
            SEGUNDOS_LISTAS,
            lambda: xtream.obtener_peliculas(contexto.credenciales, None, cliente=cliente),
        )
    return await _consultar(
        contexto.clave("series", "todas"),
        SEGUNDOS_LISTAS,
        lambda: xtream.obtener_series(contexto.credenciales, None, cliente=cliente),
    )


@router.get("/canales", response_model=list[esquemas.Canal])
async def listar_canales(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    control: Control,
    categoria_id: FiltroCategoria = None,
    limite: Limite = None,
    desde: Desde = 0,
    orden: Orden = "proveedor",
) -> list[esquemas.Canal]:
    bloqueadas = await _categorias_bloqueadas(contexto, cliente, control.bloqueos, "en_vivo")
    control.exigir(any(parte in bloqueadas for parte in _ids(categoria_id)))
    canales = await _de_categorias(contexto, cliente, "en_vivo", "canales", categoria_id)
    recorte = _pagina(_ordenar(_visibles(canales, bloqueadas, control), orden), desde, limite)
    return _marcar([esquemas.Canal.model_validate(c) for c in recorte], recorte, bloqueadas)


def _ahora() -> datetime:
    return datetime.now(UTC)


@router.get("/canales/{canal_id}/epg", response_model=list[esquemas.ProgramaEpg])
async def obtener_epg_canal(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    canal_id: str,
    limite: Annotated[
        int, Query(ge=1, le=50, description="Cuántos programas, empezando por el actual")
    ] = 10,
) -> list[esquemas.ProgramaEpg]:
    programas = await _consultar(
        contexto.clave("epg", canal_id, limite),
        SEGUNDOS_EPG,
        lambda: xtream.obtener_epg(contexto.credenciales, canal_id, limite, cliente=cliente),
    )
    ahora = _ahora()
    vigentes = [p for p in programas if p.fin > ahora][:limite]
    return [esquemas.ProgramaEpg.model_validate(p) for p in vigentes]


@router.get("/peliculas", response_model=list[esquemas.Pelicula])
async def listar_peliculas(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    control: Control,
    categoria_id: FiltroCategoria = None,
    limite: Limite = None,
    desde: Desde = 0,
    orden: Orden = "proveedor",
    agrupar: Agrupar = False,
) -> list[esquemas.Pelicula]:
    bloqueadas = await _categorias_bloqueadas(contexto, cliente, control.bloqueos, "pelicula")
    control.exigir(any(parte in bloqueadas for parte in _ids(categoria_id)))
    peliculas = await _de_categorias(contexto, cliente, "pelicula", "peliculas", categoria_id)
    visibles = _visibles(peliculas, bloqueadas, control)
    grupos = None
    if agrupar:
        visibles, grupos = _agrupar(_sin_duplicados(visibles))
    recorte = _pagina(_ordenar(visibles, orden), desde, limite)
    return _modelos(esquemas.Pelicula, recorte, bloqueadas, grupos)


@router.get("/peliculas/{pelicula_id}", response_model=esquemas.FichaPelicula)
async def ver_pelicula(
    contexto: ConexionPropia, cliente: ClienteHTTP, control: Control, pelicula_id: str
) -> esquemas.FichaPelicula:
    ficha = await _consultar(
        contexto.clave("pelicula", pelicula_id),
        SEGUNDOS_FICHAS,
        lambda: xtream.obtener_ficha_pelicula(contexto.credenciales, pelicula_id, cliente=cliente),
    )
    bloqueadas = await _categorias_bloqueadas(contexto, cliente, control.bloqueos, "pelicula")
    bloqueada = _esta_bloqueado(ficha.pelicula, bloqueadas)
    control.exigir(bloqueada)
    modelo = esquemas.FichaPelicula.model_validate(ficha)
    modelo.pelicula = _modelos(esquemas.Pelicula, [ficha.pelicula], bloqueadas)[0]
    modelo.clasificacion = await _clasificacion("pelicula", ficha.tmdb_id)
    return modelo


@router.get("/series", response_model=list[esquemas.Serie])
async def listar_series(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    control: Control,
    categoria_id: FiltroCategoria = None,
    limite: Limite = None,
    desde: Desde = 0,
    orden: Orden = "proveedor",
    agrupar: Agrupar = False,
) -> list[esquemas.Serie]:
    bloqueadas = await _categorias_bloqueadas(contexto, cliente, control.bloqueos, "serie")
    control.exigir(any(parte in bloqueadas for parte in _ids(categoria_id)))
    series = await _de_categorias(contexto, cliente, "serie", "series", categoria_id)
    visibles = _visibles(series, bloqueadas, control)
    grupos = None
    if agrupar:
        visibles, grupos = _agrupar(_sin_duplicados(visibles))
    recorte = _pagina(_ordenar(visibles, orden), desde, limite)
    return _modelos(esquemas.Serie, recorte, bloqueadas, grupos)


@router.get("/series/{serie_id}", response_model=esquemas.FichaSerie)
async def ver_serie(
    contexto: ConexionPropia, cliente: ClienteHTTP, control: Control, serie_id: str
) -> esquemas.FichaSerie:
    ficha = await _consultar(
        contexto.clave("serie", serie_id),
        SEGUNDOS_FICHAS,
        lambda: xtream.obtener_ficha_serie(contexto.credenciales, serie_id, cliente=cliente),
    )
    bloqueadas = await _categorias_bloqueadas(contexto, cliente, control.bloqueos, "serie")
    bloqueada = _esta_bloqueado(ficha.serie, bloqueadas)
    control.exigir(bloqueada)
    modelo = esquemas.FichaSerie.model_validate(ficha)
    modelo.serie = _modelos(esquemas.Serie, [ficha.serie], bloqueadas)[0]
    modelo.clasificacion = await _clasificacion("serie", getattr(ficha.serie, "tmdb_id", None))
    return modelo


async def _clasificacion(tipo: str, tmdb_id: str | None) -> str | None:
    if not tmdb_id or not tmdb.disponible():
        return None
    return await cache.obtener_o_calcular(
        f"tmdb:clasificacion:{tipo}:{tmdb_id}",
        lambda: tmdb.clasificacion(tipo, tmdb_id),
        SEGUNDOS_ELENCO,
    )


@router.get("/series/{serie_id}/creditos", response_model=esquemas.CreditosSerie)
async def ver_creditos(
    contexto: ConexionPropia, sesion_bd: SesionBD, serie_id: str
) -> esquemas.CreditosSerie:
    guardado = await sesion_bd.get(CreditosSerie, (contexto.conexion.id, serie_id))
    return esquemas.CreditosSerie(segundos=guardado.segundos if guardado else None)


@router.put("/series/{serie_id}/creditos", response_model=esquemas.CreditosSerie)
async def guardar_creditos(
    datos: esquemas.CreditosSerie, contexto: ConexionPropia, sesion_bd: SesionBD, serie_id: str
) -> esquemas.CreditosSerie:
    if datos.segundos is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Falta segundos")
    guardado = await sesion_bd.get(CreditosSerie, (contexto.conexion.id, serie_id))
    if guardado is None:
        guardado = CreditosSerie(
            conexion_id=contexto.conexion.id, serie_id=serie_id, segundos=datos.segundos
        )
        sesion_bd.add(guardado)
    else:
        guardado.segundos = datos.segundos
        guardado.actualizado_en = datetime.now(UTC)
    await sesion_bd.commit()
    return esquemas.CreditosSerie(segundos=guardado.segundos)


def _sin_duplicados(elementos: list[Any]) -> list[Any]:
    vistos: set[str] = set()
    unicos = []
    for elemento in elementos:
        if elemento.id not in vistos:
            vistos.add(elemento.id)
            unicos.append(elemento)
    return unicos


def _normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


@router.get("/buscar", response_model=esquemas.ResultadoBusqueda)
async def buscar(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    control: Control,
    q: Annotated[str, Query(min_length=2, max_length=80, description="Texto a buscar")],
    limite: Annotated[int, Query(ge=1, le=1000)] = 20,
    agrupar: Agrupar = False,
) -> esquemas.ResultadoBusqueda:
    canales, peliculas, series = await asyncio.gather(
        _consultar(
            contexto.clave("canales", "todas"),
            SEGUNDOS_LISTAS,
            lambda: xtream.obtener_canales(contexto.credenciales, None, cliente=cliente),
        ),
        _consultar(
            contexto.clave("peliculas", "todas"),
            SEGUNDOS_LISTAS,
            lambda: xtream.obtener_peliculas(contexto.credenciales, None, cliente=cliente),
        ),
        _consultar(
            contexto.clave("series", "todas"),
            SEGUNDOS_LISTAS,
            lambda: xtream.obtener_series(contexto.credenciales, None, cliente=cliente),
        ),
    )
    necesidad = _normalizar(q.strip())
    canales, peliculas, series = (
        _sin_duplicados(canales),
        _sin_duplicados(peliculas),
        _sin_duplicados(series),
    )
    b_canales, b_peliculas, b_series = await asyncio.gather(
        _categorias_bloqueadas(contexto, cliente, control.bloqueos, "en_vivo"),
        _categorias_bloqueadas(contexto, cliente, control.bloqueos, "pelicula"),
        _categorias_bloqueadas(contexto, cliente, control.bloqueos, "serie"),
    )
    canales = _visibles(
        [c for c in canales if necesidad in _normalizar(c.nombre)], b_canales, control
    )
    peliculas = _visibles(
        [p for p in peliculas if necesidad in _normalizar(p.nombre)], b_peliculas, control
    )
    series = _visibles([s for s in series if necesidad in _normalizar(s.nombre)], b_series, control)
    g_peliculas = g_series = None
    if agrupar:
        peliculas, g_peliculas = _agrupar(peliculas)
        series, g_series = _agrupar(series)
    totales = {
        "total_canales": len(canales),
        "total_peliculas": len(peliculas),
        "total_series": len(series),
    }
    canales, peliculas, series = canales[:limite], peliculas[:limite], series[:limite]
    return esquemas.ResultadoBusqueda(
        **totales,
        canales=_marcar([esquemas.Canal.model_validate(c) for c in canales], canales, b_canales),
        peliculas=_modelos(esquemas.Pelicula, peliculas, b_peliculas, g_peliculas),
        series=_modelos(esquemas.Serie, series, b_series, g_series),
    )


@router.get("/destacados", response_model=esquemas.Destacados)
async def destacados(
    contexto: ConexionPropia,
    cliente: ClienteHTTP,
    control: Control,
    limite: Annotated[int, Query(ge=1, le=50)] = 12,
) -> esquemas.Destacados:
    peliculas, series = await asyncio.gather(
        _lista_completa(contexto, cliente, "pelicula"), _lista_completa(contexto, cliente, "serie")
    )
    recientes = sorted(_sin_duplicados(peliculas), key=lambda p: p.agregado_en or "", reverse=True)[
        :limite
    ]
    valoradas = sorted(
        series, key=lambda s: (s.calificacion or 0, s.fecha_estreno or ""), reverse=True
    )[:limite]
    b_peliculas, b_series = await asyncio.gather(
        _categorias_bloqueadas(contexto, cliente, control.bloqueos, "pelicula"),
        _categorias_bloqueadas(contexto, cliente, control.bloqueos, "serie"),
    )
    recientes = _visibles(recientes, b_peliculas, control)
    valoradas = _visibles(valoradas, b_series, control)
    return esquemas.Destacados(
        peliculas=_modelos(esquemas.Pelicula, recientes, b_peliculas),
        series=_modelos(esquemas.Serie, valoradas, b_series),
    )


SEGUNDOS_ELENCO = 24 * 3600


@router.get("/peliculas/{pelicula_id}/elenco", response_model=esquemas.Elenco)
async def elenco_pelicula(
    contexto: ConexionPropia, cliente: ClienteHTTP, pelicula_id: str
) -> esquemas.Elenco:
    ficha = await _consultar(
        contexto.clave("pelicula", pelicula_id),
        SEGUNDOS_FICHAS,
        lambda: xtream.obtener_ficha_pelicula(contexto.credenciales, pelicula_id, cliente=cliente),
    )
    if ficha.tmdb_id and tmdb.disponible():
        actores = await cache.obtener_o_calcular(
            f"tmdb:pelicula:{ficha.tmdb_id}",
            lambda: tmdb.reparto_pelicula(ficha.tmdb_id),
            SEGUNDOS_ELENCO,
        )
        if actores:
            return esquemas.Elenco(
                actores=[esquemas.Actor.model_validate(a) for a in actores], fuente="tmdb"
            )
    return esquemas.Elenco(
        actores=[esquemas.Actor.model_validate(a) for a in tmdb.reparto_desde_texto(ficha.reparto)],
        fuente="proveedor",
    )


@router.get("/series/{serie_id}/elenco", response_model=esquemas.Elenco)
async def elenco_serie(
    contexto: ConexionPropia, cliente: ClienteHTTP, serie_id: str
) -> esquemas.Elenco:
    ficha = await _consultar(
        contexto.clave("serie", serie_id),
        SEGUNDOS_FICHAS,
        lambda: xtream.obtener_ficha_serie(contexto.credenciales, serie_id, cliente=cliente),
    )
    return esquemas.Elenco(
        actores=[esquemas.Actor.model_validate(a) for a in tmdb.reparto_desde_texto(ficha.reparto)],
        fuente="proveedor",
    )
