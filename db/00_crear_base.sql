CREATE ROLE flowcast LOGIN PASSWORD :'contrasena_flowcast' NOSUPERUSER NOCREATEDB NOCREATEROLE;

CREATE DATABASE flowcast OWNER flowcast ENCODING 'UTF8' TEMPLATE template0;

COMMENT ON DATABASE flowcast IS 'FlowCast: usuarios, perfiles, conexiones Xtream, favoritos e historial. El catálogo no se guarda aquí.';
