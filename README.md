# FlowCast IPTV · Backend

API de FlowCast, una plataforma de IPTV estilo Netflix. Un solo backend da servicio a todas las apps:

- **App de TV** para Samsung (Tizen) y LG (webOS)
- **App Android** (Kotlin + Jetpack Compose)
- **Panel de administración** web, en `/admin`

El catálogo (canales en vivo, películas y series) se lee del proveedor Xtream Codes de cada cuenta. FlowCast guarda lo que es del usuario: cuentas, perfiles, Mi Lista, Seguir viendo, preferencias y control parental.

## Funciones

- **Cuentas y sesiones:** registro, inicio de sesión con tokens de acceso y de refresco, sesiones por dispositivo y límite de intentos fallidos
- **Seguridad:** contraseñas con Argon2, credenciales del proveedor cifradas, CORS restringido, cabeceras de seguridad y documentación de la API oculta en producción
- **Perfiles:** avatares, perfiles infantiles, preferencias, y audio y subtítulos recordados por serie
- **Catálogo:**
  - canales en vivo con guía de programación (EPG)
  - películas y series agrupadas por idioma, con categorías traducidas
  - búsqueda y ordenamientos
- **Biblioteca:** Mi Lista, Seguir viendo y el historial, sincronizados entre dispositivos
- **Plataformas:** contenido organizado por plataforma de streaming, sincronizado cada día
- **Control parental:** PIN y bloqueo de categorías para adultos
- **Música:** biblioteca de audio propia
- **Administración:**
  - cuentas FlowCast: crear, editar, desactivar y eliminar
  - cuentas de proveedor: varias cuentas, una predeterminada y traspaso de usuarios al eliminar
  - dispositivos con sesión abierta: IP, modelo y sistema

## Tecnología

| | |
|---|---|
| Lenguaje | Python 3.13 |
| API | FastAPI + Uvicorn |
| Base de datos | PostgreSQL 17 con SQLAlchemy (async) |
| Seguridad | Argon2, JWT y cifrado de las credenciales del proveedor |
| Dependencias | [uv](https://docs.astral.sh/uv/) |

## Estructura

```
app/
  routers/    rutas de la API
  services/   lógica: proveedor Xtream, caché, catálogo, plataformas
  models/     tablas de la base de datos
  schemas/    formatos de entrada y salida
  static/     panel de administración
db/           esquema de PostgreSQL
tools/        rutinas: sincronizar plataformas, crear administrador, migraciones
```

## Correr en local

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:aplicacion --reload
```

1. **Base de datos:** crea la base siguiendo [`db/README.md`](db/README.md).
2. **Configuración:** llena el `.env`.
3. **Administrador:** créalo con `uv run python -m tools.crear_administrador`.

La API queda en `http://localhost:8000` y el panel en `http://localhost:8000/admin`.

Con `DOCUMENTACION_PUBLICA=true` en el `.env`, la documentación interactiva queda disponible en `/docs`.

## Calidad de código

```bash
uv run ruff check app
uv run ruff format --check app
```

## Autores

- Álvaro Gómez ([@Pegazusk](https://github.com/Pegazusk))
- Saúl Villeda
