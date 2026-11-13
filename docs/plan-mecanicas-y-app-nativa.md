# Plan: mecánicas de la libreta y ruta a app nativa

**Fecha:** 2026-11-13 · **Estado:** propuesta, espera tu aprobación. **Nada de esto está construido.**

Este documento tiene dos partes y una lista final de decisiones:

- **Parte A.** Qué formas de usar el lápiz y los dedos conviene tomar de GoodNotes, Notability y Derive.
- **Parte B.** Cómo convertir la libreta en una app de iPad sin tener Mac, qué se gana y qué no.

Regla que no cambia: se adoptan **mecánicas** (cómo responde la app a un gesto). Nunca nombre, marca, logos, íconos ni ningún recurso de esas apps (SPEC §1).

## Cómo leer las fuentes

La investigación se hizo el 13 de noviembre de 2026 desde una sesión en la nube que **no pudo abrir** varias páginas de soporte (GoodNotes, Notability, Derive, Capacitor, WebKit, documentación de GitHub). Para esas se usaron los extractos que devuelve el buscador. Por eso cada dato lleva una marca:

- **[leído]**: se abrió la página original y dice eso.
- **[extracto]**: viene del resumen del buscador sobre la página oficial. Probablemente correcto; los nombres exactos de menús pueden variar.
- **[tercero]**: lo dice un blog o foro, no el fabricante.
- **[sin verificar]**: no se encontró fuente. No lo des por cierto.

Las fuentes están numeradas al final. **Todo lo de Derive es [extracto] o peor**: la app es nueva (versión 1.0) y la única fuente es su ficha de la tienda. Tú la tienes instalada: cinco minutos probándola valen más que esa columna.

Los esfuerzos son estimaciones mías, no mediciones: **chico** = medio día o menos, **mediano** = uno o dos días, **grande** = varios días y riesgo de romper algo que ya funciona.

---

# Parte A. Mecánicas

Lo que «existe hoy» se sacó leyendo `frontend/src/canvas/` (`NotebookCanvas.ts`, `Toolbar.tsx`, `CanvasView.tsx`, `view.ts`) y `frontend/src/strokes/`, no de memoria.

## A1. Dedos y lápiz

**En las otras apps**

- GoodNotes: la palma se ignora sola con Apple Pencil. Con zoom, un dedo mueve la hoja y dos dedos acercan o alejan. Deshacer es un **doble toque con dos dedos**; rehacer, doble toque con tres. [extracto 1, 3, 4]
- Notability: con el Pencil, un dedo desplaza. Los gestos de deshacer (toque con dos dedos, rehacer con tres) existen pero vienen **apagados** de fábrica. [extracto 20, 21]
- Derive: «toque con dos dedos para deshacer, pellizco para zoom». [extracto 34]
- En las tres, el doble toque del Pencil y el apretón del Pencil Pro cambian de herramienta. Eso solo lo recibe una app nativa (ver Parte B).

**Hoy en Paso**

- El lápiz escribe; un dedo desplaza, con inercia al soltar; dos dedos hacen zoom y mueven a la vez.
- La palma: un toque que cae mientras el lápiz trabaja, o hasta 0.4 s después, se ignora. Si la mano llegó antes que la punta y alcanzó a mover la hoja, la hoja regresa a su lugar.
- El lápiz se lee por dos vías (eventos de puntero y eventos táctiles) porque Safari a veces retiene la primera. **Esto sigue sin confirmarse en el iPad.**
- No hay ningún gesto para deshacer. No se puede escribir con el dedo.

**Qué faltaría**

| Mecánica | Prioridad | Esfuerzo | Nota |
|---|---|---|---|
| Deshacer con toque de dos dedos, rehacer con tres | **Alta** | Chico | Es el gesto que más ahorra viajes a la barra. Riesgo: ya quitamos un doble toque de un dedo porque la mano apoyada lo disparaba (ADR 0006). Este exige dos dedos que bajen y suban casi juntos sin moverse, y nunca justo después del lápiz. Debe poder apagarse en ajustes, como hace Notability. |
| Escribir con el dedo (interruptor) | Baja | Chico | Solo sirve sin lápiz. No lo necesitas. |

## A2. Borrador

**En las otras apps**

- GoodNotes: tres modos (de precisión, por tramo, por trazo completo), un filtro para borrar solo cierto tipo de tinta, y «volver sola a la pluma» al levantar el lápiz. Además, **garabatear encima de algo lo borra** sin cambiar de herramienta. [extracto 5, 6]
- Notability: borrador parcial y borrador de trazo completo, con tamaños; volver sola a la pluma es un ajuste. [extracto 22]
- Derive: tiene borrador; no se encontraron sus modos. [extracto 34]

**Hoy en Paso**

- Borra **trazos completos**, con un círculo de tamaño fijo.
- Es de un solo uso: borra y al levantar el lápiz vuelve la pluma. No se puede dejar fijo.
- Borra pluma y resaltador por igual.

**Qué faltaría**

| Mecánica | Prioridad | Esfuerzo | Nota |
|---|---|---|---|
| Garabatear para borrar | **Alta** | Mediano | Es el mejor sustituto del doble toque del Pencil que una app web puede tener: borras sin tocar la barra. Riesgo real en matemáticas: tachar un término con una raya para cancelarlo **no** debe borrarlo; solo un zigzag apretado cuenta. Tiene que poder apagarse y deshacerse con un gesto. |
| Dejar el borrador fijo (segundo toque al botón) | Media | Chico | Para borrar mucho de corrido. |
| Borrar solo resaltador | Baja | Chico | |
| Borrador parcial (cortar un trazo por la mitad) | Baja | Grande | Obliga a partir trazos guardados; toca el autoguardado y el deshacer. Para ecuaciones, borrar el trazo entero casi siempre basta. |

## A3. Lazo

**En las otras apps**

- GoodNotes: lazo libre o rectangular; después de seleccionar ofrece mover, cambiar tamaño, girar, cambiar color, copiar, convertir a texto o matemáticas y tomar captura. También «dibuja un círculo y mantén» para seleccionar sin cambiar de herramienta. [extracto 7, 8]
- Notability: selección libre o en caja; pellizcar dentro cambia el tamaño, torcer con dos dedos gira; copiar, cortar, cambiar estilo, convertir. [extracto 23]
- Derive: tiene lazo; no se encontró más. [extracto 34]

**Hoy en Paso**

- Lazo libre. Toma los trazos que quedan al menos a la mitad dentro, **solo de la página donde empezaste**.
- Con la selección: arrastrar desde dentro la mueve; arrastrar una esquina la estira (ancho y alto por separado, así que puede deformar); botón de borrar; botón **Revisar**.
- No hay copiar ni duplicar, ni cambiar color, ni girar, ni pasar la selección a otra página.

**Qué faltaría**

| Mecánica | Prioridad | Esfuerzo | Nota |
|---|---|---|---|
| Duplicar la selección | **Alta** | Chico | Repetir una ecuación o un pedazo de circuito es de todos los días. |
| Estirar sin deformar (proporción fija por omisión) | Media | Chico | Hoy una letra estirada de una esquina queda chata. |
| Cambiar el color de lo seleccionado | Media | Chico | |
| Mover la selección a otra página | Media | Mediano | Hoy es una limitación anotada en el ADR 0006. |
| Girar | Baja | Mediano | Poco uso en apuntes de matemáticas. |
| «Círculo y mantener» para seleccionar | No adoptar | — | Choca con nuestra forma por pausa: hoy un círculo sostenido se vuelve elipse. |

## A4. Formas

**En las otras apps**

- GoodNotes: trazar y mantener al final para enderezar, ajustando tamaño y ángulo sin levantar; además una herramienta de formas, relleno, y puntos para editar la forma después. [extracto 9, 10]
- Notability: mantener hasta que la forma «salte»; reconoce círculo, elipse, triángulo, cuadrado, rectángulo, pentágono, hexágono y **flecha**. [extracto 24]
- Derive: tiene ajustes de formas; no se encontró más. [extracto 34]

**Hoy en Paso**

- Mantener el lápiz quieto 0.55 s convierte el trazo en recta, elipse, triángulo o rectángulo, y se puede ajustar mientras no levantes.
- La forma se guarda como un trazo normal: el lazo la mueve y estira, pero ya no «sabe» que es una forma.

**Qué faltaría**

| Mecánica | Prioridad | Esfuerzo | Nota |
|---|---|---|---|
| Flecha | Media | Chico | Útil en diagramas de cuerpo libre, corrientes y bloques. |
| Rectas que se pegan a horizontal, vertical y 45° | Media | Chico | Ejes y circuitos quedan limpios. |
| Editar los vértices de una forma ya hecha | Baja | Grande | Exigiría un tipo «forma» en el formato de trazos (nueva versión del formato y migración). |
| Relleno | No adoptar | — | No aporta a apuntes de ingeniería. |

## A5. Páginas y miniaturas

**En las otras apps**

- GoodNotes: desplazamiento vertical u horizontal a elegir; una barra lateral con miniaturas desde donde se agrega, duplica, reordena arrastrando y cambia la plantilla. [extracto 11, 12]
- Notability: vista continua vertical o página por página; un panel de miniaturas con agregar, duplicar, borrar y reordenar. [extracto 25, 26]
- Derive: lienzo infinito en vez de páginas. [extracto 34] [tercero 36]

**Hoy en Paso**

- Páginas tamaño carta una debajo de otra; al escribir en la última aparece otra.
- En el menú **⋯**: subir, bajar o borrar la página que está al centro de la pantalla.
- El fondo (cuadrícula, rayado, blanco) se cambia por página.
- **No hay miniaturas, ni número de página, ni forma de saltar a una página.** En un cuaderno de 40 páginas solo queda desplazar.

**Qué faltaría**

| Mecánica | Prioridad | Esfuerzo | Nota |
|---|---|---|---|
| Indicador «página 7 de 40» al desplazar | **Alta** | Chico | |
| Panel de miniaturas para saltar a una página | **Alta** | Mediano | Las miniaturas se dibujan con el mismo código que ya pinta los trazos. |
| Reordenar arrastrando miniaturas, duplicar e insertar página en medio | Media | Mediano | Hoy reordenar borra el historial de deshacer; habría que cuidarlo. |
| Lienzo infinito | No adoptar | — | Contradice el tamaño carta y el PDF fiel a la hoja (SPEC §6.1, §6.7). |

## A6. Zoom

**En las otras apps**

- GoodNotes: pellizco y doble toque; además una **ventana de zoom**: escribes grande en una franja inferior y el texto queda chico en la hoja, avanzando solo. [extracto 3, 13]
- Notability: pellizco y una «vista de zoom» equivalente. [extracto 27]
- Derive: pellizco; la tinta sigue nítida muy de cerca. [extracto 34]

**Hoy en Paso**

- Pellizco de 0.4× a 6×, anclado donde están los dedos. La tinta se redibuja nítida a cualquier zoom.
- Al abrir, la página se ajusta al ancho. No hay forma rápida de volver a ese ajuste.

**Qué faltaría**

| Mecánica | Prioridad | Esfuerzo | Nota |
|---|---|---|---|
| Botón «ajustar al ancho» | Media | Chico | Botón, no doble toque con el dedo: ese ya nos falló con la palma. |
| Ventana de zoom para escribir | Baja | Grande | Potente para letra pequeña, pero es casi un segundo lienzo. Solo si la echas de menos tras semanas de uso. |

## A7. Barra de herramientas

**En las otras apps**

- GoodNotes: tres colores a la vista, ampliables; desde 2025 una barra flotante que se acomoda en cualquier borde. [extracto 14] [tercero 15]
- Notability: barra reordenable, plumas duplicadas cada una con su estilo, una tira de favoritos y un modo que deja a la vista solo la herramienta activa. [extracto 28, 29, 30]
- Derive: barra que recuerda la última herramienta. [extracto 34]

**Hoy en Paso**

- Barra flotante fija arriba al centro: biblioteca, lazo, cuatro plumas de color, tres grosores, resaltador (un solo amarillo), borrador, deshacer, rehacer, fondo y menú.
- Un toque cambia de pluma. No se puede mover ni personalizar colores.

**Qué faltaría**

| Mecánica | Prioridad | Esfuerzo | Nota |
|---|---|---|---|
| Recordar pluma y grosor al reabrir | Media | Chico | |
| Mover la barra abajo o a un lado | Media | Chico | Para zurdos o para que no tape el primer renglón. |
| Colores a elegir y colores de resaltador | Baja | Chico | El SPEC pide cuatro colores; ampliar es decisión tuya. |
| Ocultar la barra mientras escribes | Baja | Mediano | |

## A8. Deshacer

**En las otras apps**: botones en la barra más los gestos de A1. Ninguna muestra un historial. [extracto 4, 21]

**Hoy en Paso**

- Botones de deshacer y rehacer, sin límite de pasos.
- El historial vive en memoria: se pierde al cerrar el cuaderno o al reordenar páginas.

**Qué faltaría**: solo los gestos de A1. Guardar el historial entre sesiones no lo hace ninguna de las tres y no lo recomiendo.

## Orden que propongo

1. **Primera tanda (lo que más se nota, poco riesgo):** deshacer con dos dedos, indicador de página, duplicar selección, estirar sin deformar, recordar la pluma.
2. **Segunda tanda:** panel de miniaturas, garabatear para borrar, flecha y rectas que se pegan.
3. **Después, solo si lo pides:** mover selección entre páginas, borrador fijo, mover la barra.

Cada gesto nuevo se prueba en el iPad con la mano apoyada antes de darlo por bueno: los dos fallos que ya tuvimos con gestos vinieron de ahí.

---

# Parte B. App nativa para iPad sin Mac

## Lo primero: esto cambia una decisión del SPEC

El SPEC dice que la app nativa está **fuera del alcance** (§3) y solo pide dejar la puerta abierta (§12.8). Seguir esta ruta es cambiar esa decisión. No es una reescritura: la idea es **envolver** la misma libreta web en una cáscara nativa.

## Qué se gana

1. **El doble toque del Apple Pencil** (y el apretón del Pencil Pro). Una app nativa lo recibe con una pieza de Apple llamada `UIPencilInteraction`. [leído 40, 41] La web no puede: hay una petición abierta en WebKit sin respuesta. [extracto 42] Lo conectaríamos al borrador de un solo uso, como ya prevé el SPEC §6.1.
   - **No existe un complemento ya hecho** para Capacitor; hay que escribir uno pequeño en Swift (unas 50 líneas). [leído: búsqueda en el registro de npm]
   - Apple pide respetar lo que el usuario eligió en Ajustes → Apple Pencil. [leído 40]
2. **Almacenamiento más seguro, pero no automático.** Aquí la investigación matiza lo que creíamos:
   - Una app web **instalada en la pantalla de inicio** ya tiene su propio contador y no sufre el borrado a los 7 días de Safari mientras la uses. [extracto 43] El riesgo actual es menor de lo que dice hoy el README.
   - Dentro de una app nativa, los datos de la parte web **también** pueden ser reclamados por iOS si el iPad se queda sin espacio. Lo advierte la propia guía de Capacitor. [extracto 45]
   - Lo que iOS no purga es la carpeta **Documentos** de la app, que además entra en el respaldo de iCloud. [extracto 46] [tercero 47] La ganancia real llega si la app guarda ahí una copia (por ejemplo, el JSON de cada cuaderno al cerrarlo). Eso es trabajo adicional, chico, que la versión web no puede hacer.
3. **Funciona sin conexión sin trucos**: los archivos van dentro de la app.

## Qué no se gana

- **La latencia del trazo no mejora por envolver.** Es el mismo motor de Safari. No se encontró ninguna medición que diga lo contrario. [sin verificar]
- La parte web dentro de una app parece limitada a 60 cuadros por segundo. [extracto 48] Apple dice que la tinta de baja latencia requiere dibujar con sus herramientas nativas (PencilKit, Metal). [extracto 49] Eso sería reescribir el lienzo: otra decisión, mucho más grande, que este plan **no** propone.
- No se gana nada en la revisión con IA: el backend es el mismo.

## Qué se pierde o se complica

- **Las notas no pasan solas.** La app nativa es «otra dirección» para el almacenamiento, igual que advierte la regla 10 de `CLAUDE.md`. Empieza vacía. Habría que exportar cada cuaderno a JSON en la PWA e importarlo en la nueva. **Hoy la libreta exporta JSON pero no sabe importarlo**: esa función falta y conviene tenerla de todos modos, porque sin ella el respaldo actual no se puede restaurar.
- **Publicar deja de ser un comando.** Hoy `npm run deploy` y listo. Con app nativa cada cambio es: compilar en la nube, subir a TestFlight, actualizar en el iPad (unos 15 a 30 minutos, estimación mía).
- **Depurar sin Mac es incómodo.** El inspector de Safari necesita macOS. Existe un puente para Windows [tercero 58], sin confirmar que funcione con el iPadOS actual.
- El backend tendría que aceptar el origen de la app nativa en `ALLOWED_ORIGINS`.

## La ruta, paso a paso

**Etapa 0, gratis y útil aunque no sigas (no requiere pagar nada):**

1. Agregar «Importar cuaderno desde JSON» a la libreta.
2. Añadir Capacitor al proyecto. La versión estable es la 8.6.2 [leído: registro de npm]; pide Xcode 26 y iOS 15 o más nuevo [extracto 38]. Crear la carpeta del proyecto de iOS funciona en Windows; lo que exige macOS es compilar y firmar. [tercero 39]
3. Configurar la compilación en una Mac en la nube e intentar compilar **sin firmar**, solo para comprobar que el proyecto arma. (Que esto se pueda sin cuenta de pago es suposición mía razonable, [sin verificar].)

**Etapa 1, aquí se paga:**

4. Inscribirte en el Apple Developer Program: **99 USD al año**, cobrados en moneda local donde aplique. [leído 50] El precio exacto en pesos no se encontró. [sin verificar] Requisitos: cuenta de Apple con verificación en dos pasos y mayoría de edad; pueden pedir identificación. [leído 50] No hay exención para estudiantes individuales. [tercero 51]
5. Crear desde el navegador el identificador de la app y una llave del API de App Store Connect. Los certificados de firma se pueden generar sin Mac. [extracto 53, 54] [tercero 52]
6. Elegir dónde compilar:

| Servicio | Gratis al mes | Nota |
|---|---|---|
| Codemagic | 500 minutos en Mac, cuentas personales [extracto 54] | Firma automática con tu llave. **Mi recomendación.** |
| GitHub Actions | Sin costo si el repositorio es público; si es privado, unos 200 minutos de Mac [extracto 55] [tercero 56] | Ya usas GitHub. |
| Xcode Cloud | 25 horas con la membresía [extracto 57] | **Descartado: el primer flujo se configura desde Xcode en una Mac.** [leído 57b] |
| Rentar una Mac por horas | Desde unos 0.22 EUR la hora, mínimo 24 h [tercero 59] | Solo como plan B para depurar. |

**Etapa 2, instalar en el iPad:**

7. **TestFlight, pruebas internas.** Subes la compilación, te agregas como probador e instalas desde la app TestFlight. No pasa revisión de Apple (esa es para probadores externos) y no pide activar el «modo desarrollador». [leído 60, 61]
   - **Cada compilación caduca a los 90 días.** [leído 60] Hay que subir una nueva antes; se puede programar para que la nube lo haga sola cada mes.
8. Escribir el complemento del doble toque y conectarlo al borrador.
9. Guardar copia de los cuadernos en Documentos.

**Rutas que descarto**

- **Instalación directa («ad hoc»)**: exige el modo desarrollador, y Apple dice que ese interruptor solo aparece si el iPad se emparejó alguna vez con una Mac. [leído 61] Sin Mac, hay reportes encontrados sobre si se puede. [tercero 62]
- **Cuenta gratuita con herramientas de terceros**: la app caduca cada 7 días y hay que reinstalarla desde la PC. [leído 63] [tercero 64] No sirve para una libreta de uso diario.

## ¿Hace falta una Mac prestada?

- **En el papel, nunca**: Capacitor en Windows + Codemagic + TestFlight no tocan una Mac tuya.
- **En la práctica, una tarde prestada puede ahorrar días** si el complemento en Swift no funciona a la primera: ahí Xcode enseña el error exacto y desde Windows se trabaja casi a ciegas. No es requisito; es el plan B. Rentar una Mac en la nube 24 horas cumple lo mismo.

## Costos

| Concepto | Costo |
|---|---|
| Apple Developer Program | 99 USD al año, recurrente |
| Compilación en la nube | 0, dentro de los minutos gratis (una compilación ronda 10 a 15 minutos, estimación mía) |
| Mac rentada, solo si hay que depurar | del orden de 5 a 30 USD por día |
| Tu tiempo y el mío | Etapa 0: 1 a 2 días. Etapas 1 y 2: 3 a 5 días, con riesgo de alargarse por la firma y el complemento |

## Riesgos

1. **Si dejas de pagar, la app deja de abrir.** Apple no lo dice de TestFlight en su página de renovación [leído 65]; un reporte en su foro dice que las compilaciones se detienen de inmediato [tercero 66]. Las notas quedarían dentro de una app que no abre. Por eso el respaldo a Documentos y la importación de JSON van **antes** de mudarte.
2. **Los 90 días de TestFlight.** Si se te pasa, la app no abre hasta instalar una compilación nueva. Los datos deberían conservarse al actualizar [sin verificar]; habría que probarlo con un cuaderno de prueba antes de confiarle notas reales.
3. **El doble toque puede no llegar a la primera** dentro de la parte web de la app; es código nuevo sin Mac para depurar.
4. **Dos caminos de publicación** (web y nativa) mientras convivan.
5. **Todo [extracto] y [tercero] de arriba puede estar desactualizado.** Antes de pagar, vale revisar a mano las fuentes 38, 50, 54 y 60.

## Mi recomendación

No pagar todavía. Hacer la **Etapa 0** cuando toque (la importación de JSON hace falta de cualquier modo) y, antes de eso, la primera tanda de la Parte A: el deshacer con dos dedos y el garabato para borrar cubren buena parte de lo que el doble toque daría, gratis y sin mantenimiento. Si después de un par de semanas de uso real el doble toque sigue siendo lo que más extrañas, entonces sí vale los 99 USD al año.

---

# Decisiones que te tocan

1. **¿Apruebas la primera tanda de mecánicas** (deshacer con dos dedos, indicador de página, duplicar selección, estirar sin deformar, recordar la pluma)? ¿Quitas o agregas algo?
2. **¿Garabatear para borrar**, sabiendo que puede confundirse con un tachón? ¿Encendido o apagado de fábrica?
3. **¿Miniaturas de páginas** en la segunda tanda, o antes?
4. **¿Hacemos ya «Importar cuaderno desde JSON»?** Hoy el respaldo no se puede restaurar. Lo recomiendo con independencia de todo lo demás.
5. **¿Cambiamos el SPEC para permitir una app nativa envuelta?** Sí, no, o «después de probar la Etapa 0».
6. **¿Pagas la cuenta de desarrollador de Apple** (99 USD al año, recurrente)? Mi sugerencia: todavía no.
7. Si sigues adelante: **¿Codemagic o GitHub Actions?** ¿El repositorio es público o privado?
8. **¿Tienes a quién pedirle una Mac una tarde**, por si el complemento del doble toque se atora?
9. **¿Corrijo en el README** la frase sobre que Safari puede borrar las notas tras semanas sin abrir la app? Según WebKit [extracto 43], instalada en la pantalla de inicio el riesgo es por falta de espacio, no por tiempo. Preferí no tocarla sin que lo veas.

---

# Fuentes

Consultadas el 2026-11-13. La marca de cada dato está en el texto.

**GoodNotes**

1. Rechazo de palma: https://support.goodnotes.com/hc/en-us/articles/7353727026959-Configure-palm-rejection-for-comfortable-writing
2. Pluma: https://support.goodnotes.com/hc/en-us/articles/5898596859279-Write-with-the-Pen-tool
3. Zoom y desplazamiento: https://support.goodnotes.com/hc/en-us/articles/6554036735631-Zoom-pan-and-scroll-through-pages-in-Goodnotes
4. Gestos de deshacer y rehacer: https://support.goodnotes.com/hc/en-us/articles/14069931315983-Quick-gestures-for-Undo-and-Redo
5. Borrador: https://support.goodnotes.com/hc/en-us/articles/7353718249231-Erasing-content
6. Garabatear para borrar: https://support.goodnotes.com/hc/en-us/articles/7443501398671-How-to-Use-Scribble-to-Erase
7. Lazo: https://support.goodnotes.com/hc/en-us/articles/7353695644175-Select-Move-and-Edit-Content-With-the-Lasso-Tool
8. Círculo para seleccionar: https://support.goodnotes.com/hc/en-us/articles/7443556793103-Select-content-with-the-Circle-to-Lasso-pen-gesture
9. Herramienta de formas: https://support.goodnotes.com/hc/en-us/articles/13682939148943-Improved-Shape-Tool
10. Líneas y formas perfectas: https://support.goodnotes.com/hc/en-us/articles/7353718215951-Draw-perfect-lines-curves-and-shapes
11. Dirección de desplazamiento: https://support.goodnotes.com/hc/en-us/articles/7353695996559-Set-the-scrolling-direction-to-horizontal-or-vertical
12. Páginas y barra lateral: https://support.goodnotes.com/hc/en-us/articles/5898537788815-Manage-pages-in-Document-View y https://support.goodnotes.com/hc/en-us/articles/9497798035983-Use-the-Sidebar-to-navigate-your-document
13. Ventana de zoom: https://support.goodnotes.com/hc/en-us/articles/7353756826383-Write-with-the-Zoom-Window
14. Colores predefinidos: https://support.goodnotes.com/hc/en-us/articles/7353743265039-Adding-colors-to-the-pen-and-highlighter-presets
15. Barra flotante (foro de usuarios): https://feedback.goodnotes.com/forums/191274-customer-suggestions-for-goodnotes-apple/suggestions/50579222--toolbar-make-the-new-floating-toolbar-optional
16. Apple Pencil Pro: https://support.goodnotes.com/hc/en-us/articles/9757771783823-Utilize-the-new-features-of-Apple-Pencil-Pro

**Notability**

20. Escribir con Apple Pencil: https://support.gingerlabs.com/hc/en-us/articles/218333197-Writing-with-Apple-Pencil
21. Ajustes y gestos: https://support.gingerlabs.com/hc/en-us/articles/5955260981786-Settings-Appearances-Tools-Gestures
22. Borrador: https://support.gingerlabs.com/hc/en-us/articles/360029432891-Eraser
23. Herramienta de selección: https://support.gingerlabs.com/hc/en-us/articles/360018646412-Select-Tool
24. Formas: https://support.gingerlabs.com/hc/en-us/articles/226905028-Creating-and-Styling-Perfect-Shapes
25. Vistas de la nota: https://intercom.help/notability/en-us/articles/16300185-note-view-settings
26. Administrador de páginas: https://support.gingerlabs.com/hc/en-us/articles/206059167-Content-Manager-and-Bulk-Actions
27. Vista de zoom: https://support.gingerlabs.com/hc/en-us/articles/206058497-Zoom-View
28. Personalizar la barra: https://support.gingerlabs.com/hc/en-us/articles/6272405402650-Customize-your-Toolbox
29. Herramientas favoritas: https://support.gingerlabs.com/hc/en-us/articles/360048463032-Favorite-Tools
30. Modo de enfoque: https://support.gingerlabs.com/hc/en-us/articles/11012024558106-Focus-Mode
31. Apretón del Pencil Pro: https://support.gingerlabs.com/hc/en-us/articles/7316896037786-Squeeze-Gestures-with-Apple-Pencil-Pro

**Derive**

34. Ficha en la tienda: https://apps.apple.com/us/app/derive-handwritten-math-notes/id6763991536
35. Sitio y soporte: https://www.derivenotes.com/ y https://www.derivenotes.com/support
36. Reseña de un tutor: https://heywoodacademies.com/derive-notes-review/

**Capacitor y Apple Pencil**

38. Requisitos de Capacitor 8: https://capacitorjs.com/docs/next/updating/8-0 y https://ionic.io/blog/announcing-capacitor-8
39. Capacitor en Windows: https://capgo.app/blog/capacitor-development-on-windows/
40. Doble toque del Pencil: https://developer.apple.com/documentation/applepencil/handling-double-taps-from-apple-pencil
41. Apretón del Pencil Pro: https://developer.apple.com/documentation/applepencil/handling-squeezes-from-apple-pencil
42. Petición abierta en WebKit: https://bugs.webkit.org/show_bug.cgi?id=296943 y https://developer.apple.com/forums/thread/760238

**Almacenamiento y latencia**

43. Límite de 7 días y apps en pantalla de inicio: https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
44. Política de almacenamiento de WebKit: https://webkit.org/blog/14403/updates-to-storage-policy/
45. Guía de almacenamiento de Capacitor: https://capacitorjs.com/docs/guides/storage
46. Sistema de archivos en Capacitor: https://capacitorjs.com/docs/apis/filesystem
47. Documentos y respaldo de iCloud: https://capgo.app/blog/capacitor-file-handling-guide/
48. Límite de 60 cuadros por segundo: https://bugs.webkit.org/show_bug.cgi?id=294338 y https://bugs.webkit.org/show_bug.cgi?id=173434
49. Tinta de baja latencia (WWDC 2019, sesión 221): https://developer.apple.com/videos/play/wwdc2019/221

**Cuenta de Apple, compilación e instalación**

50. Inscripción al programa: https://developer.apple.com/help/account/membership/program-enrollment/
51. Exenciones de cuota: https://developer.apple.com/support/fee-waiver/
52. Certificado desde Windows con openssl: https://gist.github.com/jcward/d08b33fc3e6c5f90c18437956e5ccc35
53. API de App Store Connect, perfiles: https://developer.apple.com/documentation/appstoreconnectapi/profiles
54. Codemagic, precios y firma: https://docs.codemagic.io/billing/pricing/ y https://docs.codemagic.io/partials/code-signing-ios-obtain-certificate/
55. GitHub Actions, facturación: https://docs.github.com/en/billing/concepts/product-billing/github-actions
56. GitHub Actions, precios de macOS: https://cicdcost.com/github-actions-pricing
57. Xcode Cloud: https://developer.apple.com/xcode-cloud/get-started · 57b. Primer flujo desde Xcode: https://developer.apple.com/documentation/xcode/configuring-your-first-xcode-cloud-workflow
58. Depuración desde Windows: https://github.com/google/ios-webkit-debug-proxy
59. Mac por horas: https://www.greenmini.nl/compare/scaleway-alternative/ y https://aws.amazon.com/ec2/instance-types/mac/
60. TestFlight: https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/
61. Modo desarrollador: https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device
62. Modo desarrollador sin Mac, reportes: https://docs.expo.dev/guides/ios-developer-mode/ y https://blog.diawi.com/2022/10/25/developer-mode-required-in-ios-ipados-16
63. Cuenta gratuita y de pago: https://developer.apple.com/support/compare-memberships/
64. Instalación con herramientas de terceros: https://sideloadly.io/faq
65. Renovación de la membresía: https://developer.apple.com/support/renewal/
66. TestFlight al vencer la membresía (foro): https://developer.apple.com/forums/thread/841920
