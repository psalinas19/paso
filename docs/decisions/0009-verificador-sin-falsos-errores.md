# ADR 0009 — Cuándo un «no coincide» es un error

**Fecha:** 2026-11-13
**Estado:** aceptado

## Contexto

En la primera sesión real en el iPad, la app marcó con ✕ un desarrollo **correcto** de una ecuación diferencial de segundo orden. Es el fallo que este proyecto declara como el peor posible (regla 1 de `CLAUDE.md`).

Para reproducirlo se escribieron 27 desarrollos correctos típicos de la carrera, tal como el modelo los transcribe, incluidas etiquetas de relación descuidadas. Resultado con el verificador de entonces: **12 errores falsos y una caída interna**. Los patrones:

| Lo que el alumno escribe | Por qué salía ✕ |
|---|---|
| Ecuación característica `r² + 3r + 2 = 0`, luego `r₁ = −1`, `r₂ = −2` | Se comparaban como ecuaciones distintas: `r₁` no aparece en la anterior. |
| La solución general como resultado | Se sustituía en la ecuación característica, no en la ecuación diferencial. |
| `C₁ = 1` tras aplicar una condición inicial | «No existe valor de la constante que haga coincidir los pasos». |
| La solución particular de un problema de valor inicial | Se comprobaba contra un renglón intermedio (`y′ = −C₁ sen x + C₂ cos x`). |
| `V = 10` usando `i = 2` y `R = 5` de renglones anteriores | Solo se usaban valores marcados como dato del enunciado. |
| `ln|y| = x² + C` tras integrar | SymPy da `log(y)` y las barras contaban como diferencia. |
| Integración por partes a medias | «Falta la constante», aunque el renglón aún traía una integral. |
| Sustituir la solución propuesta en la ecuación (coeficientes indeterminados) | Se comparaba con un solo paso de los dos de los que sale. |

La causa común: **comparar un paso con el anterior solo prueba un error cuando el paso no usó nada más.** Y casi siempre usa algo más.

## Decisiones

**Una diferencia solo es error si los dos pasos hablan de lo mismo.** Antes de convertir un «no coincide» en ✕ se da una segunda mirada (`KindStrategy.settle`):
1. Se sustituyen los valores que la hoja ya dio o calculó en renglones anteriores. Si con eso coinciden, el paso es correcto.
2. Si el paso **introduce un nombre** que el anterior no tiene, **sale de varios pasos** a la vez, o **deja de mencionar algo** cuyo valor la hoja no da, el resultado es «no verificable», no error.
3. Dividir ambos lados entre un parámetro es equivalencia.

**Sustituir un candidato en una ecuación tiene tres salidas falsas que ya no cuentan como error** (`satisfies`): que la «ecuación» sea una expresión suelta; que no mencione lo que el candidato despeja; o que tras sustituir queden símbolos que el candidato no trae (su valor está en otra parte de la hoja).

**Un resultado se comprueba contra los datos del problema, en orden de lectura** (regla 5), y solo después contra los pasos de los que deriva.

**Comprobaciones propias, que sí pueden afirmar un error porque la pregunta está bien planteada:**
- **Raíces:** `r₁ = −1` tras una ecuación en una sola incógnita. Se resuelve y se compara, con tolerancia para redondeos a mano.
- **Consecuencia de un sistema:** si los pasos de los que sale determinan todas las incógnitas, el paso se cumple con esa solución o no se sigue de ellos (nodos y mallas).
- **Coeficientes:** `A = −1` tras una identidad en `s`, `x` o `t` (fracciones parciales, coeficientes indeterminados).
- **Definición:** `f(x) = sen(x²)` seguido de un renglón sobre `f′`. Así se detecta la regla de la cadena olvidada.
- **Condición inicial:** `C₁ = 1` con `y(0) = 1` escrito en la hoja.
- **Operación enunciada:** un renglón que da el valor de una integral, una derivada o una transformada se comprueba por sí mismo, sea cual sea su relación.
- **Laplace:** un paso que cruza entre `s` y `t` se comprueba transformando el lado del tiempo. Solo cuenta como error si los dos renglones son a la vista un par (`F` y `f`, `Y` y `y`); si no, puede ser otra cosa, como la respuesta a una entrada que no está escrita.
- **Solución propuesta sustituida** en su ecuación diferencial: solo confirma.

**Laplace entra por configuración de la materia**, no por el prompt de reconocimiento: `extra_functions` y `notation_notes` de `general.yaml` y `ed.yaml` añaden `LaplaceTransform(f, t, s)` e `InverseLaplaceTransform(F, s, t)`, sin evaluar. Antes no había forma de escribir una transformada, así que el enunciado quedaba sin fórmula, con lectura «dudosa», y la solución se negaba.

**Una caída dentro de una comprobación es «no verificable»**, nunca un error ni una revisión fallida.

**Las pruebas quedan en el repositorio** (`tests/test_career_developments.py`): los 27 desarrollos correctos no pueden producir ningún error; 13 desarrollos con un error real deben seguir detectándolo sin culpar a ningún otro paso; y al menos el 60 % de los pasos correctos debe quedar comprobado, para que «no puedo decidir» no se vuelva la respuesta a todo.

## Limitaciones conocidas

- **Los casos los escribí yo, no salen de tu letra.** Imitan cómo creo que transcribe el modelo. La revisión que falló en el iPad no la he visto: `python -m app.case show <id>` la imprime para comprobar que era uno de estos patrones.
- **Se detectan menos errores que antes en pasos con varios padres o nombres nuevos.** Es el precio de no acusar en falso; esos pasos quedan en ámbar y es el modelo quien opina.
- Condiciones iniciales sobre la derivada (`y′(0) = 0`) no tienen forma en el dialecto todavía: `C₂` queda sin comprobar.
- La nota de Laplace cambia lo que se le pide al modelo al leer en esas dos materias, y **no está medida**: el banco de pruebas sigue vacío.
- Transformada Z, Fourier, fasores, matrices y espacio de estados no tienen comprobación propia aún.
