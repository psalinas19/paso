# ADR 0010 — Chat por ejercicio y cola sin conexión

**Fecha:** 2026-11-13
**Estado:** aceptado; construido y probado **solo con el modelo simulado**

## Contexto

Cierran lo que la Fase 3 del SPEC pedía y faltaba: el chat de cada ejercicio (§6.5) y la cola de revisiones sin conexión (§6.9). Los niveles 2 y 3 ya estaban (ADR 0008).

## Decisiones

### Chat

**Un hilo por revisión, guardado en los dos lados.** En el backend (tabla `ChatMessage`, migración 0004) y en el iPad dentro de la propia revisión, para releerlo sin conexión.

**La respuesta llega mientras se escribe**, por eventos del servidor (SSE) sobre el mismo `POST /api/checks/{id}/chat`: `delta` con cada trozo, `done` con el costo, o `error`. Los datos van en JSON para que un salto de línea del texto no se confunda con el fin del evento.

**El tutor recibe el estado del ejercicio aparte de sus reglas.** Las reglas (`chat.system.md`) no cambian entre preguntas y van en la parte del prompt que se guarda en caché. El estado sí cambia: pasos con su veredicto, qué paso falla según el verificador, y la pista, explicación o solución que ya vio. La imagen viaja con la primera pregunta.

**Nada de lo que dice el chat pasa por el verificador.** Es conversación, no un resultado: el panel lo rotula como del modelo («puede equivocarse») y el prompt lo ata a los veredictos que recibe. Es la única ayuda de la app sin comprobación simbólica; se aceptó porque comprobar texto libre no es posible, y se dice a la vista.

**Si la respuesta falla no se guarda nada**, ni la pregunta: vuelve al cuadro de texto y se puede enviar otra vez sin duplicarla.

**Solo se reenvían los últimos 30 turnos.** Los anteriores siguen guardados y visibles; dejan de releerse (y pagarse) en cada pregunta.

**`ANTHROPIC_MODEL_CHAT`** permite un modelo más barato para el chat (SPEC §4). Vacío usa el mismo.

**Markdown propio y mínimo** (párrafos, listas, títulos, negritas, cursivas, código, fórmulas con KaTeX), convertido a datos y pintado como nodos de React, nunca como HTML: lo que escriba el modelo no puede inyectar marcado. Se evitó añadir una librería para esto.

**Preguntas sugeridas** según el estado de la revisión, para no empezar ante un cuadro vacío (SPEC §6.4).

### Cola sin conexión

**Revisar sin conexión guarda la selección y avisa.** Imagen, trazos y materia van a una tabla nueva de IndexedDB (`queue`, versión 3 de Dexie). También se guarda si el backend no responde: en ambos casos no se gastó nada y la petición vale la pena conservarla.

**Nada se envía solo.** Al volver la conexión la app avisa cuántas hay; enviarlas es un toque tuyo, porque cada una cuesta (SPEC §6.9).

**Una revisión sale de la cola solo cuando su resultado ya está guardado**, en una misma transacción. Si el envío falla, se queda donde estaba.

**La imagen se guarda como bytes, no como `Blob`**: no todos los motores de almacenamiento conservan un `Blob`.

## Limitaciones conocidas

- **Sin probar con el modelo real ni en el iPad.** Que el túnel de Cloudflare entregue la respuesta por trozos y no toda junta al final no está comprobado.
- **No se puede adjuntar una nueva selección al chat** (SPEC §6.5). Queda pendiente.
- El chat y los niveles de ayuda necesitan conexión; solo *Revisar* se encola.
- Borrar un cuaderno no borra sus revisiones ni lo que tenga en cola.
- El chat de una revisión abierta desde «Revisiones guardadas» necesita el backend con su misma base de datos.
