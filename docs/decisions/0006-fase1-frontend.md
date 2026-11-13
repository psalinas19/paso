# ADR 0006 — Frontend de la Fase 1

**Fecha:** 2026-11-12
**Estado:** aceptado

## Contexto

La Fase 1 (SPEC §10) entrega la libreta: una PWA para iPad que funciona sin conexión, donde escribir con el Pencil se siente inmediato y las notas no se pierden. No toca el backend.

## Decisiones

**El lienzo es código imperativo, no estado de React.** `NotebookCanvas` es una clase que maneja punteros, tinta, zoom y herramientas directamente sobre el DOM. React solo dibuja la barra y la biblioteca. Pasar cada evento del lápiz por el estado de React provocaría un re-render por evento y añadiría latencia justo donde más se nota.

**Dos capas de dibujo.** Cada página visible tiene un canvas con los trazos terminados; encima hay un único canvas del tamaño de la pantalla para lo transitorio (trazo en curso, lazo, selección). Escribir un trazo nunca redibuja la página.

**Zoom por transformación, nitidez después.** Mover y hacer zoom solo cambia una transformación CSS del documento. Los canvas se vuelven a dibujar a la resolución nueva 120 ms después de que el gesto termina. El tope es 4 píxeles por unidad de página, por el límite de memoria de canvas de Safari; más allá la tinta se estira.

**Coordenadas en puntos PDF.** La página mide 612 × 792 unidades (carta). Los trazos no dependen del zoom ni del dispositivo, y exportar a PDF no necesita conversión. Formato en [stroke-format.md](../stroke-format.md).

**Un registro de IndexedDB por trazo.** El autoguardado escribe solo el trazo nuevo. Borrar, mover y deshacer son operaciones «estos trazos se reemplazan por estos», que es también la unidad del historial de deshacer.

**El contorno no se guarda.** Se guardan los puntos centrales; el contorno visible se calcula al dibujar (`perfect-freehand`). Así cambiar el aspecto del trazo no invalida datos. Dos ajustes salieron de probar en el iPad:
- `streamline: 0`: el suavizado recortaba cerca de una cuarta parte de cada esquina en trazos rápidos.
- Los huecos entre muestras lejanas se rellenan con una curva (Catmull-Rom) antes de calcular el contorno; sin eso los trazos rápidos salían adelgazados.

**Las formas son trazos comunes.** Recta, elipse, triángulo y rectángulo se reconocen al mantener el lápiz quieto y se guardan como puntos de un trazo normal. No hay un tipo «forma» en el formato, y el lazo las mueve y estira como a cualquier trazo.

**PDF vectorial con jsPDF.** Cada trazo se exporta como el mismo contorno relleno que se ve en pantalla. La librería se carga solo al exportar y queda en la caché offline.

**Despliegue: archivos estáticos en Cloudflare.** Solo se sube `dist/`; no hay código de servidor. Se eligió una dirección fija porque IndexedDB está ligado al origen: si la dirección cambia, la app instalada empieza vacía.

## Limitaciones conocidas

- **El doble toque del Apple Pencil no existe para la web.** Safari no lo expone. El borrador es de un solo uso desde la barra (SPEC §6.1).
- El historial de deshacer vive en memoria: se pierde al cerrar el cuaderno o reordenar páginas.
- Una selección no se puede mover a otra página.
- Los diálogos de renombrar y confirmar borrado son los nativos del navegador.
- La materia guarda qué plantilla usa, pero la configuración completa (taxonomía, estrategias) se conecta en la Fase 2.
- Los trazos de una página visitada quedan en memoria mientras el cuaderno está abierto.

## Consecuencias

- La lógica que puede perder datos (borrados en cascada, reordenar, exportar) y la geometría (formas, borrador, lazo) son funciones puras o acciones de base de datos con pruebas en `vitest`. El lienzo en sí se prueba en el navegador y en el iPad.
- El formato de trazos y el JSON de exportación son independientes de la PWA, como pide SPEC §12.8.
