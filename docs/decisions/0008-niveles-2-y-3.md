# ADR 0008 — Explicación y solución (niveles 2 y 3)

**Fecha:** 2026-11-13
**Estado:** aceptado; construido y probado **solo con el modelo simulado**

## Contexto

En la primera prueba real en el iPad la revisión conectó y leyó bien, pero no aportaba: al escribir solo `3x + 2 = 9` la app respondía «no encontré errores» y nada más. No decía cómo seguir, ni el valor de `x`, ni por qué un paso estaba bien. Eran dos problemas distintos:

1. **Un mensaje falso.** Con solo el enunciado en la hoja no se comprueba nada; decir «sin errores» y poner una palomita verde era dar una tranquilidad que no existía.
2. **Faltaba la ayuda de verdad.** El SPEC (§2.5) prevé tres niveles de ayuda y solo existía el primero (la pista), que además no dice nada cuando no hay error.

A petición directa de Pakal se adelantan los niveles 2 y 3, que el plan por fases dejaba para la Fase 3, **antes** de la entrega 2c (marcas sobre la hoja). El chat sigue en la Fase 3.

## Decisiones

**El resumen dice lo que de verdad se comprobó.** Si solo hay datos del enunciado: «Solo veo el enunciado: todavía no hay un desarrollo que revisar». Si se comprobó algo: cuántos pasos y cuántos no se pudieron comprobar. Un dato del enunciado lleva una marca neutra («•», «Dato»), no una palomita: nadie lo verificó.

**Tres ayudas a un toque, ninguna automática.** *Pista*, *Explícame* y *Ver solución*. Cada una es una llamada de pago y se escribe sobre la lectura que el alumno ya confirmó; por eso no se piden solas. Pedirla dos veces no cobra dos veces, y corregir un paso las borra a las tres.

**Nivel 2, «Explícame»** (`POST /api/checks/{id}/level/2`). El modelo devuelve: de qué tipo es el problema y por qué aplica el método; un comentario por paso (por qué está bien, o qué idea hay detrás del error); cómo debió quedar el paso que falla; qué hacer a continuación si el desarrollo está a medias; y una frase para recordar.
- Qué paso falla lo sigue decidiendo el verificador (regla 17). Sin error comprobado, el modelo solo puede dudar de un paso `unverifiable`, y se presenta como opinión.
- **El paso corregido que propone el modelo pasa por el verificador antes de mostrarse.** Si sale correcto, se muestra como «comprobado con matemáticas». Si no se puede comprobar, se muestra como propuesta sin comprobar. **Si el verificador demuestra que está mal, no se muestra**: una corrección equivocada presentada como la buena es peor que ninguna.

**Nivel 3, «Ver solución»** (`POST /api/checks/{id}/solve`). El modelo resuelve en pasos estructurados, con el porqué de cada uno.
- **La solución parte de los datos del alumno, no de los del modelo.** Los pasos `given` de la hoja se anteponen tal cual (`g1`, `g2`…) y los pasos del modelo se verifican como cualquier desarrollo. «Verificada» significa lo mismo que en el resto de la app: cada paso se sigue de los anteriores, empezando por lo que está escrito en la hoja. Sin datos marcados, el primer renglón es el problema.
- **El modelo no puede declarar datos.** El verificador acepta un dato sin revisarlo, así que un paso del modelo marcado `given` se convierte en afirmación y se comprueba como tal. Sin esto, bastaría con declarar la respuesta como «dato» para que saliera verificada.
- **Un reintento.** Si el verificador encuentra un error, se le dice al modelo cuál y se le pide corregir una vez (SPEC §6.4). Si persiste, la solución se muestra con la advertencia «no verificada: revísala con cuidado», nunca con la insignia.
- La insignia exige que **todas** las fórmulas del modelo estén comprobadas y ninguna esté mal. Un paso en palabras («separando variables») no cuenta ni a favor ni en contra.

**Los prompts que escriben SymPy incluyen el de reconocimiento**, como ya hacía `restructure` (regla 20), para no duplicar el dialecto.

## Limitaciones conocidas

- **Nada medido ni probado con el modelo real.** Los prompts `explain` y `solve` son nuevos; su calidad, costo y tiempo reales se desconocen.
- **Los comentarios por paso son texto libre del modelo.** El prompt le prohíbe poner en duda un paso comprobado, pero no hay forma automática de impedirlo dentro de una frase. Cada comentario se muestra pegado a su paso, que conserva la marca del verificador, y rotulado como explicación del modelo.
- **Una solución verificada puede estar incompleta**: que cada paso se siga del anterior no garantiza que se llegó a lo que el problema pedía.
- **Qué se pide lo infiere el modelo** cuando el enunciado no lo dice (despejar, resolver la ecuación diferencial…).
- Solución y explicación reciben la imagen además de los pasos, lo que sube el costo de cada llamada.
- No hay chat todavía: no se puede preguntar sobre la explicación.
