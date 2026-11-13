# Paso

Libreta inteligente para iPad que revisa, corrige y explica desarrollos de ingeniería escritos a mano.

El spec completo está en [docs/SPEC.md](docs/SPEC.md). Las decisiones de diseño, en [docs/decisions/](docs/decisions/).

**Estado: Fase 2 en curso** — la libreta ya puede pedirle una revisión al backend:

- **La libreta** (`frontend/`): PWA para iPad que funciona sin conexión. Ver [ADR 0006](docs/decisions/0006-fase1-frontend.md).
- **El revisor** (`backend/`): transcribe y verifica un desarrollo. Se usa desde la libreta por HTTP ([ADR 0007](docs/decisions/0007-fase2-api.md)) o con dos comandos de terminal ([ADR 0001](docs/decisions/0001-fase0-scope.md)).

## La libreta (frontend)

Requiere **Node 22.12 o más nuevo**. Todo se corre desde `frontend\`.

```powershell
npm install          # instalar dependencias (versiones fijas)
npm run dev          # servidor de desarrollo en http://localhost:5173
npm test             # pruebas (sin red)
npm run build        # compila a dist\
npm run preview      # sirve dist\ en http://localhost:4173, como en producción
npm run deploy       # compila y publica en Cloudflare
```

`npm run dev` no activa el modo sin conexión: el service worker solo existe en la versión compilada. Para probar eso usa `npm run preview`.

### Probar en el iPad

El iPad exige HTTPS para instalar la app y trabajar sin conexión, así que se publica en una dirección fija de Cloudflare:

**https://paso-libreta.paso-frontend.workers.dev**

1. La primera vez, inicia sesión: `npx --yes wrangler@4.161.0 login` (abre el navegador para autorizar).
2. Publica: `npm run deploy`.
3. En el iPad, abre la dirección en Safari → Compartir → **Agregar a inicio**.
4. Ábrela desde el ícono con internet una vez; después funciona en modo avión.

Solo se suben los archivos de la app. **Las notas nunca salen del iPad**: viven en el almacenamiento de Safari para esa dirección. Por eso la dirección no debe cambiar: en otra dirección la app empieza vacía.

Tras publicar una versión nueva, el iPad la descarga al abrir la app con internet y la usa a partir de la siguiente vez que la abras (ciérrala del todo desde el selector de apps).

### Respaldo de las notas

En un cuaderno, botón **⋯** → *Exportar…*: eliges qué páginas van al PDF, o sacas el cuaderno completo como JSON (respaldo). Se abre la hoja de compartir de iOS; desde ahí se guarda en Archivos o Nextcloud. El formato del JSON está en [docs/stroke-format.md](docs/stroke-format.md).

Mientras no exista el respaldo automático al servidor (Fase 5), **exportar es la única copia fuera del iPad**. Safari puede borrar los datos de una app web que lleva semanas sin abrirse.

## El revisor (backend)

Lo que sigue (requisitos, puesta en marcha, comandos, materias, costos y banco de pruebas) es todo del backend.

## Requisitos

- **Python 3.12.** Ya lo tienes en `C:\Users\pakal\AppData\Local\Programs\Python\Python312`.
- **`uv`** para las dependencias.

Ojo con un detalle de Windows: escribir `python` a secas abre la Microsoft Store, porque el alias de ejecución apunta al stub. Usa **`py -3.12`** en su lugar. Todos los comandos de abajo ya lo hacen.

### Instalar uv

```powershell
py -3.12 -m pip install uv
```

Queda en `...\Python312\Scripts\uv.exe`, que no está en el PATH. Por eso los comandos usan `py -3.12 -m uv`. Si prefieres escribir solo `uv`, agrega esa carpeta al PATH.

## Puesta en marcha

```powershell
cd backend
py -3.12 -m uv sync
Copy-Item .env.example .env
```

Abre `backend\.env` y pon tu `ANTHROPIC_API_KEY`. Ese archivo está en `.gitignore` y nunca debe subirse.

## Comandos

Todos se corren desde `backend\`.

```powershell
# Transcribir y verificar una foto
py -3.12 -m uv run python -m app.poc ..\fotos\ed-01.jpg --materia ED

# Igual, pero imprime el JSON completo (útil para armar truth.json)
py -3.12 -m uv run python -m app.poc ..\fotos\ed-01.jpg --materia ED --json

# Correr el banco de pruebas completo
py -3.12 -m uv run python -m app.eval

# Lo mismo desde la caché, sin gastar API
py -3.12 -m uv run python -m app.eval --no-llm

# Tests (no tocan la red: el modelo va simulado)
py -3.12 -m uv run pytest

# Lint y formato
py -3.12 -m uv run ruff check .
py -3.12 -m uv run ruff format .
```

## Materias

Una materia es un archivo YAML en `backend/app/subjects/`. Agregar una **no requiere tocar código** (SPEC §12.5): copia `ed.yaml`, cámbiale el `slug`, la notación, las estrategias de verificación y la taxonomía de errores.

Hoy existen `ed` (Ecuaciones Diferenciales) y `circuitos1` (Circuitos Eléctricos I, solo DC).

## Costos

Cada llamada al API se registra en `backend/usage.jsonl` con tokens y costo estimado. Los precios viven en `backend/app/llm/pricing.yaml`, con la fecha en que se consultaron.

La **caché de reconocimiento** (`backend/.cache/`) guarda la transcripción de cada imagen por (imagen, versión del prompt, modelo). Mientras no cambies el prompt ni el modelo, volver a correr el eval no cuesta nada. Borrarla solo cuesta dinero, nunca datos.

## Banco de pruebas

Cómo agregar ejercicios y anotar la transcripción correcta: [backend/eval/README.md](backend/eval/README.md).

## Revisar desde la libreta

La libreta le manda al backend la selección del lazo y muestra cómo se leyó y qué dice el verificador de cada paso. El backend corre en tu laptop y el iPad lo alcanza por un túnel HTTPS.

### Una sola vez

1. **Clave de Anthropic.** Créala en console.anthropic.com (necesita saldo) y pégala en `backend\.env` como `ANTHROPIC_API_KEY`.
2. **Token de la app.** Genera uno y pégalo en `backend\.env` como `APP_TOKEN`:

```powershell
py -3.12 -c "import secrets; print(secrets.token_hex(24))"
```

3. **Túnel.** Instala cloudflared:

```powershell
winget install Cloudflare.cloudflared
```

### Cada vez que quieras revisar

En una terminal, desde `backend\`:

```powershell
py -3.12 -m uv run python -m uvicorn app.api.main:app --port 8000
```

En otra terminal:

```powershell
cloudflared tunnel --url http://localhost:8000
```

El túnel imprime una dirección `https://….trycloudflare.com`. **Cambia en cada arranque.** En la libreta: **⋯ → Ajustes de revisión…**, pega esa dirección y el token, y toca *Probar conexión*.

Luego, en un cuaderno: herramienta **lazo**, encierra el desarrollo y toca **Revisar**.

### Lo que conviene saber

- Cada revisión cuesta dinero (centavos de dólar). El panel muestra el costo y el gasto del mes. Al llegar a `MONTHLY_BUDGET_USD` el backend rechaza revisiones nuevas.
- La materia del cuaderno decide la notación y las comprobaciones. La plantilla genérica usa la materia `general`.
- Las revisiones se guardan en `backend\data\` (base de datos e imágenes) y también en el iPad: **⋯ → Revisiones guardadas** funciona sin conexión.
- Quien tenga la dirección del túnel **y** el token puede gastar tu clave. No compartas el token; si se filtra, cámbialo en `.env` y reinicia.

## Qué falta

Resto de la Fase 2 (pista, corregir la transcripción, marcas sobre la hoja, banco de pruebas con tinta real) y Fases 3 a 5 (chat, cola sin conexión, banco de errores, respaldo automático, despliegue del backend) según el plan por fases de [docs/SPEC.md](docs/SPEC.md) §10.
