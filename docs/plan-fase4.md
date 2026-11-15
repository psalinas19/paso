# Plan de la Fase 4: banco de errores, repaso, búsqueda, exportar y graficar

**Fecha:** 2026-11-15 · **Estado:** arrancada por indicación tuya («empieza con la fase 4»). **4a a 4d construidas** (ADR 0011, 0012 y 0013), probadas en navegador con el modelo simulado; falta 4e (graficar). Las decisiones de abajo se tomaron con mi recomendación; cualquiera se puede cambiar.

## Qué cubre

Lo que pide el SPEC en §6.6, §6.7, §6.10 y §10:

| Entrega | Qué es | Depende de |
|---|---|---|
| **4a. Banco de errores** | Guardar cada error tuyo con materia, tema y tipo; una vista «Mis errores» con conteos y lo que más se repite en el último mes. | Nada. No llama al modelo. |
| **4b. Modo repaso** | Eliges materia; la app genera de 3 a 5 ejercicios cargados hacia tus errores más frecuentes; los resuelves en la hoja y los revisas igual que siempre. Un tipo de error que resuelves bien varias veces queda como superado. Modo examen opcional: sin ayudas hasta terminar. | 4a. Prompt nuevo. |
| **4c. Búsqueda** | Buscar texto en transcripciones, soluciones y chats de todas tus revisiones. | Nada. No llama al modelo. |
| **4d. Revisión a LaTeX** | Descargar una revisión (transcripción y solución) como archivo `.tex` para reportes. | Nada. No llama al modelo. |
| **4e. Graficar** | Lazo sobre una ecuación → **Graficar** → tarjeta con la gráfica 2D, con zoom y desplazamiento. | Usa la lectura que ya existe. |

El orden es ese: el banco primero porque el repaso lo necesita, y porque es lo que más se acerca a lo que pediste al probar («que me diga dónde me equivoco, para reforzar mi aprendizaje»).

## Decisiones tomadas

1. **Un error entra al banco cuando tú lo confirmas con un toque**, no solo. El SPEC dice «cada error *confirmado*», y hay una razón de fondo: si el modelo leyó mal un renglón, el verificador marca un error que no es tuyo. Guardarlo solo llenaría el banco de errores falsos, y el repaso te pondría a practicar lo que no te falla.
2. **Un paso que el verificador comprobó como correcto no se puede guardar como error.** Uno marcado con ✕ se guarda como «comprobado»; uno que no se pudo comprobar (⚠) se puede guardar, y queda rotulado como «no comprobado».
3. **El banco vive en el backend**, con una copia en el iPad para leerlo sin conexión. Así lo comparten la app web y la app nativa (que son almacenes separados), sobrevive a que Safari borre los datos del sitio, y el repaso y la búsqueda lo tienen a la mano. Guardar o cambiar un error necesita conexión; la app lo dice.
4. **El tipo y el tema los propone el modelo solo cuando ya pediste la pista.** Guardar un error no cuesta nada: si hay pista, el tipo y el tema llegan propuestos; si no, los eliges tú de la lista de la materia. Siempre puedes cambiarlos.
5. **Los errores se agrupan por la materia como la nombraste en la biblioteca.** Dos materias creadas con la plantilla general no se mezclan.
6. **«Superado» se marca a mano en la 4a.** El repaso (4b) lo marcará solo cuando resuelvas bien ese tipo de error varias veces.

## Lo que no se puede medir todavía

- La 4b trae un **prompt nuevo** (generar ejercicios) y la 4a amplía el de la pista para que proponga también el tema. Igual que todo lo demás, solo se han probado con el modelo simulado: no hay clave del API en esta sesión y el banco de pruebas sigue vacío.
- Los ejercicios que genere el modelo pasarán por el verificador cuando traigan una respuesta: un ejercicio cuya respuesta no se pueda comprobar se mostrará sin respuesta, no con una inventada.

## Qué cambia en el código

- **Backend:** tabla `ErrorEntry` (migración nueva), rutas `/api/errors` y `/api/taxonomy/{materia}`; después `/api/review/generate`, `/api/search` y la exportación a LaTeX.
- **Frontend:** un control en cada paso con error del panel, la pantalla «Mis errores» desde la biblioteca, tabla nueva en la base del iPad (`db.version(4)`); después la pantalla de repaso, el buscador y la tarjeta de gráfica.
- **Documentación:** ADR 0011, `README.md`, `CLAUDE.md`.

## Cómo sabremos que está hecho

- **4a:** revisas un desarrollo con un error, tocas «Guardar en mi banco de errores», y aparece en «Mis errores» con su materia y tipo; cambias el tipo, lo marcas como superado, lo quitas; lo ves en modo avión. Un paso correcto no ofrece guardarse.
- **4b–4e:** los criterios del SPEC §10: «el repaso genera ejercicios según mis errores reales; una ecuación escrita a mano se grafica correctamente».

## Decisiones que te tocan (cuando quieras)

Las tres se resolvieron con la recomendación para no detener el trabajo; dime si quieres otra cosa.

1. ¿Prefieres que los errores comprobados se guarden **solos**? Se puede, con un botón «no fue mi error» para quitarlos. No lo recomiendo hasta ver cuántos errores falsos quedan con el modelo real.
2. En el repaso, ¿los ejercicios se resuelven en un **cuaderno de repaso** aparte por materia, o en una página nueva del cuaderno donde estés? Propongo el cuaderno aparte, para no ensuciar tus apuntes.
3. ¿Cuántas veces seguidas bien hacen «superado»? Propongo tres.
