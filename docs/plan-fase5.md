# Plan de la Fase 5: despliegue

**Fecha:** 2026-11-15 · **Estado:** construido todo lo que no depende de elegir hosting. **Falta tu decisión de hosting y desplegarlo con tus cuentas**: yo no puedo hacerlo desde aquí (no tengo tu clave de Anthropic ni tus cuentas, y así debe ser).

## Qué pide el SPEC (§10 y §5)

| Pide | Estado |
|---|---|
| Dos opciones de hosting baratas con costo, y esperar tu decisión | Abajo. **Tú eliges.** |
| Backend en Docker | Hecho: `backend/Dockerfile`. Se construye en GitHub en cada cambio. |
| HTTPS | Lo da el hosting (opción A) o Caddy (opción B). Configurado en ambos. |
| Límite de gasto activo | Ya existía (`MONTHLY_BUDGET_USD`); va en la configuración de las dos opciones. |
| Respaldo diario, fuera del servidor, con retención | Hecho: lo hace el propio backend y lo sube con `rclone`. |
| Script de restauración **probado** | Hecho y probado con la imagen real: `deploy/prueba-restauracion.sh` borra un servidor de prueba y lo recupera. |
| Flujo para archivar un semestre | Hecho, junto con lo que necesitaba: que los cuadernos se respalden en el servidor. |
| README final | Hecho. |

## Algo que no estaba hecho y era urgente

Hasta hoy **tus notas vivían solo en el iPad**. El SPEC (§5) dice que el servidor es la fuente de verdad a largo plazo, porque Safari puede borrar los datos de un sitio. Eso entra en esta fase:

- Cada cuaderno se sube solo al servidor, en segundo plano. No cuesta (no pasa por el modelo).
- La biblioteca dice si algún cuaderno tiene cambios sin copia.
- Si el iPad se pierde o Safari borra todo, **Recuperar del servidor** los trae de vuelta.

## Las dos opciones de hosting

Los precios los consulté el 2026-11-15, pero **no pude abrir las páginas oficiales desde esta sesión**: salen de resúmenes de búsqueda. Confírmalos en la página de precios antes de pagar.

| | **A. Fly.io** (recomendada) | **B. Servidor propio (DigitalOcean)** |
|---|---|---|
| Qué es | Le das el contenedor y ellos lo corren | Rentas una máquina Linux y tú la administras |
| Costo al mes | ≈ **4 USD** (512 MB + disco de 3 GB) | **6 USD** (1 GB de RAM, 25 GB de disco) |
| HTTPS y dirección | Incluidos: `tu-nombre.fly.dev` | Caddy lo pone solo, pero necesitas un nombre: gratis con DuckDNS o un dominio (≈ 10 USD al año) |
| Cómo se despliega | Un comando desde tu Windows: `fly deploy` | Por SSH: `docker compose up -d --build` |
| Mantenimiento | Casi ninguno | Tú actualizas el sistema y cuidas el acceso por SSH |
| Dónde corre | Hay región en Querétaro | Estados Unidos |
| Lo malo | Se cobra por uso: la cuenta varía un poco. No hay capa gratuita. | Es un servidor más que cuidar. Si lo descuidas, es un riesgo. |

**Recomiendo la A.** Cuesta menos, no hay un Linux que mantener y se despliega desde Windows con un comando. Medí el contenedor: usa unos 190 MB con el verificador caliente, así que la máquina de 512 MB alcanza.

Otras que miré y descarté:

- **Hetzner:** era la barata de siempre, pero subió precios dos veces en 2026, lo económico solo está en Europa y hubo semanas sin poder contratar.
- **Oracle «siempre gratis»:** cuesta 0, pero Oracle apaga las máquinas que usan poco, y esta usaría poco.
- **Render y Railway:** parecidas a Fly, algo más caras para este uso.

**Almacenamiento externo para los respaldos:** Cloudflare R2. Los primeros 10 GB son gratis y ya tienes cuenta de Cloudflare (ahí está publicada la libreta). Cualquier otro destino que `rclone` conozca sirve igual (un Nextcloud, Google Drive).

## Qué se construyó

1. **Copia de los cuadernos en el servidor**, con subida automática, estado en la biblioteca y recuperación.
2. **Archivar un semestre:** sube y confirma cada cuaderno, y solo entonces lo quita del iPad. Los archivados se abren con conexión y solo para leer. Se puede desarchivar.
3. **Respaldo diario del servidor** (base de datos, imágenes y cuadernos) con copia fuera, retención y restauración.
4. **Contenedor**, configuración para las dos opciones y una prueba automática de restauración.
5. **Guía paso a paso:** [docs/despliegue.md](despliegue.md).

Decisiones técnicas en el [ADR 0015](decisions/0015-despliegue-y-respaldos.md).

## Lo que no pude comprobar

- **El despliegue en sí.** Los archivos de Fly (`backend/fly.toml`) y los comandos de la guía están escritos de memoria: no pude ejecutar `fly` ni leer su documentación desde aquí. Si un comando cambió, `fly help` manda.
- **La subida a R2.** Probé el respaldo, la subida y la restauración con una carpeta haciendo de almacenamiento externo. Con R2 de verdad no, porque no tengo tus credenciales.
- **El certificado de Caddy** (necesita un dominio real apuntando a un servidor real).
- **El criterio del SPEC:** «funciona desde la red de la universidad sin mi laptop encendida». Solo se sabe allá.
- **Todo en el iPad**, como siempre.

## Decisiones que te tocan

1. **¿Opción A o B?** Con eso sigues la guía; son unos 30 a 45 minutos.
2. **¿R2 para los respaldos?** Si prefieres otro destino, dime cuál y ajusto el ejemplo.
3. Al terminar el despliegue hay que **cambiar la dirección del backend en el iPad** (Ajustes de revisión). La dirección de la libreta no cambia.
