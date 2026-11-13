# ADR 0006 — Frontend de la Fase 1

**Fecha:** 2026-11-12
**Estado:** aceptado

## Contexto

La Fase 1 (SPEC §10) entrega la libreta: una PWA para iPad que funciona sin conexión, donde escribir con el Pencil se siente inmediato y las notas no se pierden. No toca el backend.

## Decisiones

**El lienzo es código imperativo, no estado de React.** `NotebookCanvas` es una clase que maneja punteros, tinta, zoom y herramientas directamente sobre el DOM. React solo dibuja la barra y la biblioteca. Pasar cada evento del lápiz por el estado de React provocaría un re-render por evento y añadiría latencia justo donde más se nota.

**Dos capas del tamaño de la pantalla.** Un canvas dibuja las páginas visibles y los trazos terminados; otro encima, lo transitorio (trazo en curso, lazo, selección). Ambos miden lo que la pantalla en píxeles reales. Escribir un trazo solo pinta ese trazo.

**La tinta siempre se dibuja como vectores a resolución de pantalla.** Al mover o hacer zoom, el canvas ya dibujado se desplaza y escala con una transformación CSS para seguir al dedo al instante, y enseguida se redibuja para la vista nueva: al siguiente cuadro si dibujar es barato (≤ 8 ms), o en cuanto el gesto hace una pausa si la página está muy llena. Solo se dibujan los trazos que caen en pantalla.

La primera versión tenía un canvas por página, escalado con una transformación CSS. Se descartó tras probar en el iPad: Safari pintaba esos canvas a la resolución del diseño y luego los estiraba, así que la letra se veía borrosa al terminar cada trazo y peor con zoom, y además había un tope de resolución por el límite de memoria de canvas.

**Coordenadas en puntos PDF.** La página mide 612 × 792 unidades (carta). Los trazos no dependen del zoom ni del dispositivo, y exportar a PDF no necesita conversión. Formato en [stroke-format.md](../stroke-format.md).

**Un registro de IndexedDB por trazo.** El autoguardado escribe solo el trazo nuevo. Borrar, mover y deshacer son operaciones «estos trazos se reemplazan por estos», que es también la unidad del historial de deshacer.

**El contorno no se guarda.** Se guardan los puntos centrales; el contorno visible se calcula al dibujar (`perfect-freehand`). Así cambiar el aspecto del trazo no invalida datos. Dos ajustes salieron de probar en el iPad:
- Los huecos entre muestras lejanas se rellenan con una curva (Catmull-Rom) antes de calcular el contorno; sin eso los trazos rápidos salían adelgazados.
- `streamline` (el suavizado del temblor de la mano) solo es seguro después de ese relleno: sobre muestras lejanas recortaba cerca de una cuarta parte de cada esquina. Queda en `0.2`.

**Las formas son trazos comunes.** Recta, elipse, triángulo y rectángulo se reconocen al mantener el lápiz quieto y se guardan como puntos de un trazo normal. No hay un tipo «forma» en el formato, y el lazo las mueve y estira como a cualquier trazo.

**PDF vectorial con jsPDF.** Cada trazo se exporta como el mismo contorno relleno que se ve en pantalla. La librería se carga solo al exportar y queda en la caché offline.

**Las páginas crecen solas.** Cuando la última página recibe tinta se crea otra en blanco debajo. La exportación parte de las páginas con contenido, así que la página en blanco del final no sale en el PDF.

**Las versiones nuevas entran al reabrir la app.** El service worker nuevo espera a que la app se cierre; recargar en caliente interrumpía la escritura o borraba un nombre a medio teclear.

**Despliegue: archivos estáticos en Cloudflare.** Solo se sube `dist/`; no hay código de servidor. Se eligió una dirección fija porque IndexedDB está ligado al origen: si la dirección cambia, la app instalada empieza vacía.

**El Pencil tiene dos fuentes de eventos.** La principal son los eventos de puntero. Safari no siempre se los entrega al lápiz: con la mano ya apoyada, el primer trazo podía no arrancar hasta levantar y volver a bajar. Los eventos táctiles sí siguen llegando e indican cuál toque es el lápiz (`touchType === "stylus"`), así que sirven de red de seguridad: si el lápiz está sobre el vidrio y no hay trazo en curso, se dibuja desde ellos. Además se llama a `preventDefault` en los eventos táctiles del lienzo para que Safari no se quede con los toques (pulsación larga, desplazamiento).

## Ampliación del 2026-11-13: primera tanda de mecánicas

Aprobada en [el plan de mecánicas](../plan-mecanicas-y-app-nativa.md). Probada en navegador de escritorio con toques simulados; **falta confirmarla en el iPad con la mano apoyada**, que es donde fallaron los gestos anteriores.

**Deshacer con un toque de dos dedos, rehacer con tres.** La decisión es una función pura (`canvas/gestures.ts`) y es estricta a propósito: los dedos deben bajar casi juntos (150 ms), levantarse pronto (300 ms) y no moverse (12 px). Una mano apoyada dura más, apoya sus contactos de uno en uno y resbala. Además sigue valiendo el rechazo de palma: un toque que cae hasta 0.4 s después del lápiz se ignora, así que deshacer justo al levantar la pluma no responde. Se apaga en **⋯ → Gestos de deshacer**.

**Las esquinas de la selección conservan la proporción; los lados estiran en un sentido.** Antes cada esquina estiraba ancho y alto por separado y la letra quedaba chata. Ahora hay ocho puntos: cuatro esquinas (misma escala en ambos sentidos, sin voltear) y cuatro lados (un solo sentido, que es como se cambia la forma de un rectángulo).

**Duplicar la selección** crea trazos nuevos un cuadro abajo y a la derecha y los deja seleccionados. Es una sola operación de deshacer.

**Indicador «Página N de M»** abajo al centro. No recibe toques.

**La barra recuerda pluma, grosor y el ajuste de gestos** (`localStorage`, por dispositivo). Borrador y lazo no se recuerdan: son momentáneos.

**Importar un respaldo** como cuaderno nuevo: ver [stroke-format.md](../stroke-format.md).

### Segunda tanda (mismo día)

**Garabatear para borrar, apagado de fábrica.** Se enciende en **⋯ → Garabatear para borrar**. Con la pluma, un zigzag apretado (cuatro o más idas y vueltas) borra los trazos que **cubre**: los que quedan en su mayoría dentro del garabato y que este realmente cruza. Una raya que tacha un término no da vueltas y no borra nada; un zigzag que solo toca la punta de un trazo largo (una resistencia junto a su cable) tampoco. Si el garabato no cubre nada, se queda como tinta. Es una sola operación de deshacer. Está apagado porque en matemáticas un falso borrado cuesta más que ir al botón.

**Panel de páginas.** **⋯ → Páginas…** abre las miniaturas; tocar una lleva a esa página con el mismo zoom. Cada miniatura se dibuja con el mismo contorno que la hoja, solo cuando entra a la vista. No reordena ni duplica todavía.

**Flecha por pausa.** Un tramo recto que termina con una o dos barbas junto a la punta (como se dibuja una flecha sin levantar el lápiz) y el lápiz quieto se convierte en flecha. Se guarda como un solo trazo común: asta, barba, regreso a la punta, otra barba. La cabeza crece con la flecha, entre 7 y 18 unidades.

**Las rectas se enderezan.** Una recta o flecha a menos de 6° de horizontal, vertical o 45° queda exactamente en esa dirección, sin cambiar su largo; también mientras se ajusta sin levantar. Cualquier otro ángulo sigue libre.

**Las entradas del menú ⋯ van con clave por posición.** Con clave por texto, un ajuste cuyo rótulo cambia al tocarlo se reemplazaba a medio toque, el menú no se cerraba y el siguiente trazo se perdía cerrándolo.

### El trazo, tras la prueba en el iPad (2026-11-13)

Escribir «se siente raro, no tan fluido como otras apps». Se cambiaron dos cosas, **sin poder comprobarlas en el iPad**:

- **Un dibujo por cuadro.** El Pencil informa unas dos veces por cuadro de pantalla; antes se redibujaba el trazo en cada informe. Ahora se redibuja una vez por cuadro con todos los puntos llegados hasta entonces: no aparece más tarde en pantalla y deja la mitad del trabajo libre.
- **El trazo llega hasta la punta.** Mientras se escribe se dibuja como trazo terminado, así que alcanza la última muestra en vez de quedarse un poco atrás, y no cambia de forma al levantar el lápiz.

Medido en esta máquina: recalcular el contorno cuesta 0.2 ms por evento en un trazo de 100 puntos y 0.9 ms en uno de 800. No es ahí donde se pierde la fluidez.

**Lo que una página web no puede igualar.** Safari dibuja las páginas a 60 cuadros por segundo y no ofrece el camino de baja latencia que usan las apps nativas para la tinta. El trazo siempre irá algo más atrás de la punta que en GoodNotes. Envolver la web en una app nativa no lo cambia (ver el plan de app nativa): haría falta dibujar con las herramientas de Apple, es decir, reescribir el lienzo.

### Biblioteca con portadas (2026-11-13)

En la prueba en el iPad no era obvio que el nombre de un cuaderno se podía tocar. Ahora cada cuaderno es una **portada**: la miniatura de su primera página con un lomo, el título y cuántas páginas tiene. Al tocarla se hunde un poco. Renombrar, mover y borrar pasaron a un menú **⋯** en la esquina de cada portada, para que lo principal (abrir) sea lo único grande. «Nuevo cuaderno» es una portada punteada con un **+**.

## Limitaciones conocidas

- **El doble toque del Apple Pencil no existe para la web.** Safari no lo expone. El borrador es de un solo uso, desde la barra (SPEC §6.1). Un doble toque con el dedo se probó como sustituto y se retiró: la mano apoyada lo activaba por accidente.
- El historial de deshacer vive en memoria: se pierde al cerrar el cuaderno o reordenar páginas.
- Una selección no se puede mover a otra página.
- Los diálogos de renombrar y confirmar borrado son los nativos del navegador.
- La materia guarda qué plantilla usa, pero la configuración completa (taxonomía, estrategias) se conecta en la Fase 2.
- Los trazos de una página visitada quedan en memoria mientras el cuaderno está abierto.
- En páginas muy llenas, la tinta puede verse estirada durante un gesto de zoom hasta que el dedo hace una pausa.

## Consecuencias

- La lógica que puede perder datos (borrados en cascada, reordenar, exportar) y la geometría (formas, borrador, lazo) son funciones puras o acciones de base de datos con pruebas en `vitest`. El lienzo en sí se prueba en el navegador y en el iPad.
- El formato de trazos y el JSON de exportación son independientes de la PWA, como pide SPEC §12.8.
