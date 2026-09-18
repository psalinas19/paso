# ADR 0002 — Dialecto SymPy del campo `sympy`

**Fecha:** 2026-09-17
**Estado:** aceptado
**Resuelve:** riesgo R3

## Contexto

El campo `sympy` de cada paso (§6.2) es el eje de todo el verificador, y el SPEC no dice en qué dialecto se escribe. Sin una convención acordada, el modelo alterna entre `y'`, `dy/dx`, `Derivative(y(x), x)` y `diff(y, x)` según el día, y entre `C`, `C1` y `c_1` para la constante de integración. Cada variante rompe una estrategia distinta del verificador.

Hay además dos problemas concretos:

1. **Colisión de la unidad imaginaria.** Hayt escribe `j`; SymPy usa `I`; y en circuitos `I` es corriente. Los tres significados chocan en el mismo carácter.
2. **`sympify()` hace `eval`.** El texto del campo `sympy` lo produce un modelo de lenguaje, y en §6.4 también lo produce para sus propias soluciones. Pasarlo a `sympify()` es ejecución de código arbitrario.

## Decisión

### Forma de las expresiones

| Concepto | Se escribe | No se escribe |
|---|---|---|
| Función incógnita | `y(x)` — siempre aplicada | `y` |
| Derivada | `Derivative(y(x), x)`, `Derivative(y(x), x, 2)` | `y'`, `dy/dx`, `diff(...)` |
| Integral | `Integral(f(x), x)` — sin evaluar | `integrate(...)` |
| Constante de integración | `C1`, `C2`, … | `C`, `c_1`, `k` |
| Ecuación | `Eq(lhs, rhs)` | `lhs = rhs` |
| Sistema | lista de `Eq`: `[Eq(...), Eq(...)]` | ecuaciones sueltas en pasos distintos |
| Subíndices | guion bajo: `V_1`, `i_L`, `R_eq` | `V1`, `V[1]` |
| Fracciones exactas | `1/2` (parsea a `Rational`) | `0.5` si en el papel dice ½ |

`Derivative` e `Integral` se usan **sin evaluar** a propósito: representan lo que está escrito en el papel, y es el verificador quien decide cuándo evaluarlas. Si se escribieran con `diff` o `integrate`, el paso llegaría ya resuelto y no habría nada que comprobar.

**Sin unidades dentro de la expresión.** Se escribe `10`, no `10*ohm`. Las unidades van en `notes`. Mezclarlas rompe `simplify` y no aporta a la equivalencia simbólica; la revisión de unidades que pide §9.6 la hace el tutor sobre el texto, no el verificador.

### La unidad imaginaria, por configuración

El parser trabaja con un `local_dict` restringido que se construye **desde la configuración de la materia**, así que el significado de `I` y `j` se decide por materia y no globalmente:

- **`complex_domain: false`** (ED, Circuitos I en DC): no existe unidad imaginaria. `I`, `i`, `j` son símbolos ordinarios, así que `I_1` e `i_L` son corrientes y nada los reinterpreta.
- **`complex_domain: true`** (Circuitos en AC, y más adelante Laplace, Fourier y Z): `j` se normaliza a la unidad imaginaria de SymPy al parsear, y **`I` a secas queda prohibido como nombre de símbolo** — una corriente debe escribirse `I_1`, `I_x`, `i_L`. Si el modelo emite `I` suelta en una materia compleja, el paso se rechaza como no parseable, no se adivina.

El LaTeX es independiente de esto: en Circuitos se conserva `j` al renderizar, porque es la notación de Hayt y es la que yo escribo.

### Parseo seguro

Nunca `sympify()`. Siempre `parse_expr` con:

- `local_dict` explícito: los símbolos declarados por la materia más una **lista blanca de invocables** (`Eq`, `Derivative`, `Integral`, `Matrix`, `Rational`, `sqrt`, `exp`, `log`, `sin`, `cos`, `tan`, `sinh`, `cosh`, `Abs`, `pi`, `E`, `oo`).
- `global_dict` vacío, para que no se filtre el espacio de nombres de SymPy.
- Rechazo previo por análisis del AST: nada de `import`, atributos (`.` fuera de literales numéricos), `lambda`, comprehensions, ni nombres con `__`.

Un paso que no parsea es `unverifiable` con el motivo, **nunca** `error`. No parsear es un fallo nuestro, no un error del alumno, y marcarlo como error sería exactamente el falso ❌ que R1 quiere evitar.

## Consecuencias

- El prompt de reconocimiento lleva esta tabla, y las reglas específicas de la materia se inyectan desde su archivo de configuración.
- `truth.json` del banco de pruebas se escribe en este mismo dialecto, así que el eval compara manzanas con manzanas.
- Agregar Laplace o espacio de estados significa ampliar la lista blanca de invocables y añadir una estrategia, no cambiar el dialecto.
