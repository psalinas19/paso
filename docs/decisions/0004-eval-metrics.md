# ADR 0004 — Métricas del eval

**Fecha:** 2026-09-17
**Estado:** aceptado — hace medible §10
**Resuelve:** riesgo R5

## Contexto

§10 pide «al menos 8 de 10 transcritas correctamente» y que «el verificador detecte los errores sembrados». Ninguna de las dos es medible como está:

- **«Transcrita correctamente» no está definido.** Comparar LaTeX como cadena es imposible: `\frac{1}{2}` contra `0.5`, `\cdot` contra `*`, espaciado, `\left(` opcional. Cualquier umbral sobre comparación textual mide formato, no lectura.
- **«Detecta los errores sembrados» sin medir falsos positivos se cumple marcando todo mal.** Es la métrica que un verificador roto maximiza.
- **10 fotos es poca muestra.** 8/10 contra 7/10 es una sola foto. Y §12.4 quiere decidir cambios de modelo comparando porcentajes: con n=10 por foto, eso es ruido.

## Decisión

### La unidad de medida es el paso, no la foto

Diez fotos dan del orden de 60–100 pasos. Eso sí tiene señal suficiente para comparar dos prompts. El criterio por foto de §10 se conserva, pero como criterio de aceptación secundario, no como la métrica de trabajo.

### Alineación antes de medir

Los pasos predichos se alinean contra los de `truth.json` con alineación de secuencias (tipo Needleman–Wunsch) permitiendo inserciones y omisiones. El predicado de coincidencia es **equivalencia semántica**, no igualdad textual:

- Ambos con `sympy`: equivalentes si `simplify(a - b) == 0`, o para `Eq`, si coinciden como conjunto solución. Es la misma maquinaria del verificador, reutilizada.
- Ambos con `sympy: null`: se comparan por LaTeX normalizado (espacios colapsados, `\left`/`\right` y `\,` fuera, `\cdot`→`*`).
- Uno con `sympy` y el otro sin: no coinciden. Leer una ecuación como texto es un fallo de lectura.

De la alineación salen inserciones (pasos inventados), omisiones (pasos no vistos) y sustituciones (leídos mal).

### Las cinco métricas

| Métrica | Definición | Objetivo |
|---|---|---|
| **Exactitud de transcripción** | pasos alineados y equivalentes / pasos en truth | ≥ 80% |
| **Fotos limpias** | fotos sin omisiones, sin inserciones y sin ningún paso mal leído que cambie el resultado | ≥ 8 de 10 |
| **Errores sembrados detectados** | sembrados marcados `error` / sembrados verificables | 100% |
| **Falsos ❌** | pasos `error` cuya verdad es correcta / pasos correctos verificables | **0** |
| **Tasa de ⚠️** | pasos `unverifiable` / pasos **excluyendo los `given`** | ≤ 30% |

Las últimas dos son las que importan de verdad. Un falso ❌ le dice al alumno que un paso correcto está mal: es el peor fallo que esta app puede cometer, peor que no verificar nada, y por eso su objetivo es cero y no «bajo». La tasa de ⚠️ es el termómetro del dialecto: si sube, el problema está en el prompt o en ADR 0002, no en las estrategias.

«Errores sembrados **verificables**» excluye los que caen en pasos `text`, `diagram` o sin `sympy`: el verificador simbólico no puede detectarlos por construcción, y contarlos en su contra mide otra cosa. El eval los reporta aparte, como cota de lo que solo el modelo puede atrapar.

Se mide además, por caso y para el total: **exactitud de `relation`** (aparte de la del LaTeX, porque son dos fallos con dos arreglos distintos), **costo en USD** y **latencia**.

### Reproducibilidad

Cada corrida escribe `eval/results/<timestamp>.json` con las métricas, el `prompt_version` (hash del archivo), el modelo y el detalle por caso, más un resumen en Markdown. Los resultados **se versionan**: son el registro histórico que hace cumplible §12.4 («si baja el porcentaje, no se cambia»).

`--no-llm` recorre desde la caché de reconocimiento, de modo que iterar sobre el verificador no cuesta dinero ni cambia la entrada. Es la diferencia entre poder ajustar el verificador veinte veces en una tarde o no poder.

## Consecuencias

- `truth.json` hay que escribirlo a mano por cada foto, en el dialecto de ADR 0002. Es el trabajo aburrido de la Fase 0 y no hay atajo: sin verdad anotada no hay medición.
- Con n≈80 pasos, una diferencia de menos de ~5 puntos entre dos corridas no es concluyente. El banco crece cada semestre (§10), y hasta entonces el eval sirve para detectar regresiones grandes, no para afinar.
