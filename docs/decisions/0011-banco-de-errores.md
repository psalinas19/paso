# ADR 0011 — Banco de errores

**Fecha:** 2026-11-15
**Estado:** aceptado; construido y probado **solo con el modelo simulado**

## Contexto

Primera entrega de la Fase 4 ([plan](../plan-fase4.md)). El SPEC §6.6 pide guardar cada error confirmado con materia, tema, tipo, fecha y si ya se resolvió; que el modelo proponga tema y tipo desde una taxonomía por materia que el alumno puede cambiar; y una vista con conteos y lo más frecuente del último mes. El modo repaso (4b) se alimenta de esto.

## Decisiones

**Un error entra al banco con un toque, nunca solo.** Un renglón mal leído también se ve como error ante el verificador, y solo el alumno sabe cuál de los dos fue. Un banco que se llenara solo mandaría al repaso a practicar errores que nunca ocurrieron. Es la lectura literal de «cada error *confirmado*».

**Un paso comprobado como correcto no se puede guardar.** El backend lo rechaza (422) y el panel no lo ofrece. Sería un falso ❌ con memoria. Se ofrecen los pasos con ✕ y, entre los que no se pudieron comprobar, solo aquel al que apuntó la ayuda. Cada entrada dice si el error está **comprobado** o si solo lo sostiene el alumno (`proved`), y la pantalla lo rotula.

**Corregir una lectura arrastra al banco.** Si tras corregir un paso este queda correcto, su entrada se borra: el «error» era de lectura. Si sigue mal, la entrada toma el texto y el veredicto nuevos. Cada respuesta sobre una revisión (`CheckResponse.errors`) lista sus entradas, y la libreta alinea su copia con eso.

**El banco vive en el backend** (tabla `ErrorEntry`, migración 0005) y la libreta guarda una copia (`db.errors`, versión 4 de Dexie) para leerlo sin conexión. Razones: la app web y la nativa son almacenes separados y así comparten banco; sobrevive a que Safari borre los datos del sitio; el repaso y la búsqueda se calculan en el backend. Todo cambio va primero al backend y luego a la copia: sin conexión el cambio falla y lo dice, en vez de dejar dos versiones.

**Cada entrada es una foto, no un puntero.** Copia el LaTeX del paso y lo que dijo el verificador, para leerse sin la revisión y sin conexión.

**Se agrupa por la materia como se llama en la biblioteca.** El backend solo conoce la configuración (`general`, `ed`…), y dos materias creadas con la plantilla general se mezclarían. La libreta manda el nombre; la configuración sigue decidiendo la taxonomía.

**Guardar es gratis; clasificar lo propone el modelo solo donde ya se pagó.** La pista ya clasificaba el tipo; ahora propone también el **tema** (campo `topic` en lo que llena el modelo; cambia la versión del prompt `hint`). Al guardar, la entrada toma lo que propuso la pista si habla de ese mismo paso; si no hay pista, queda sin clasificar y el alumno elige de la lista. Un tema o un tipo que no esté en la materia se descarta, como ya se hacía con el tipo. El tema admite además texto libre del alumno: la materia `general` no define temas.

**El tipo se guarda por id y se muestra con la etiqueta de hoy.** Editar el YAML de la materia renombra también las entradas viejas; un tipo retirado se muestra con su id.

**«Lo más frecuente» cuenta los errores del último mes, superados o no,** porque mide qué tan seguido ocurre algo. Los que nadie clasificó no entran: no dicen qué practicar.

**Estas rutas reciben JSON**, a diferencia del resto (formularios): en un cambio parcial hay que distinguir «no lo mando» de «lo borro». Por eso CORS admite ahora `PATCH`, `DELETE` y la cabecera `Content-Type`.

## Rutas

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/errors` | Todo el banco, lo más nuevo primero |
| POST | `/api/errors` | Guarda un paso de una revisión; repetirlo actualiza la entrada |
| PATCH | `/api/errors/{id}` | Cambia tipo, tema o «superado» |
| DELETE | `/api/errors/{id}` | «No fue un error mío» |
| GET | `/api/taxonomy` | Temas y tipos de cada materia, para las listas |

## Lo que queda fuera

- Marcar «superado» automáticamente: llega con el repaso (4b). Hoy es un botón.
- Guardar desde la tarjeta de una marca en la hoja: solo desde el panel.
- Abrir el cuaderno en la página del error: la pantalla muestra la revisión, sin saltar a la hoja.

## Sin medir

La propuesta de tema es un cambio al prompt de la pista que no se ha ejecutado contra el modelo real, igual que el resto de la pista. No afecta a la lectura ni al verificador.
