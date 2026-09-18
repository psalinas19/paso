# CLAUDE.md

Contexto para Claude Code. El spec manda: [docs/SPEC.md](docs/SPEC.md). Trabaja **una fase a la vez** (§10), presenta plan y espera aprobación al iniciar cada fase.

## Comandos

Desde `backend/`. En Windows, `python` a secas es el stub de Microsoft Store: usa `py -3.12`.

```powershell
py -3.12 -m uv sync                                   # instalar
py -3.12 -m uv run pytest                             # tests (sin red)
py -3.12 -m uv run ruff check . ; py -3.12 -m uv run ruff format .
py -3.12 -m uv run python -m app.poc <img> --materia ED
py -3.12 -m uv run python -m app.eval [--no-llm] [--case <id>]
```

## Estado

Fase 0: librería + dos CLIs. **No hay** FastAPI, SQLite, Alembic ni frontend todavía ([ADR 0001](docs/decisions/0001-fase0-scope.md)).

## Arquitectura

```
app/schemas.py            contratos Pydantic; el resto cuelga de aquí
app/subjects/             una materia = un YAML (SPEC 12.5)
app/llm/                  proveedor de IA detrás de LLMProvider (SPEC 12.3)
app/recognition/          imagen -> pasos
app/verification/         pasos -> estados, registro de estrategias
app/evaluation/           métricas del banco de pruebas
app/poc.py, app/eval.py   los CLIs
```

`recognition` y `verification` son **funciones puras sobre los modelos de `schemas.py`**: sin estado global, sin framework. La Fase 2 las envuelve en endpoints sin reescribirlas.

## Decisiones tomadas

| ADR | Qué fija |
|---|---|
| [0001](docs/decisions/0001-fase0-scope.md) | Alcance de la Fase 0 |
| [0002](docs/decisions/0002-sympy-dialect.md) | Dialecto del campo `sympy`; parseo seguro; `j` contra `I` |
| [0003](docs/decisions/0003-step-relations.md) | `relation` y `derives_from`; propagación de error |
| [0004](docs/decisions/0004-eval-metrics.md) | Cómo se mide el eval |
| [0005](docs/decisions/0005-structured-output.md) | Salida estructurada en vez de tool use |

## Reglas que no son obvias en el código

1. **Un falso ❌ es el peor fallo posible.** Cuando el verificador no puede decidir, el resultado es `unverifiable`, nunca `error`. No parsear es un fallo nuestro, no del alumno. Los tests `assert_no_false_errors` existen para esto.
2. **Nunca `sympify()`** sobre texto del modelo. Solo `safe_parse`. El guardia de AST no es adorno: sin él, `().__class__` devuelve el tipo real y abre la vía de escape por `__subclasses__()`. Hay un test que lo fija.
3. **`integrate` no está en la lista blanca** a propósito: evalúa, y eso convertiría un paso «integro ambos lados» en su propia respuesta, tapando el error del paso siguiente.
4. **El timeout usa un subproceso**, no `signal.alarm`, que no existe en Windows.
5. **Los datos del enunciado se buscan en orden de lectura**, no por la cadena `derives_from`: se escriben arriba de la hoja y son premisa de todo el desarrollo, no de una rama.
6. **Antes de tocar el cliente de Anthropic, carga el skill `claude-api`.** Lo pide §4 del spec y la API cambió más de lo que la memoria sugiere.
7. **Antes de cambiar modelo o prompt, corre `app.eval`.** Si baja el porcentaje, no se cambia (§12.4).

## Idioma

Código, nombres y commits en **inglés**. Interfaz, mensajes al usuario, documentación y ADRs en **español** (§4).
