# ADR 0007 — API HTTP de la Fase 2

**Fecha:** 2026-11-12
**Estado:** aceptado (entregas 2a y 2b; se amplía con 2c)

## Contexto

La Fase 2 conecta la libreta con el revisor: lazo → **Revisar** → transcripción y verificación. Hasta aquí el reconocimiento **nunca se había ejecutado contra el API real ni con letra real**: no había clave configurada y `backend/eval/cases/` estaba vacío. Los criterios de la Fase 0 seguían sin medirse.

## Decisiones

**Primero el tubo completo, luego lo fino.** La entrega 2a solo lleva una selección hasta el modelo y de vuelta. Las pistas, la edición de la transcripción y las marcas sobre la hoja esperan a ver cómo lee el modelo tinta real y a tener un banco de pruebas (2b), porque cualquier ajuste de prompt o de contrato debe medirse (SPEC §12.4).

**El banco de pruebas se arma con tinta de la app.** Lo que el modelo recibirá en producción es un PNG de trazos sobre blanco, no una foto de cuaderno. Los casos de `eval/` salen de revisiones reales guardadas por el backend.

**Los endpoints no reescriben nada.** `POST /api/check` guarda la imagen y llama a `recognize()` y `verify()` tal como lo hacen los CLIs (ADR 0001). El API solo añade lo que exige una frontera de red: token, límite de gasto, límite de tamaño y persistencia.

**Sin token no hay servicio.** Toda ruta exige `Authorization: Bearer <APP_TOKEN>`. Si `APP_TOKEN` está vacío el backend rechaza todo: un proxy abierto hacia un API de pago no debe ser el comportamiento por omisión. CORS admite solo el origen de la libreta y `localhost`.

**El límite mensual se aplica antes de gastar.** El gasto del mes se suma desde la tabla `UsageLog`; al alcanzar `MONTHLY_BUDGET_USD` la revisión se rechaza con un mensaje claro, sin llamar al modelo (SPEC §6.8).

**SQLite + SQLModel, con Alembic desde la primera tabla.** El backend migra al arrancar. Las tablas nunca se crean con `create_all` (SPEC §12.2).

**Un solo proceso verificador, precalentado.** Arrancar el subproceso de SymPy cuesta varios segundos en Windows. Medido con el modelo simulado: 4.6 s por revisión creando uno cada vez, cerca de 1 s reutilizándolo. El API mantiene uno vivo y lo protege con un candado.

**Modelo inicial: Claude Sonnet 5.5**, elegido por costo. Se compara contra otros cuando exista la línea base del banco de pruebas.

**Backend en la laptop con túnel rápido de Cloudflare** durante las pruebas. La dirección cambia en cada arranque, así que la app tiene un ajuste para pegarla. No afecta a las notas: IndexedDB depende del origen de la libreta, no del backend. El hosting definitivo es de la Fase 5.

**Las revisiones se guardan en los dos lados.** En el backend (`Check`, con la imagen y los trazos, para poder re-reconocer con modelos futuros) y en el iPad (tabla `reviews` de Dexie, versión 2) para leerlas sin conexión.

## Entrega 2b (2026-11-13)

Construida y probada **solo con el proveedor simulado**. Ninguna de estas piezas se ha ejecutado contra el API real ni en el iPad, y los dos prompts nuevos no están medidos: el banco de pruebas sigue vacío.

**De una revisión a un caso de prueba, con una persona en medio.** `python -m app.case new` copia la imagen de un `Check` y escribe su transcripción como `truth.draft.json`. El eval **ignora** los borradores y avisa cuántos hay. `app.case confirm` exige que cada error tenga su tipo de la taxonomía, que todo `sympy` se pueda leer y que las referencias entre pasos existan; enseña qué dice hoy el verificador de cada paso y solo entonces renombra a `truth.json`. Se eligió un archivo aparte, y no una marca dentro de `truth.json`, para que un borrador no pueda medirse por descuido: sin esa barrera el banco compararía al modelo con su propia lectura.

**Corregir un paso: el alumno escribe LaTeX, el modelo lo reestructura.** `POST /api/checks/{id}/steps/{step_id}` recibe el LaTeX. Convertirlo al dialecto de SymPy (ADR 0002) necesita las mismas reglas del reconocimiento (`y` es `y(x)`, `C` es `C1`, unidades fuera), así que lo hace el modelo con un prompt propio (`restructure.system.md`) que **incluye** el de reconocimiento para no duplicar el dialecto. Es una llamada solo de texto, sin imagen. Luego se verifica el desarrollo completo de nuevo.
- El texto y el id del paso los fija el backend, no el modelo; la confianza pasa a 1.0 porque el alumno acaba de confirmar la lectura.
- Si el modelo no da un `sympy` utilizable, el paso queda `unverifiable`, nunca `error`.
- Guardar el mismo texto no llama al modelo.
- Alternativa descartada: un traductor de LaTeX a SymPy hecho a mano. No conoce el dialecto ni la notación de cada materia.

**La lectura original no se pisa.** `Check.steps_json` conserva lo que leyó el modelo; las correcciones van en `corrected_steps_json` (migración 0002). La diferencia entre ambas es justo lo que el banco de pruebas necesita, y `app.case` propone la versión corregida.

**La pista se pide aparte, después de confirmar la lectura.** El SPEC §7 la ponía dentro de `POST /api/check`. Se separó en `POST /api/checks/{id}/hint` porque una pista escrita sobre un paso mal leído acusa al alumno de un error que no cometió, y porque así no se paga cuando no hace falta. La pista se guarda (`hint_json`); pedirla dos veces no cobra dos veces, y corregir un paso la borra.

**Quién decide qué (SPEC §9.4).**
- Si el verificador encontró un error, **él** dice qué paso falla. Al modelo se le informa y lo que nombre se ignora; solo redacta la pista y propone el tipo de error.
- Si no encontró ninguno, el modelo puede señalar únicamente un paso `unverifiable`, y se presenta como opinión. Si señala un paso `correct` o inexistente, se descarta todo lo que dijo.
- Si todo quedó comprobado, no se llama al modelo.
- El tipo de error se valida contra la taxonomía de la materia; un id desconocido se descarta.
- La respuesta separa `verified` (texto nuestro, armado con el resultado del verificador) de `hint` (palabras del modelo). El panel los muestra en dos recuadros con título propio.

**«Sin revelar la respuesta» es una regla del prompt, no una garantía.** No hay comprobación automática de que la pista no suelte el resultado. Juzgarlo requiere leer pistas reales.

**La pista recibe la imagen además de los pasos**, para poder opinar de diagramas y texto. Sube el costo de la llamada; si conviene se decide con el banco de pruebas.

**Un solo método privado para las tres llamadas.** `AnthropicProvider._parse` concentra la salida estructurada (ADR 0005), la caché del prompt de sistema y el manejo de `stop_reason`. `extract_steps` pasa por ahí sin cambiar lo que envía.

### Limitaciones conocidas de 2b

- Sin medir: calidad de la reestructuración y de la pista, y su costo y latencia reales.
- La corrección no ve la imagen: confía en lo que el alumno escribió.
- Solo se edita LaTeX a mano; no hay teclado matemático.
- Solo se corrige el texto de un paso. No se pueden agregar, quitar ni reordenar pasos.
- Una revisión abierta desde «Revisiones guardadas» necesita el backend encendido, con su misma base de datos, para corregir o pedir pista.
- No hay registro de errores confirmados (banco de errores, Fase 4).

## Entrega 2c, etapa 1: marcas sobre la hoja (2026-11-13)

Plan y motivos en [plan-fase2c-marcas.md](../plan-fase2c-marcas.md). Construida sin tocar al modelo; probada en navegador de escritorio, **no en el iPad**.

**Dónde está cada paso se deduce solo de la tinta, y solo cuando no hay duda.** Los trazos de la selección se agrupan en renglones por su altura (una fracción cuenta como un renglón; una letra que baja al renglón siguiente no los une). Si hay **exactamente** tantos renglones como pasos, se emparejan en orden. Con cualquier otra cuenta no se coloca ninguno: la revisión lleva **una sola insignia** en su esquina. Repartir «a ojo» pondría un ✕ junto a un renglón correcto.

**Una marca recuerda sus trazos, no una coordenada.** Se dibuja junto a la caja de sus trazos tal como están ahora: si mueves el desarrollo con el lazo, va con él; si borras el renglón, desaparece. Si se borró parte de lo revisado, las marcas que quedan se ponen grises («revisión desactualizada») en vez de fingir que el veredicto sigue describiendo la hoja.

**Los datos del enunciado no llevan marca**: nadie los comprobó. **La revisión más reciente de una misma tinta gana**; las anteriores no se dibujan.

**Las marcas son vectores en el mismo lienzo que la tinta**, así que hacen zoom nítidas y no salen en el PDF (que se arma solo con trazos).

**Tocar una marca abre una tarjeta junto a ella**, con el lápiz o con un dedo. Un toque del lápiz sobre una marca no deja tinta. La tarjeta muestra lo que comprobó el verificador y, aparte y rotulado, lo que el modelo haya dicho de ese paso (pista, comentario, corrección). Pedir la pista es un botón; nada se gasta solo. Se cierra al volver a escribir, salvo que se fije.

### Limitaciones de la etapa 1

- **No sé cuántas de tus revisiones caerán en «tantos renglones como pasos».** Si son pocas, verás casi siempre la insignia. Lo arregla la etapa 2 (que el modelo diga dónde está cada paso), que necesita el banco de pruebas.
- Las revisiones hechas antes de este cambio no guardaron sus trazos y no tienen marcas.
- La tarjeta se queda donde se abrió: no sigue a la hoja al desplazarla.
- Un toque con el dedo sobre una marca no responde durante 0.4 s después de escribir (es el rechazo de palma).
- El «Ver explicación completa» del SPEC abre el panel de la revisión; no hay chat todavía.

## Limitaciones conocidas de 2a

- ~~No hay pista ni clasificación del error.~~ Resuelto en 2b.
- ~~La transcripción no se puede corregir.~~ Resuelto en 2b.
- Solo se revisa una selección de lazo, no la página entera.
- Sin conexión, Revisar avisa y no hace nada; la cola es de la Fase 3.
- No hay respaldo alterno de modelo si este declina una imagen: se muestra el error.
- El registro `usage.jsonl` de los CLIs y la tabla `UsageLog` del API conviven; el límite mensual usa solo la tabla.
