import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

SEGUNDOS_POR_DEFECTO = 300
MAXIMO_ENTRADAS = 2000

_entradas: dict[str, tuple[float, Any]] = {}
_candados: dict[str, asyncio.Lock] = {}
_respaldos: dict[str, Any] = {}
registro = logging.getLogger("flowcast.cache")
_renovando: set[str] = set()
_AUSENTE = object()


async def obtener_o_calcular(
    clave: str,
    fabrica: Callable[[], Awaitable[Any]],
    segundos: int = SEGUNDOS_POR_DEFECTO,
) -> Any:
    valor = _leer(clave)
    if valor is not _AUSENTE:
        return valor
    candado = _candados.setdefault(clave, asyncio.Lock())
    async with candado:
        valor = _leer(clave)
        if valor is not _AUSENTE:
            return valor
        valor = await fabrica()
        guardar(clave, valor, segundos)
        return valor


async def obtener_con_respaldo(
    clave: str,
    fabrica: Callable[[], Awaitable[Any]],
    segundos: int = SEGUNDOS_POR_DEFECTO,
) -> Any:
    valor = _leer(clave)
    if valor is not _AUSENTE:
        return valor
    if clave in _respaldos:
        if clave not in _renovando:
            _renovando.add(clave)
            asyncio.get_running_loop().create_task(_renovar(clave, fabrica, segundos))
        return _respaldos[clave]
    valor = await obtener_o_calcular(clave, fabrica, segundos)
    _respaldos[clave] = valor
    return valor


async def _renovar(clave: str, fabrica: Callable[[], Awaitable[Any]], segundos: int) -> None:
    try:
        guardar_con_respaldo(clave, await fabrica(), segundos)
    except Exception:
        registro.exception("No se pudo renovar %s; se sigue usando la copia anterior", clave)
    finally:
        _renovando.discard(clave)


def guardar_con_respaldo(clave: str, valor: Any, segundos: int = SEGUNDOS_POR_DEFECTO) -> None:
    guardar(clave, valor, segundos)
    _respaldos[clave] = valor


def guardar(clave: str, valor: Any, segundos: int = SEGUNDOS_POR_DEFECTO) -> None:
    if len(_entradas) >= MAXIMO_ENTRADAS:
        _hacer_sitio()
    _entradas[clave] = (time.monotonic() + segundos, valor)


def invalidar(prefijo: str) -> int:
    claves = [clave for clave in _entradas if clave.startswith(prefijo)]
    for clave in claves:
        _entradas.pop(clave, None)
        _candados.pop(clave, None)
    for clave in [clave for clave in _respaldos if clave.startswith(prefijo)]:
        _respaldos.pop(clave, None)
    return len(claves)


def vaciar() -> None:
    _entradas.clear()
    _candados.clear()
    _respaldos.clear()
    _renovando.clear()


def _leer(clave: str) -> Any:
    entrada = _entradas.get(clave)
    if entrada is None:
        return _AUSENTE
    caduca_en, valor = entrada
    if caduca_en <= time.monotonic():
        _entradas.pop(clave, None)
        return _AUSENTE
    return valor


def _hacer_sitio() -> None:
    ahora = time.monotonic()
    for clave in [clave for clave, (caduca_en, _) in _entradas.items() if caduca_en <= ahora]:
        _entradas.pop(clave, None)
    if len(_entradas) >= MAXIMO_ENTRADAS:
        por_caducidad = sorted(_entradas.items(), key=lambda elemento: elemento[1][0])
        for clave, _ in por_caducidad[: max(1, MAXIMO_ENTRADAS // 10)]:
            _entradas.pop(clave, None)
