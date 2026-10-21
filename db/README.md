# Base de datos de FlowCast

PostgreSQL 17. Guarda cuentas, perfiles, conexiones Xtream, favoritos,
progreso, historial y reseñas. El catálogo se lee del servidor Xtream en
cada consulta y no se guarda aquí.

Tablas: `usuario`, `sesion_autenticacion`, `perfil`, `conexion_xtream`,
`favorito`, `progreso_reproduccion`, `historial`, `resena`.

## Crear desde cero (macOS con Homebrew)

```bash
brew install postgresql@17
brew services start postgresql@17
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"

psql -h localhost -d postgres -v contrasena_flowcast='TU_CONTRASEÑA' -f db/00_crear_base.sql
psql -h localhost -U flowcast -d flowcast -f db/01_esquema.sql
```

El primer comando crea el rol y la base; el segundo, todas las tablas. Después
pon la misma contraseña en `URL_BASE_DATOS` dentro de `.env`.

## Empezar de cero

```bash
psql -h localhost -d postgres -c "DROP DATABASE IF EXISTS flowcast" -c "DROP ROLE IF EXISTS flowcast"
```

## Respaldos

```bash
mkdir -p db/respaldos
pg_dump -h localhost -U flowcast flowcast > db/respaldos/$(date +%Y%m%d).sql
```

La carpeta `db/respaldos/` está ignorada por git porque contiene datos reales.

## Nota sobre la autenticación local

La instalación de Homebrew deja `pg_hba.conf` en modo `trust` para conexiones
locales: PostgreSQL no verifica la contraseña en tu Mac. El backend la envía de
todas formas, así que en un servidor real funcionará igual sin cambiar código.
