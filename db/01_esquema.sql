BEGIN;

CREATE TABLE usuario (
    id              uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    correo          text         NOT NULL,
    hash_contrasena text         NOT NULL,
    hash_pin_parental text,
    nombre          varchar(120) NOT NULL,
    activo          boolean      NOT NULL DEFAULT true,
    creado_en       timestamptz  NOT NULL DEFAULT now(),
    nombre_usuario  text,
    es_administrador boolean     NOT NULL DEFAULT false,
    CONSTRAINT usuario_nombre_usuario_formato CHECK (nombre_usuario ~ '^[a-z0-9._-]{3,40}$')
);
CREATE UNIQUE INDEX usuario_correo_unico ON usuario (lower(correo));
CREATE UNIQUE INDEX usuario_nombre_usuario_unico ON usuario (lower(nombre_usuario));
CREATE TABLE sesion_autenticacion (
    id                  uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id          uuid         NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    hash_token_refresco text         NOT NULL UNIQUE,
    nombre_dispositivo  varchar(120),
    creado_en           timestamptz  NOT NULL DEFAULT now(),
    expira_en           timestamptz  NOT NULL,
    revocado_en         timestamptz,
    iniciada_en         timestamptz  NOT NULL DEFAULT now(),
    ultimo_uso_en       timestamptz  NOT NULL DEFAULT now(),
    ip_inicio           text,
    ip_ultima           text,
    agente_usuario      text,
    dispositivo         jsonb        NOT NULL DEFAULT '{}'
);
CREATE INDEX sesion_autenticacion_usuario_idx ON sesion_autenticacion (usuario_id);
CREATE TABLE perfil (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id        uuid        NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    nombre            varchar(80) NOT NULL,
    avatar            varchar(40) NOT NULL DEFAULT '01',
    es_infantil       boolean     NOT NULL DEFAULT false,
    hash_pin_parental text,
    imagen_avatar     bytea,
    imagen_tipo       varchar(40),
    imagen_actualizada_en timestamptz,
    preferencias      jsonb       NOT NULL DEFAULT '{}',
    creado_en         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (usuario_id, nombre)
);

CREATE TABLE cuenta_proveedor (
    id                     uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    etiqueta               varchar(120) NOT NULL,
    url_base_cifrada       bytea        NOT NULL,
    nombre_usuario_cifrado bytea        NOT NULL,
    contrasena_cifrada     bytea        NOT NULL,
    huella                 text         NOT NULL UNIQUE,
    notas                  text,
    predeterminada         boolean      NOT NULL DEFAULT false,
    estado_cuenta          varchar(20)  NOT NULL DEFAULT 'desconocido',
    expira_en              timestamptz,
    max_conexiones         integer,
    conexiones_activas     integer,
    ultima_revision_en     timestamptz,
    creado_en              timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE conexion_xtream (
    id                         uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id                 uuid         NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    cuenta_proveedor_id        uuid         REFERENCES cuenta_proveedor(id) ON DELETE SET NULL,
    etiqueta                   varchar(120) NOT NULL,
    url_base_cifrada           bytea        NOT NULL,
    nombre_usuario_cifrado     bytea        NOT NULL,
    huella                     text         NOT NULL,
    contrasena_cifrada         bytea        NOT NULL,
    estado_cuenta              varchar(20)  NOT NULL DEFAULT 'desconocido'
                               CHECK (estado_cuenta IN ('desconocido', 'activa', 'expirada', 'bloqueada', 'deshabilitada')),
    expira_en                  timestamptz,
    max_conexiones             integer      CHECK (max_conexiones IS NULL OR max_conexiones > 0),
    zona_horaria_servidor      text,
    formatos_salida_permitidos text[],
    ultima_autenticacion_en    timestamptz,
    creado_en                  timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT conexion_xtream_usuario_huella_unica UNIQUE (usuario_id, huella)
);
CREATE INDEX conexion_xtream_usuario_idx ON conexion_xtream (usuario_id);

CREATE TABLE categoria_bloqueada (
    usuario_id     uuid        NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    conexion_id    uuid        NOT NULL REFERENCES conexion_xtream(id) ON DELETE CASCADE,
    tipo_contenido varchar(10) NOT NULL CHECK (tipo_contenido IN ('en_vivo', 'pelicula', 'serie')),
    categoria_id   text        NOT NULL,
    bloqueada      boolean     NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (usuario_id, conexion_id, tipo_contenido, categoria_id)
);
COMMENT ON TABLE categoria_bloqueada IS 'Categorías que el usuario bloqueó o desbloqueó a mano; las de adultos se bloquean solas.';

CREATE TABLE favorito (
    perfil_id      uuid        NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
    conexion_id    uuid        NOT NULL REFERENCES conexion_xtream(id) ON DELETE CASCADE,
    tipo_contenido varchar(10) NOT NULL CHECK (tipo_contenido IN ('en_vivo', 'pelicula', 'serie')),
    stream_id      text        NOT NULL,
    titulo         text        NOT NULL,
    url_portada    text,
    creado_en      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (perfil_id, conexion_id, tipo_contenido, stream_id)
);

CREATE TABLE progreso_reproduccion (
    perfil_id         uuid          NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
    conexion_id       uuid          NOT NULL REFERENCES conexion_xtream(id) ON DELETE CASCADE,
    tipo_contenido    varchar(10)   NOT NULL CHECK (tipo_contenido IN ('pelicula', 'episodio')),
    stream_id         text          NOT NULL,
    serie_id          text,
    titulo            text          NOT NULL,
    url_portada       text,
    posicion_segundos numeric(10,3) NOT NULL DEFAULT 0 CHECK (posicion_segundos >= 0),
    duracion_segundos numeric(10,3) CHECK (duracion_segundos IS NULL OR duracion_segundos > 0),
    completado        boolean       NOT NULL DEFAULT false,
    actualizado_en    timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (perfil_id, conexion_id, tipo_contenido, stream_id),
    CONSTRAINT progreso_posicion_dentro_de_duracion
        CHECK (duracion_segundos IS NULL OR posicion_segundos <= duracion_segundos),
    CONSTRAINT progreso_episodio_requiere_serie
        CHECK (tipo_contenido <> 'episodio' OR serie_id IS NOT NULL)
);
CREATE INDEX progreso_reproduccion_continuar_idx
    ON progreso_reproduccion (perfil_id, actualizado_en DESC) WHERE NOT completado;
CREATE TABLE historial (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    perfil_id      uuid        NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
    conexion_id    uuid        NOT NULL REFERENCES conexion_xtream(id) ON DELETE CASCADE,
    tipo_contenido varchar(10) NOT NULL CHECK (tipo_contenido IN ('en_vivo', 'pelicula', 'episodio')),
    stream_id      text        NOT NULL,
    titulo         text        NOT NULL,
    url_portada    text,
    reproducido_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX historial_perfil_idx ON historial (perfil_id, reproducido_en DESC);

CREATE TABLE resena (
    id               bigserial   PRIMARY KEY,
    perfil_id        uuid        NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
    servidor_huella  char(64)    NOT NULL,
    tipo_contenido   varchar(10) NOT NULL CHECK (tipo_contenido IN ('en_vivo', 'pelicula', 'serie')),
    stream_id        text        NOT NULL,
    titulo           text        NOT NULL,
    calificacion     smallint    NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    texto            text,
    creado_en        timestamptz NOT NULL DEFAULT now(),
    actualizado_en   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (perfil_id, servidor_huella, tipo_contenido, stream_id)
);
CREATE INDEX resena_contenido_idx ON resena (servidor_huella, tipo_contenido, stream_id);

CREATE TABLE plataforma (
    clave  varchar(30) PRIMARY KEY,
    nombre text        NOT NULL,
    logo   text,
    orden  integer     NOT NULL DEFAULT 1000
);

CREATE TABLE disponibilidad_tmdb (
    tipo_contenido varchar(10) NOT NULL CHECK (tipo_contenido IN ('pelicula', 'serie')),
    tmdb_id        text        NOT NULL,
    plataformas    text[]      NOT NULL DEFAULT '{}',
    consultado_en  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tipo_contenido, tmdb_id)
);
CREATE INDEX disponibilidad_tmdb_plataformas_idx ON disponibilidad_tmdb USING gin (plataformas);
COMMIT;

CREATE TABLE creditos_serie (
    conexion_id    uuid        NOT NULL REFERENCES conexion_xtream(id) ON DELETE CASCADE,
    serie_id       text        NOT NULL,
    segundos       real        NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (conexion_id, serie_id)
);

CREATE TABLE pistas_serie (
    perfil_id      uuid        NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
    conexion_id    uuid        NOT NULL REFERENCES conexion_xtream(id) ON DELETE CASCADE,
    serie_id       text        NOT NULL,
    audio          varchar(40),
    subtitulos     varchar(40),
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (perfil_id, conexion_id, serie_id)
);
