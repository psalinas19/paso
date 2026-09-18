# ADR 0003 — Relaciones entre pasos y propagación de error

**Fecha:** 2026-09-17
**Estado:** aceptado — modifica §6.2 y §6.3 del SPEC
**Resuelve:** riesgos R1, R2, R4

## Contexto

§6.3 dice «compara cada paso con el anterior». Eso solo se sostiene en cadenas de manipulación algebraica. En un desarrollo real de ingeniería se rompe todo el tiempo:

- «Sea R = 10 Ω» es un dato: no hay nada con qué compararlo.
- Aplicar `y(0) = 2` a la solución general produce un paso que **no** es equivalente al anterior. Es una especialización, y exigir equivalencia lo marcaría como error.
- En análisis nodal, plantear KCL en el nodo A y luego en el nodo B da dos pasos hermanos; ninguno se deriva del otro.
- En `numeric_iteration`, x₂ no equivale a x₁: se deriva de él por una fórmula.

Un ❌ falso destruye la confianza en la herramienta mucho más rápido que un ⚠️ de más. Por eso la relación entre pasos tiene que ser **declarada**, no supuesta.

Aparte, §6.2 y §6.3 no coinciden: el enum de `kind` es `expression | equation | system | ode | numeric_iteration | text | diagram`, pero la tabla de verificación añade una fila «derivadas/integrales» que no es un `kind`.

## Decisión

### Dos campos nuevos en `Step`

- **`derives_from: list[str]`** — ids de los pasos de los que éste sale. Vacío si el paso no se deriva de ninguno.
- **`relation`** — qué tipo de vínculo es, y por tanto qué comprobación aplica:

| `relation` | Qué significa | Cómo se verifica |
|---|---|---|
| `given` | Dato o definición del enunciado | No se comprueba. Es una premisa, no una derivación |
| `equivalent` | Manipulación algebraica del padre | Equivalencia simbólica clásica |
| `substitution` | Se sustituyen valores o expresiones de pasos previos | Se aplican esas sustituciones al padre y se compara |
| `specialization` | Se impone una condición (condición inicial, caso particular) | Se comprueba que el resultado **satisface** al padre bajo la condición. No se exige equivalencia |
| `assertion` | Afirmación nueva no derivada: plantear KCL en un nodo, elegir un método | Solo si la estrategia de la materia sabe comprobarla; si no, `unverifiable` |
| `result` | Resultado final | Se sustituye en la ecuación original, o `checkodesol` |

### `kind` deja de mezclar niveles

`kind` describe únicamente la **forma estructural** de lo escrito: `expression`, `equation`, `system`, `ode`, `numeric_iteration`, `text`, `diagram`. La fila «derivadas/integrales» de §6.3 desaparece como categoría: derivar o integrar es una *operación* dentro de un paso `expression` o `equation`, y la estrategia la detecta por la presencia de `Derivative` o `Integral` en el árbol, no por una etiqueta.

El registro de estrategias se indexa por **`(kind, relation)`**, con caída a un manejador por `kind` y finalmente a `unverifiable`.

### Propagación de error

Cuando un paso queda `error`, sus descendientes **se siguen verificando, pero contra el paso erróneo tal como fue escrito**. Si son consistentes con él, se marcan `correct` con `depends_on_error` apuntando al paso culpable.

Así hay **un solo ❌ por error real**, en el punto donde se cometió, y no una cascada roja que no dice nada. La UI muestra ✅ con la nota «consistente con el paso N, que tiene un error». Si un descendiente además está mal por su cuenta, sale su propio ❌.

`depends_on_error` es un campo del resultado, no un cuarto estado: §2.4 sigue teniendo tres.

### `given` y el estado que muestra

Un paso `given` se reporta como `correct` con `method_used = "given"` y un detalle que dice que es un dato del problema. Marcarlo `unverifiable` sería técnicamente cierto pero pondría un ⚠️ en cada dato del enunciado, que es ruido. A cambio, los pasos `given` quedan **excluidos del denominador** de la tasa de ⚠️ en el eval (ver ADR 0004), para que no inflen artificialmente el resultado.

## Consecuencias

- El prompt de reconocimiento tiene que pedir `derives_from` y `relation`, y explicar cuándo usar cada uno. Es el punto más frágil del prompt y el que más atención necesita en el eval.
- Si el modelo se equivoca al declarar la relación, el verificador aplica la comprobación equivocada. Mitigación: cuando una comprobación falla bajo `equivalent`, se reintenta como `specialization` antes de declarar error — de nuevo, el sesgo es hacia ⚠️ y nunca hacia un ❌ falso.
- El eval mide la exactitud de `relation` por separado de la del `latex`, porque son dos fallos distintos con dos arreglos distintos.
