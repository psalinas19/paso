# Poner el backend en un servidor

Para dejar de depender de tu laptop y del túnel. La libreta (`paso-libreta.paso-frontend.workers.dev`) no cambia: solo cambia a dónde manda las revisiones.

> **Aviso.** Los comandos de Fly.io y de Cloudflare R2 de esta guía están escritos de memoria; no pude ejecutarlos ni leer su documentación al escribirla. Lo que sí está probado es todo lo nuestro: la imagen, el respaldo y la restauración. Si un comando de `fly` no existe o pide otra cosa, `fly help <comando>` manda, y me dices para corregir la guía.

Hay dos caminos. Elige uno. El paso 1 (respaldos) es igual en los dos.

## 1. Un lugar para los respaldos, fuera del servidor (Cloudflare R2)

Sin esto los respaldos quedan en el mismo disco que protegen.

1. En el panel de Cloudflare: **R2** → crear un bucket, por ejemplo `paso-respaldos`.
2. **R2 → Manage API Tokens** → crear un token con permiso de **lectura y escritura de objetos**, limitado a ese bucket.
3. Apunta tres cosas: *Access Key ID*, *Secret Access Key* y el *endpoint* (`https://<id-de-cuenta>.r2.cloudflarestorage.com`).

Esos tres datos y el nombre del bucket van en las variables de abajo. Son secretos: no los pegues en ningún chat.

```
BACKUP_REMOTE=r2:paso-respaldos
RCLONE_CONFIG_R2_TYPE=s3
RCLONE_CONFIG_R2_PROVIDER=Cloudflare
RCLONE_CONFIG_R2_ACCESS_KEY_ID=...
RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=...
RCLONE_CONFIG_R2_ENDPOINT=https://<id-de-cuenta>.r2.cloudflarestorage.com
RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
```

## Opción A: Fly.io

Desde `backend\` en tu Windows.

1. Instala `flyctl` y entra a tu cuenta (te pedirá una tarjeta):

```powershell
fly auth login
```

2. Crea la app con un nombre tuyo (será `ese-nombre.fly.dev`). No despliega todavía:

```powershell
fly launch --no-deploy --copy-config --name paso-tunombre --region qro
```

3. Crea el disco donde vivirán los datos:

```powershell
fly volumes create paso_data --size 3 --region qro
```

4. Guarda los secretos. `APP_TOKEN` puede ser el mismo que ya usas en el iPad. Agrega aquí también las siete variables del paso 1:

```powershell
fly secrets set ANTHROPIC_API_KEY=sk-ant-... APP_TOKEN=... BACKUP_REMOTE=r2:paso-respaldos RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare RCLONE_CONFIG_R2_ACCESS_KEY_ID=... RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=... RCLONE_CONFIG_R2_ENDPOINT=https://....r2.cloudflarestorage.com RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
```

5. Despliega:

```powershell
fly deploy
```

6. Comprueba que responde (debe decir `{"ok":true}`):

```powershell
curl https://paso-tunombre.fly.dev/api/ping
```

El límite de gasto, el modelo y lo demás se cambian en `backend\fly.toml`, sección `[env]`, y se aplican con otro `fly deploy`.

## Opción B: un servidor propio con Docker

1. Renta el servidor más chico con 1 GB de RAM (Ubuntu) e instala Docker.
2. Consigue un nombre que apunte a su dirección IP: un subdominio gratis en DuckDNS o un dominio tuyo.
3. Abre los puertos 80 y 443.
4. En el servidor:

```bash
git clone https://github.com/psalinas19/paso.git
```

```bash
cd paso/deploy && cp ../backend/.env.example .env
```

5. Edita `deploy/.env`: pon `ANTHROPIC_API_KEY`, `APP_TOKEN`, `PASO_DOMAIN` (el nombre del paso 2) y las variables del paso 1. Deja `DATA_DIR` y `BACKUP_DIR` como vienen comentadas: el contenedor ya las trae.
6. Arranca:

```bash
docker compose up -d --build
```

7. Comprueba, desde cualquier lado:

```bash
curl https://tu-nombre.duckdns.org/api/ping
```

Para actualizar después: `git pull` y otra vez `docker compose up -d --build`.

## 2. Llevar al servidor lo que ya tienes en la laptop

Tus revisiones, el banco de errores y el gasto del mes están en `backend\data\`. Para no empezar de cero:

1. En la laptop, desde `backend\`, haz un respaldo (queda en `backend\backups\`):

```powershell
py -3.12 -m uv run python -m app.backup create
```

2. Sube ese archivo `paso-....tar.gz` a tu bucket de R2 desde el panel de Cloudflare.
3. En el servidor, tráelo y restáuralo. Con Fly:

```powershell
fly ssh console -C "python -m app.backup fetch"
```

```powershell
fly ssh console -C "sh -c 'python -m app.backup restore /data/backups/paso-*.tar.gz --force'"
```

```powershell
fly apps restart paso-tunombre
```

Con Docker (opción B), desde `deploy/`:

```bash
docker compose stop api
```

```bash
docker compose run --rm api sh -c 'python -m app.backup fetch && python -m app.backup restore /backups/paso-*.tar.gz --force'
```

```bash
docker compose up -d
```

`--force` no borra lo que había: lo aparta a una carpeta `antes-de-restaurar-...` dentro de los respaldos.

## 3. Apuntar el iPad al servidor

En la libreta: abre un cuaderno → **⋯ → Ajustes de revisión…** → pon la dirección nueva (`https://paso-tunombre.fly.dev` o la de tu dominio) y el token → **Probar conexión**.

El mensaje de la prueba dice también cómo va el respaldo del servidor. Debe decir «con copia fuera del servidor». Si dice «SIN copia fuera del servidor», revisa las variables del paso 1.

Desde ese momento los cuadernos empiezan a subirse solos. En la biblioteca, la línea bajo el título dice cuándo todos tienen copia.

## Los respaldos, en corto

- **Cuándo:** una vez al día, solos. También puedes pedir uno: `python -m app.backup create`.
- **Qué llevan:** la base de datos, las imágenes de las revisiones y la copia de cada cuaderno. Son `.tar.gz` normales: se abren sin esta app.
- **Cuánto se guarda:** todos los de 14 días, luego uno por semana durante 8 semanas, luego uno por mes durante un año. Se cambia con `BACKUP_KEEP_DAYS`, `BACKUP_KEEP_WEEKS` y `BACKUP_KEEP_MONTHS`.
- **Ver cuáles hay:** `python -m app.backup list`.

## Si el servidor se pierde

1. Crea uno nuevo siguiendo la opción A o B, con las mismas variables del paso 1.
2. Trae y restaura el respaldo más nuevo, con los comandos del apartado 2 (sin `--force` si el servidor está vacío).
3. Arranca. La base de datos se pone al día sola.

Esto está probado con la imagen real: `deploy/prueba-restauracion.sh` crea un servidor de prueba, le guarda un cuaderno, lo respalda, borra servidor y datos, y lo recupera desde la copia externa. GitHub lo corre en cada cambio del backend.

Para probarlo tú, con Docker instalado:

```bash
docker build -t paso-backend backend
```

```bash
deploy/prueba-restauracion.sh
```

**Haz un simulacro una vez por semestre.** Un respaldo que nunca se ha restaurado es una esperanza, no un respaldo.

## Si el iPad se pierde o Safari borra sus datos

En la biblioteca, abajo: **Recuperar del servidor → Buscar en el servidor**. Lista los cuadernos que el servidor guarda y el iPad no tiene, y **Recuperar** los trae a su semestre y materia.

Las revisiones no se pierden: viven en el servidor. Lo que el iPad guardaba de ellas (para leerlas sin conexión) se vuelve a llenar al usarlas.
