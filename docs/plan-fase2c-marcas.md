# Plan de la entrega 2c: marcas sobre la hoja

**Fecha:** 2026-11-13 · **Estado:** aprobado el 2026-11-13. **Todavía no hay nada construido.**

**Decisiones tomadas:** opción C en dos etapas; una marca se toca con el dedo o con el lápiz; insignia única cuando no se sabe dónde va cada paso; las marcas no salen en el PDF. La etapa 1 empieza después de la primera prueba en el iPad de lo ya construido; la etapa 2, cuando exista la línea base del banco de pruebas.

## Qué es

Hoy el resultado de una revisión vive solo en el panel lateral. La 2c lo lleva a la hoja, como pide el SPEC §6.4:

- Una marca pequeña junto a cada renglón revisado: **✓** verde, **✕** rojo o **⚠** ámbar. El paso con error, subrayado en rojo.
- Tocar una marca abre una **tarjeta** junto al paso: qué dijo el verificador y, si ya la pediste, la pista.
- La tarjeta se puede fijar o cerrar. Al corregir un paso o volver a revisar, las marcas se actualizan.

## El problema de fondo: dónde está cada paso

Para poner una marca junto a un renglón hay que saber **dónde quedó ese paso en la hoja**. Hoy el modelo devuelve los pasos en orden, pero no dice dónde están. Hay tres formas de averiguarlo:

| Opción | Cómo | A favor | En contra |
|---|---|---|---|
| **A. Solo geometría** | Agrupar los trazos de la selección en renglones por su altura, y repartir los pasos en orden. | No toca al modelo: no cuesta ni hay que medir nada. | Falla cuando renglones y pasos no coinciden: una fracción alta parece dos renglones; dos pasos en un mismo renglón parecen uno. |
| **B. Que el modelo dé un recuadro por paso** | Se agrega un campo «posición» a lo que el modelo devuelve. | Resuelve fracciones, pasos lado a lado, texto y diagramas. | Cambia el prompt y el contrato de lectura: **hay que medirlo con el banco de pruebas** (SPEC §12.4). No sabemos qué tan preciso es el modelo dando posiciones. |
| **C. Las dos juntas** | El modelo da un recuadro aproximado; el recuadro exacto se saca de los **trazos** que caen dentro. | El modelo solo tiene que acertar «más o menos»; la precisión la ponen los trazos, que ya tenemos. Si el modelo no da posición, queda la opción A como respaldo. | Lo mismo que B: hay que medir. |

**Recomiendo la C**, construida en dos etapas para no quedar bloqueados por el banco de pruebas.

### Una regla que no se negocia

Una posición equivocada pone la marca en el renglón equivocado, y un **✕ junto a un paso correcto** es, a la vista, un falso error: lo peor que puede pasar en este proyecto. Por eso:

- Si no hay seguridad de dónde está un paso, **ese paso no lleva marca en la hoja**. Sigue apareciendo en el panel, como hoy.
- Si no se puede ubicar ninguno, la selección lleva **una sola insignia** en su esquina («1 con error» o «sin errores») que abre el panel.

Mejor una marca de menos que una mal puesta.

## Etapas

### Etapa 1: todo lo que no depende del modelo

Se puede construir y probar ya, sin gastar y sin banco de pruebas.

1. **Dibujar las marcas** en la hoja, como vectores, igual que la tinta: se mueven y hacen zoom con la página y se ven nítidas.
2. **Posición por geometría (opción A)**, usada solo cuando es inequívoca: mismo número de renglones que de pasos. Si no, la insignia única.
3. **Las marcas siguen a sus trazos.** Cada marca recuerda qué trazos son su paso, no una coordenada fija. Consecuencias:
   - Si mueves el desarrollo con el lazo, las marcas se van con él.
   - Si borras el paso, su marca desaparece.
   - Si borras o cambias trazos de un desarrollo ya revisado, sus marcas se ven **atenuadas** («revisión desactualizada») hasta que vuelvas a revisar.
4. **La tarjeta.** Al tocar una marca: el estado, lo que dijo el verificador, «Corregir lectura», y la pista si ya existe. Si no existe, un botón **Pedir pista**; nunca se pide sola, porque cuesta. Un enlace abre el panel completo.
5. **Varias revisiones del mismo desarrollo:** manda la más reciente; las marcas de las anteriores se ocultan.
6. **Sin conexión:** las marcas y tarjetas de revisiones ya hechas se ven, porque las revisiones ya se guardan en el iPad.

### Etapa 2: que el modelo diga dónde está cada paso

**Requiere antes el banco de pruebas con su línea base** (unos 10 casos confirmados y una corrida de `app.eval`). Sin eso no se puede saber si el cambio empeora la lectura, y la regla 7 de `CLAUDE.md` prohíbe hacerlo a ciegas.

1. Agregar al paso un recuadro opcional, en proporciones de la imagen (de 0 a 1), para que no dependa del tamaño al que se envíe.
2. Pedirlo en el prompt de reconocimiento. **Esto cambia la versión del prompt.**
3. **Ajustar a los trazos:** los trazos cuyo centro cae dentro del recuadro son el paso. Un trazo nunca pertenece a dos pasos. Si a un recuadro no le toca ningún trazo, ese paso se queda sin marca.
4. **Medir, y decidir con números:**
   - La exactitud de lectura **no puede bajar** respecto a la línea base. Si baja, el cambio no entra.
   - Posición: en cuántos pasos el recuadro cae sobre el renglón correcto. Para saberlo, el caso de prueba guardará también los trazos, y `app.eval` generará por cada caso una imagen con los recuadros dibujados para revisarla a ojo.
   - Costo y tiempo por revisión, antes y después.
5. Si pasa, la posición del modelo sustituye a la geométrica; la geométrica queda de respaldo.

## Qué cambia en el código

- **Frontend:** `NotebookCanvas` dibuja las marcas y avisa cuando se toca una; un módulo nuevo y puro (con pruebas) para agrupar trazos en renglones y ajustar recuadros a trazos; un componente para la tarjeta. La revisión guardada en el iPad gana un campo con los trazos de cada paso: es un campo más en un registro existente, no una tabla nueva.
- **Backend (solo etapa 2):** campo opcional de posición en `Step` y en el esquema que llena el modelo; el prompt `recognize.system.md`; `app.case` guarda los trazos junto al caso; `app.eval` dibuja los recuadros. Las revisiones viejas siguen leyéndose: el campo es opcional.
- **Documentación:** ADR 0007, `README.md`, `CLAUDE.md`.

## Qué queda fuera de la 2c

- **Nivel 2** («Ver explicación completa» con el paso corregido y el porqué) y el **chat**: son de la Fase 3. El enlace de la tarjeta abre el panel de hoy.
- **Revisar la página entera sin lazo** (SPEC §6.1). Hoy solo se revisa una selección.
- **Marcas en el PDF exportado.**
- **Banco de errores.** Es de la Fase 4.

## Riesgos

1. **Tocar una marca con la mano apoyada.** Los toques accidentales ya nos tumbaron dos gestos. Aquí el daño es menor (se abre una tarjeta, no se pierde nada), pero habrá que probarlo en el iPad.
2. **La geometría sola puede servir poco.** No sé en qué proporción de tus desarrollos coinciden renglones y pasos; se verá al probar. Si es baja, la etapa 1 mostrará casi siempre la insignia única y el valor real llegará con la etapa 2.
3. **El modelo puede no ubicar bien.** Es posible que la etapa 2 no pase la medición. En ese caso se queda la etapa 1 y se documenta.
4. **Más cosas dibujadas** en la hoja en cada movimiento. Son pocas figuras por página; no espero que se note, pero se mide.
5. **Seguimos construyendo sobre lo no probado.** La 2b, los gestos y la app nativa aún no pasan por el iPad ni por el modelo real.

## Cómo sabremos que está hecho

- **Etapa 1:** revisas un desarrollo de un paso por renglón y ves las marcas junto a cada uno; tocas la ✕ y sale la tarjeta; mueves el desarrollo con el lazo y las marcas lo siguen; corriges un paso y la marca cambia; un desarrollo que no se puede ubicar muestra la insignia y **ninguna** marca mal puesta. Pruebas en verde.
- **Etapa 2:** hay una corrida de `app.eval` antes y otra después, guardadas en el repositorio, y la de después no lee peor.

## Decisiones que te tocan

1. **¿Apruebas la opción C en dos etapas?**
2. **¿Empiezo la etapa 1 ya**, o prefieres primero probar en el iPad lo que hay? Mi recomendación: primero el iPad. Lo acumulado sin probar ya es mucho.
3. **¿Con qué se toca una marca:** dedo, lápiz o los dos? Propongo los dos; con el lápiz, un toque sobre la marca no deja punto de tinta.
4. **¿Insignia única cuando no se sabe dónde va cada paso?** La alternativa, repartir las marcas «a ojo», arriesga un ✕ en el renglón equivocado y no la recomiendo.
5. **¿Las marcas salen en el PDF?** Propongo que no.
6. **Para la etapa 2 hace falta el banco de pruebas:** unas 10 revisiones tuyas convertidas con `app.case` y confirmadas. ¿Cuándo podrías hacerlas?
