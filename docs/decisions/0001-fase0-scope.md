# ADR 0001 — Alcance de la Fase 0

**Fecha:** 2026-09-17
**Estado:** aceptado

## Contexto

La Fase 0 del SPEC (§10) existe para responder una sola pregunta antes de invertir en canvas y PWA: **¿el modelo lee bien mi letra y el verificador detecta mis errores reales?** Si la respuesta es no, todo lo demás se construye sobre arena.

## Decisión

Fase 0 entrega una **librería de Python más dos CLIs**. Nada de HTTP, base de datos ni frontend.

**Dentro:**
- Esquema de pasos y de verificación (`app/schemas.py`).
- Verificador simbólico como registro de estrategias (§6.3).
- Configuración por materia: `ed` y `circuitos1`, esta última **solo DC**.
- Proveedor de IA detrás de `LLMProvider` (§12.3), con reconocimiento por visión.
- `python -m app.poc` y `python -m app.eval`.
- Banco de pruebas permanente en `backend/eval/cases/`.

**Fuera, y por qué:**
- **FastAPI, SQLite y Alembic.** No hay nada que persistir salvo resultados de eval, que van a archivos JSON. Las migraciones que pide §12.2 entran en la Fase 2, cuando exista la primera tabla. Crear un esquema vacío ahora solo genera migraciones que habrá que rehacer.
- **Fasores y aritmética compleja.** Meten el problema de notación compleja (`j` de Hayt contra `I` de SymPy) justo en la fase donde quiero medir el reconocimiento aislado. Entran cuando Circuitos I llegue a AC.
- **Todo lo de §3 "Fuera"**, sin cambios.

## Consecuencias

- Los módulos se escriben como **funciones puras sobre los modelos de `schemas.py`**, sin estado global ni dependencias de framework, para que la Fase 2 solo los envuelva en endpoints. Concretamente: `recognition.service.recognize()` y `verification.runner.verify()` reciben y devuelven modelos Pydantic, y no saben que existe HTTP.
- El banco de pruebas (imágenes incluidas) **se versiona en git**. Es el activo que hace comparables las corridas entre semestres (§12.4), y con el orden de magnitud esperado —decenas a pocos cientos de imágenes en toda la carrera— git simple alcanza. Si algún día deja de alcanzar, la salida es git-lfs, no sacar las imágenes del repo.
- La caché de reconocimiento (`backend/.cache/`) **no** se versiona: es regenerable y nunca es fuente de verdad.
