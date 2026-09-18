# Paso

Libreta inteligente para iPad que revisa, corrige y explica desarrollos de ingeniería escritos a mano.

El spec completo está en [docs/SPEC.md](docs/SPEC.md). Las decisiones de diseño, en [docs/decisions/](docs/decisions/).

**Estado: Fase 0** — prueba de concepto sin interfaz. Hay una librería de Python y dos comandos; no hay servidor, base de datos ni frontend todavía. Ver [ADR 0001](docs/decisions/0001-fase0-scope.md).

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

## Qué falta

Fase 1 en adelante (canvas, PWA, backend HTTP, chat, banco de errores, despliegue) según el plan por fases de [docs/SPEC.md](docs/SPEC.md) §10.
