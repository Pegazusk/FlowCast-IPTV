import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

MAXIMO_SIMULTANEAS = 2
PAUSA_SEGUNDOS = 0.25


class _FrenoServidor:
    def __init__(self, bucle: asyncio.AbstractEventLoop) -> None:
        self.bucle = bucle
        self.semaforo = asyncio.Semaphore(MAXIMO_SIMULTANEAS)
        self.candado = asyncio.Lock()
        self.proximo_turno = 0.0


_frenos: dict[str, _FrenoServidor] = {}


def _servidor(url_base: str) -> str:
    return (urlsplit(url_base).netloc or url_base).lower()


def _freno_para(url_base: str) -> _FrenoServidor:
    bucle = asyncio.get_running_loop()
    servidor = _servidor(url_base)
    freno = _frenos.get(servidor)
    if freno is None or freno.bucle is not bucle:
        freno = _FrenoServidor(bucle)
        _frenos[servidor] = freno
    return freno


@asynccontextmanager
async def turno(url_base: str) -> AsyncIterator[None]:
    freno = _freno_para(url_base)
    async with freno.semaforo:
        async with freno.candado:
            ahora = time.monotonic()
            espera = freno.proximo_turno - ahora
            if espera > 0:
                await asyncio.sleep(espera)
            freno.proximo_turno = max(ahora, freno.proximo_turno) + PAUSA_SEGUNDOS
        yield
