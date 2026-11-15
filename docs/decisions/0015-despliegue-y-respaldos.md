# ADR 0015 — Despliegue, respaldos y archivo de semestres

**Fecha:** 2026-11-15
**Estado:** aceptado; construido. El despliegue real espera la decisión de hosting.

## Contexto

Fase 5 del SPEC (§10) y lo que el §5 daba por hecho y no existía: que el servidor guarde los cuadernos. [Plan](../plan-fase5.md), [guía](../despliegue.md).

## Decisiones

### Los cuadernos en el servidor

**El servidor guarda cada cuaderno como el `.paso.json` que la app ya exporta.** No se inventó un formato: una copia se puede abrir a mano, importar en otra instalación o leer con otro programa (SPEC §12.1). La tabla `NotebookBackup` es solo su ficha para listarlos.

**Solo subida, sin mezclar.** Hay un dispositivo (SPEC §3); la última subida es el cuaderno. No hay resolución de conflictos que mantener.

**Dos redes contra una subida mala:** la versión anterior queda junto a la nueva (`.prev`), y el respaldo diario guarda las más viejas.

**La libreta sube en segundo plano** lo que cambió: cada pocos minutos, al mandar la app al fondo y al salir del cuaderno. Es gratis, así que no rompe la regla 33. Un cuaderno queda «pendiente» desde su primer cambio hasta que el servidor responde con lo que guardó, y la libreta compara páginas y trazos: si el servidor guardó menos, es un fallo.

**Borrar un cuaderno en el iPad no borra la copia del servidor.** Los datos son el activo.

### Archivar un semestre

**Nada sale del iPad hasta que el servidor confirma que lo tiene todo.** Se sube cada cuaderno y se comprueba; si uno falla, no se quita ninguno.

**Un cuaderno archivado sigue en la biblioteca**, marcado como «en el servidor». Al abrirlo se descarga y se muestra en solo lectura (SPEC §5): el lienzo no acepta tinta y la barra solo deja lo que mira.

**La restauración conserva los ids** de páginas y trazos. Las revisiones, las marcas, las gráficas y los ejercicios de repaso apuntan a ellos; con ids nuevos quedarían huérfanos. (Importar un archivo a mano sigue creando ids nuevos, para no pisar nada.)

**Un cuaderno archivado nunca se sube:** aquí está vacío, y subirlo reemplazaría la copia buena por nada. Es la comprobación más importante del módulo y tiene prueba.

**Liberar espacio vuelve a preguntar al servidor** antes de quitar del iPad un archivado que se había descargado.

### Respaldo del servidor

**Lo hace el propio proceso del API**, en un hilo, cuando `BACKUP_ENABLED` está encendido. Un contenedor, un proceso: sirve igual en Fly (un volumen por máquina) y con Docker Compose. Mira cada diez minutos si el último respaldo bueno tiene un día; un servidor que estuvo apagado se pone al corriente al volver, y un respaldo fallido se reintenta en una hora.

**La base se copia con el respaldo en línea de SQLite**, no copiando el archivo: sale consistente aunque el API esté escribiendo.

**Fuera del servidor con `rclone`.** El destino es configuración, no código: R2, un Nextcloud, otro disco. Tras subir se comprueba que el archivo aparece en el destino.

**La retención del destino se decide leyendo el destino**, nunca copiando el estado de este disco: un servidor nuevo, con la carpeta vacía, no debe vaciar el almacenamiento externo. Se guarda todo 14 días, luego uno por semana 8 semanas, luego uno por mes un año; el más nuevo nunca se borra.

**Restaurar no borra:** lo que había se aparta a una carpeta. Antes de tocar nada se valida el archivo (que sea nuestro, sin rutas que se salgan, y que la base pase `integrity_check`).

**Sin almacenamiento externo, el respaldo funciona y lo dice:** «está solo en este servidor». La libreta lo muestra en mayúsculas en Ajustes.

### Contenedor y hosting

**Una imagen para todo:** Python 3.12, dependencias exactas de `uv.lock`, `rclone` de su imagen oficial con versión fija, usuario sin privilegios. Solo escribe en `/data` y `/backups`.

**`/api/ping` es la única ruta sin token** y solo dice que el proceso vive: el hosting necesita comprobarlo sin conocer el secreto.

**La prueba de restauración es un script que corre en GitHub** en cada cambio del backend: construye la imagen, guarda un cuaderno, respalda, borra contenedor y volúmenes, y recupera desde una carpeta que hace de almacenamiento externo. Encontró un fallo real que las pruebas unitarias no veían: la restauración escribía fuera de los volúmenes, donde el usuario del contenedor no puede.

**Hosting: dos opciones preparadas, ninguna elegida** (Fly.io y un servidor propio con Compose y Caddy). El SPEC deja la decisión al usuario.

## Lo que queda fuera

- Varios dispositivos escribiendo el mismo cuaderno (fuera del alcance, SPEC §3).
- Historial de versiones de un cuaderno a la vista: existe en los respaldos diarios, no en la app.
- Borrar copias del servidor desde la app: existe la ruta, no el botón.
- Cifrar los respaldos antes de subirlos: `rclone crypt` lo permite por configuración; no se activó.

## Sin comprobar

El despliegue en Fly, la subida a R2 con credenciales reales y el certificado de Caddy. Los comandos de la guía están escritos de memoria.
