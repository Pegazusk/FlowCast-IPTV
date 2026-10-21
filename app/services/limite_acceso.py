import time

MAXIMO_POR_CUENTA = 5
MAXIMO_POR_IP = 20
SEGUNDOS_VENTANA = 900

_fallos_por_cuenta: dict[str, list[float]] = {}
_fallos_por_ip: dict[str, list[float]] = {}


def _recientes(registro: dict[str, list[float]], clave: str, ahora: float) -> list[float]:
    vigentes = [t for t in registro.get(clave, []) if ahora - t < SEGUNDOS_VENTANA]
    if vigentes:
        registro[clave] = vigentes
    else:
        registro.pop(clave, None)
    return vigentes


def _espera(fallos: list[float], maximo: int, ahora: float) -> int:
    if len(fallos) < maximo:
        return 0
    return int(SEGUNDOS_VENTANA - (ahora - fallos[-maximo])) + 1


def segundos_de_espera(cuenta: str, ip: str | None) -> int:
    ahora = time.monotonic()
    por_cuenta = _espera(_recientes(_fallos_por_cuenta, cuenta, ahora), MAXIMO_POR_CUENTA, ahora)
    por_ip = _espera(_recientes(_fallos_por_ip, ip, ahora), MAXIMO_POR_IP, ahora) if ip else 0
    return max(por_cuenta, por_ip)


def registrar_fallo(cuenta: str, ip: str | None) -> None:
    ahora = time.monotonic()
    _fallos_por_cuenta.setdefault(cuenta, []).append(ahora)
    if ip:
        _fallos_por_ip.setdefault(ip, []).append(ahora)


def registrar_exito(cuenta: str) -> None:
    _fallos_por_cuenta.pop(cuenta, None)


def olvidar() -> None:
    _fallos_por_cuenta.clear()
    _fallos_por_ip.clear()
