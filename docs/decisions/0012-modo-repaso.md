# ADR 0012 — Modo repaso

**Fecha:** 2026-11-15
**Estado:** aceptado; construido y probado **solo con el modelo simulado**

## Contexto

Segunda entrega de la Fase 4 ([plan](../plan-fase4.md)). El SPEC §6.6 pide: elegir materia; que la app genere de 3 a 5 ejercicios ponderados por los errores más frecuentes; resolverlos en la hoja y revisarlos con el mismo flujo; marcar como superado un tipo de error que se resuelve bien varias veces; y un modo examen opcional que bloquea las ayudas.

## Decisiones

**Cuántos ejercicios van a cada error lo decide nuestro código, no el modelo.** Se reparten en proporción a cuántas veces se cometió cada tipo entre los errores **pendientes** de la materia (`plan_slots`, resto mayor; en un empate, el ejercicio sobrante va al error que aún no tiene ninguno). «Ponderados por mis errores más frecuentes» es aritmética, y la aritmética se puede probar. El modelo recibe la lista ya repartida, con uno o dos pasos del alumno como ejemplo de cada error.

**Sin errores pendientes no hay repaso.** El backend lo rechaza antes de gastar. Los superados no se vuelven a practicar.

**Cada ejercicio trae sus datos y su resultado en el dialecto, y el resultado pasa por el verificador.** Es la regla 24 aplicada aquí:

- Si el resultado **contradice** los datos del propio ejercicio, el ejercicio se descarta: algo está roto y no sabemos qué.
- El resultado solo se muestra al alumno si el verificador lo **comprobó**, y solo después de que entregó su intento.
- El resultado del modelo nunca entra como dato (`given`): los datos se aceptan sin revisar.

Si ningún ejercicio sobrevive, se informa y no se guarda nada (la llamada sí se cobra).

**Un ejercicio vive en una página de un cuaderno «Repaso»** de la materia, que se crea la primera vez. El repaso no ensucia los apuntes. El enunciado no es tinta: se muestra en una barra plegable sobre la hoja, ligada a la página. No sale en el PDF.

**Se revisa con el flujo de siempre.** La libreta manda el `exercise_id` con la selección cuando la página es de un ejercicio; lo demás es una revisión normal (marcas, ayudas, banco de errores).

**El primer intento decide el ejercicio.** Un intento es una revisión con al menos un paso que no sea dato: sin errores y con algún paso comprobado, *sin errores*; con algún ✕, *con error*; si nada se pudo comprobar, *sin comprobar* (no cuenta ni a favor ni en contra). Revisiones posteriores del mismo ejercicio no cambian el resultado: son el alumno corrigiendo con la respuesta a la vista. Corregir una lectura de la revisión que decidió sí lo recalcula: un renglón mal leído no es un error suyo.

**Tres intentos limpios seguidos hacen «superado».** La racha se cuenta por materia y tipo de error, hacia atrás desde el último ejercicio decidido; un intento con error la corta. Al llegar a tres, las entradas pendientes de ese tipo en el banco pasan a superadas. Un ejercicio nacido de errores sin clasificar no tiene racha.

**Modo examen.** Mientras un ejercicio no tenga un intento entregado, sus revisiones no dan pista, explicación, solución ni chat: el panel no los ofrece y el backend los rechaza (409). Es la lectura literal del SPEC («los niveles de ayuda se bloquean hasta que termine el ejercicio») y cierra el único atajo que existía: revisar solo el enunciado y pedir la solución. Las marcas del verificador no son ayuda y se muestran siempre.

**La ronda se guarda en los dos lados.** En el backend (tablas `PracticeSession` y `Exercise`, migración 0006; `Check.exercise_id`), que lleva la cuenta; y en el iPad (`db.practice`, versión 5), que sabe en qué página está cada ejercicio.

## Rutas

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/review/generate` | Una ronda para una materia: `subject_name`, `count` (3 a 5), `exam` |
| POST | `/api/check` | Acepta además `exercise_id`; la respuesta trae `exercise` y, si calificó, `progress` |

## Lo que queda fuera

- Abrir una ronda hecha en otro dispositivo: las páginas son de cada iPad.
- Elegir a mano qué errores practicar.
- Comparar el resultado final del alumno con el esperado: «sin errores» significa que cada paso se sigue del anterior, no que llegó hasta el final.

## Sin medir

El prompt `practice` es nuevo y no se ha ejecutado contra el modelo real. No se sabe qué tan bien apunta al error ni cuántos ejercicios se descartan por no pasar la comprobación.
