# Banco de pruebas

Este es el activo que hace comparables las corridas entre semestres (SPEC 10, §12.4). Crece cada semestre con ejercicios de las materias nuevas. **Se versiona en git, imágenes incluidas.**

## Desde una revisión hecha en la libreta (lo normal)

Lo que el modelo lee en producción es tinta de la app, así que los casos salen de revisiones reales (ADR 0007). El backend guarda cada revisión con su imagen.

```powershell
py -3.12 -m uv run python -m app.case list
py -3.12 -m uv run python -m app.case new a1b2c3d4 --id ed-01 --topic variables-separables
```

`new` crea `cases/ed-01/` con la imagen, `meta.yaml` y **`truth.draft.json`**: la lectura del modelo (o tu versión, si corregiste pasos en la libreta) como **propuesta**. Mientras exista el borrador, el caso **no se mide**: `app.eval` lo salta y te avisa.

Tu parte, que nadie puede hacer por ti:

1. Abre la imagen y `truth.draft.json` lado a lado.
2. Corrige cada paso hasta que diga lo que de verdad está escrito: `latex`, `sympy`, `relation`, `derives_from`.
3. En cada paso con error hay un `seeded_error` con `"type": "REVISAR"`. Si el error es tuyo y está en la hoja, pon el tipo de la materia, decide `verifiable` (ver abajo) y borra la palabra REVISAR de la nota. Si el paso estaba bien y fue un error de lectura, quita `seeded_error` y pon `"expected_status": "correct"`.
4. Confirma:

```powershell
py -3.12 -m uv run python -m app.case confirm ed-01
```

`confirm` se niega mientras falte algo, y te enseña qué dice hoy el verificador de cada paso. Si anotaste un paso como correcto y el verificador lo marca con error, te avisa pero no te frena: si tu anotación está bien, eso es un falso error y el banco existe para contarlo.

## Cómo agregar un caso a mano

Crea una carpeta por ejercicio dentro de `cases/`:

```
cases/ed-01/
  image.jpg     la foto (también vale .png o .heic)
  meta.yaml     de qué es
  truth.json    cómo debió leerse, y qué debe decir el verificador
```

El id de la carpeta y el campo `id` de `meta.yaml` deben coincidir. Sugerencia de nombres: `ed-01`, `circuitos1-03`.

### `meta.yaml`

```yaml
id: ed-01
subject: ed              # tiene que existir app/subjects/<subject>.yaml
topic: variables-separables
source: "Cuaderno ED, tarea 3"
notes: ""
```

### `truth.json`

La transcripción **correcta**, en el dialecto de `docs/decisions/0002-sympy-dialect.md`, más lo que el verificador debería decir de cada paso.

```json
{
  "schema_version": 1,
  "steps": [
    {
      "id": "t1",
      "latex": "\\frac{dy}{dx} = 2xy",
      "sympy": "Eq(Derivative(y(x), x), 2*x*y(x))",
      "kind": "ode",
      "relation": "given",
      "derives_from": []
    },
    {
      "id": "t2",
      "latex": "\\ln|y| = x^2 + C",
      "sympy": "Eq(log(y(x)), x**2 + C1)",
      "kind": "equation",
      "relation": "specialization",
      "derives_from": ["t1"],
      "expected_status": "correct"
    },
    {
      "id": "t3",
      "latex": "y = C_1 e^{-x^2}",
      "sympy": "Eq(y(x), C1*exp(-x**2))",
      "kind": "ode",
      "relation": "result",
      "derives_from": ["t1"],
      "expected_status": "error",
      "seeded_error": {
        "type": "sign",
        "verifiable": true,
        "note": "El exponente debe ser +x^2."
      }
    }
  ]
}
```

Campos por paso:

| Campo | Qué es |
|---|---|
| `id` | `t1`, `t2`, … |
| `latex` | el paso como está escrito |
| `sympy` | el paso en el dialecto, o `null` si es texto, diagrama o ilegible |
| `kind` | `expression`, `equation`, `system`, `ode`, `numeric_iteration`, `text`, `diagram` |
| `relation` | `given`, `equivalent`, `substitution`, `specialization`, `assertion`, `result` |
| `derives_from` | ids de los pasos de los que sale |
| `expected_status` | `correct` (por defecto), `error` o `unverifiable` |
| `seeded_error` | solo si sembraste un error ahí |

### El campo `verifiable` de `seeded_error`

Es el que más cuidado merece. Marca **`false`** cuando el error no lo puede detectar un verificador simbólico ni en principio:

- Una LCK o LVK mal planteada. Decidir si las corrientes de un nodo suman bien requiere la topología del circuito, y el reconocimiento estructural de diagramas está fuera de alcance (SPEC §3).
- Un divisor de voltaje con la resistencia equivocada en el numerador, cuando el desarrollo es internamente consistente con esa fórmula mal escrita.
- Elegir el método equivocado, si luego se aplica bien.
- Cualquier error que solo se ve comparando con el enunciado o el dibujo.

Marca **`true`** cuando el error se contradice con algo escrito en la misma hoja: un signo perdido al despejar, la regla de la cadena mal aplicada, una constante de integración faltante, una iteración mal calculada, un sistema mal resuelto, una solución que no satisface su ecuación.

Los `verifiable: false` se reportan aparte y **no cuentan en contra del verificador**: son la cota de lo que solo el modelo puede señalar (ADR 0004).

## Correr el eval

```powershell
py -3.12 -m uv run python -m app.eval              # todo el banco
py -3.12 -m uv run python -m app.eval --no-llm     # desde caché, sin costo
py -3.12 -m uv run python -m app.eval --case ed-01 # un solo caso
```

Los resultados van a `results/<timestamp>.json` y `.md`, y **se commitean**: son el historial que hace cumplible «si baja el porcentaje, no se cambia el modelo» (SPEC §12.4).

## Consejo práctico

Anotar `truth.json` a mano es el trabajo aburrido de esta fase y no hay atajo: sin verdad anotada no hay nada que medir. Un camino cómodo es correr primero `python -m app.poc foto.jpg --materia ED --json`, tomar su salida como borrador y **corregirla**. Ojo: revísala paso por paso, porque si copias sin revisar estarías midiendo al modelo contra sí mismo.
