# ADR 0014 — Graficar una ecuación escrita a mano

**Fecha:** 2026-11-15
**Estado:** aceptado; construido y probado **solo con el modelo simulado**

## Contexto

Última entrega de la Fase 4 ([plan](../plan-fase4.md)). El SPEC §6.10 pide: lazo sobre una ecuación → **Graficar** → tarjeta con la gráfica 2D (`y = f(x)`), con zoom y desplazamiento, que se pueda fijar o cerrar; calculada desde el campo `sympy`; si no se pudo interpretar, decirlo en vez de graficar algo inventado; una gráfica ya hecha se conserva con la página y se ve sin conexión.

## Decisiones

**La curva sale de la expresión, nunca de lo que el modelo diga que se ve.** El modelo solo lee la ecuación (la misma lectura de una revisión; cuesta lo mismo). Lo demás es nuestro: `app/plotting.py` interpreta el campo `sympy` con `safe_parse` y lo convierte en un **árbol de operaciones permitidas** (números, la variable, suma, producto, potencia y una lista corta de funciones).

**La libreta evalúa ese árbol ella misma** (`frontend/src/plot/evaluate.ts`). Por eso el zoom y el desplazamiento no necesitan conexión, y una gráfica guardada se abre en modo avión. El árbol es datos, no código: nada de lo leído se ejecuta, y un nombre de función fuera de la lista no dibuja nada.

**Cuando no se puede, se dice por qué y no se dibuja nada.** Casos que se rechazan: no está despejada (`x² + y² = 1`), más de una variable (`y = ax + b`), integrales sin evaluar, transformadas, números complejos, desigualdades, sistemas, y un valor suelto (`x = 4`: graficarlo como `y = 4` sería otra afirmación). El aviso incluye lo que costó leerla.

**La interpretación corre en el proceso con límite de tiempo**, el mismo del verificador: es el mismo analizador y el mismo riesgo de una expresión que no termina.

**De la selección se grafica el primer renglón que se pueda.** Lo normal es rodear una sola ecuación.

**Cortes en las asíntotas.** Entre dos muestras, un salto mayor que dos veces el alto de la vista con cambio de signo parte la curva: `1/x` o `tan x` no se unen con un trazo vertical que no existe. Donde la función no tiene valor real (`log` de negativos, raíz par de negativos) no hay curva.

**Primera vista:** `x` de −10 a 10 y `y` cubriendo el 90 % central de los valores, para que un pico no aplaste el resto. **Restablecer** vuelve a ella.

**La tarjeta** se abre arriba a la derecha y se arrastra por su encabezado para ponerla junto a la ecuación; escribir de nuevo la guarda si no está fijada, igual que la tarjeta de una marca. Un dedo desplaza, dos hacen zoom, un toque lee el valor en ese punto. Hay una tabla de valores de la vista actual. Diseño según la guía de visualización: una sola serie (sin leyenda; el título es la ecuación), línea de 2 px, cuadrícula y ejes discretos, textos en gris de texto y no en el color de la curva; el color de la curva pasó el validador de la guía sobre fondo claro.

**Se guarda en el iPad** (`db.plots`, versión 6 de Dexie) con su página y su última vista; **⋯ → Gráficas guardadas** las lista. El backend no guarda nada de una gráfica salvo el gasto.

## Ruta

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/plot` | Lee la selección y devuelve el árbol para dibujarla, o el motivo por el que no se puede |

## Lo que queda fuera

- Superficies 3D (`z = f(x, y)`): el SPEC las deja para después, si el 2D resulta útil.
- Varias curvas en la misma tarjeta, curvas implícitas y paramétricas.
- Una marca en la hoja que reabra la gráfica: hoy se reabre desde el menú. La tarjeta no queda anclada a la ecuación al hacer scroll.
- Las gráficas no salen en el PDF.

## Sin medir

Qué tan seguido el modelo real escribe una ecuación de modo que resulte graficable no se sabe: depende de la lectura, que sigue sin línea base.
