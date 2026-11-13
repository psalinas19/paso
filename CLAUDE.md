# CLAUDE.md

Contexto para Claude Code. El spec manda: [docs/SPEC.md](docs/SPEC.md). Trabaja **una fase a la vez** (§10), presenta plan y espera aprobación al iniciar cada fase.

## Comandos

Desde `backend/`. En Windows, `python` a secas es el stub de Microsoft Store: usa `py -3.12`.

```powershell
py -3.12 -m uv sync                                   # instalar
py -3.12 -m uv run python -m pytest                   # tests (sin red)
py -3.12 -m uv run ruff check . ; py -3.12 -m uv run ruff format .
py -3.12 -m uv run python -m app.poc <img> --materia ED
py -3.12 -m uv run python -m app.eval [--no-llm] [--case <id>]
py -3.12 -m uv run python -m uvicorn app.api.main:app --port 8000   # API HTTP
```

Desde `frontend/` (Node ≥ 22.12):

```powershell
npm install ; npm test ; npm run build
npm run preview        # dist/ en :4173; el service worker solo existe compilado
npm run deploy         # publica en https://paso-libreta.paso-frontend.workers.dev
```

## Estado

Fase 2, entrega 2a construida: la libreta manda la selección del lazo a `POST /api/check` y muestra transcripción y verificación ([ADR 0007](docs/decisions/0007-fase2-api.md)). Faltan 2b (banco de pruebas, corregir transcripción, pista) y 2c (marcas sobre la hoja). **El reconocimiento aún no se ha medido con el API real: `eval/cases/` está vacío.** Fase 1 sigue en prueba en el iPad ([ADR 0006](docs/decisions/0006-fase1-frontend.md)).

## Arquitectura

```
app/schemas.py            contratos Pydantic; el resto cuelga de aquí
app/subjects/             una materia = un YAML (SPEC 12.5)
app/llm/                  proveedor de IA detrás de LLMProvider (SPEC 12.3)
app/recognition/          imagen -> pasos
app/verification/         pasos -> estados, registro de estrategias
app/evaluation/           métricas del banco de pruebas
app/poc.py, app/eval.py   los CLIs
app/api/main.py           API HTTP: token, límite de gasto, persistencia; envuelve lo anterior
app/db.py, migrations/    SQLModel + Alembic (el API migra al arrancar)
```

`recognition` y `verification` son **funciones puras sobre los modelos de `schemas.py`**: sin estado global, sin framework. La Fase 2 las envuelve en endpoints sin reescribirlas.

```
frontend/src/db.ts            esquema Dexie; cambios = nueva .version(n) con migración
frontend/src/strokes/         formato de trazo, contorno, geometría, formas (puro, con tests)
frontend/src/canvas/          NotebookCanvas (imperativo), Toolbar, view (zoom/geometría de página)
frontend/src/library/         biblioteca y acciones de datos (borrados en cascada)
frontend/src/export/          PDF vectorial y JSON
frontend/src/review/          cliente del API, imagen de la selección, panel y ajustes
```

## Decisiones tomadas

| ADR | Qué fija |
|---|---|
| [0001](docs/decisions/0001-fase0-scope.md) | Alcance de la Fase 0 |
| [0002](docs/decisions/0002-sympy-dialect.md) | Dialecto del campo `sympy`; parseo seguro; `j` contra `I` |
| [0003](docs/decisions/0003-step-relations.md) | `relation` y `derives_from`; propagación de error |
| [0004](docs/decisions/0004-eval-metrics.md) | Cómo se mide el eval |
| [0005](docs/decisions/0005-structured-output.md) | Salida estructurada en vez de tool use |
| [0006](docs/decisions/0006-fase1-frontend.md) | Lienzo imperativo, dos capas, coordenadas en puntos PDF, despliegue |
| [0007](docs/decisions/0007-fase2-api.md) | API HTTP: token, límite de gasto, verificador precalentado, banco de pruebas con tinta real |

## Reglas que no son obvias en el código

1. **Un falso ❌ es el peor fallo posible.** Cuando el verificador no puede decidir, el resultado es `unverifiable`, nunca `error`. No parsear es un fallo nuestro, no del alumno. Los tests `assert_no_false_errors` existen para esto.
2. **Nunca `sympify()`** sobre texto del modelo. Solo `safe_parse`. El guardia de AST no es adorno: sin él, `().__class__` devuelve el tipo real y abre la vía de escape por `__subclasses__()`. Hay un test que lo fija.
3. **`integrate` no está en la lista blanca** a propósito: evalúa, y eso convertiría un paso «integro ambos lados» en su propia respuesta, tapando el error del paso siguiente.
4. **El timeout usa un subproceso**, no `signal.alarm`, que no existe en Windows.
5. **Los datos del enunciado se buscan en orden de lectura**, no por la cadena `derives_from`: se escriben arriba de la hoja y son premisa de todo el desarrollo, no de una rama.
6. **Antes de tocar el cliente de Anthropic, carga el skill `claude-api`.** Lo pide §4 del spec y la API cambió más de lo que la memoria sugiere.
7. **Antes de cambiar modelo o prompt, corre `app.eval`.** Si baja el porcentaje, no se cambia (§12.4).
8. **El lienzo no pasa por el estado de React.** Tinta, zoom y herramientas viven en `NotebookCanvas`; React solo pinta la barra y la biblioteca. Meter eventos de puntero en `useState` añade latencia al trazo.
9. **Los trazos guardan puntos, no contornos**, en puntos PDF (página 612 × 792). Cambiar cómo se dibuja no toca datos; cambiar el formato exige subir `format_version`, migración de Dexie y actualizar [docs/stroke-format.md](docs/stroke-format.md).
10. **La dirección publicada no se cambia.** IndexedDB va ligado al origen: otra dirección deja vacía la app instalada en el iPad.
11. **`wrangler` reescribe `package.json` y `vite.config.ts` si no encuentra `wrangler.jsonc`.** No borres ese archivo; si pasa, deshaz los cambios (versiones sin fijar).
12. **El doble toque del Apple Pencil no llega a la web.** No lo prometas ni lo busques; ver ADR 0006.
13. **`uv run pytest` falla en esta máquina** («trampoline failed»); usa `uv run python -m pytest`, y lo mismo con `ruff`, `uvicorn` y `alembic`.
14. **`app/api/main.py` no lleva `from __future__ import annotations`**: FastAPI resuelve las anotaciones en tiempo de ejecución y las dependencias son locales a `create_app()`.
15. **Cambios de tablas = migración nueva de Alembic** en `backend/migrations/versions/`; nunca `create_all`. En el frontend, tabla nueva = `db.version(n)` nueva en `db.ts`.
16. **Un script que arranque el API en Windows necesita `if __name__ == "__main__":`**: el verificador usa subprocesos y sin la guarda el hijo vuelve a ejecutar el script.

## Idioma

Código, nombres y commits en **inglés**. Interfaz, mensajes al usuario, documentación y ADRs en **español** (§4).
