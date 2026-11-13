# SPEC — "Paso" (nombre provisional)
Libreta inteligente para iPad que revisa, corrige y explica desarrollos de ingeniería escritos a mano.

> **Instrucciones para Claude Code:** lee este documento completo antes de escribir código. Trabaja **una fase a la vez** (sección 10). Al iniciar cada fase, presenta un plan y espera mi aprobación. Al terminarla, detente y dame instrucciones concretas para probarla en mi iPad. No agregues funciones fuera del alcance (sección 3) sin preguntarme.

---

## 1. Contexto

- **Usuario:** un solo usuario (yo). Estudiante de Ingeniería en Automatización y Control (UAQ), con experiencia en Python, C++, Django/DRF y PLCs.
- **Dispositivos:** iPad con Apple Pencil para escribir; laptop Windows (Lenovo P15) para desarrollar. **No tengo Mac.**
- **Horizonte:** la app se usará **durante toda la carrera** (varios años y semestres). Ver sección 12; las decisiones de diseño deben respetarla.
- **Sin internet en clase:** en la universidad muchas veces no hay conexión. Escribir y consultar notas (y revisiones ya hechas) funciona **100% offline**; la IA solo se usa cuando hay internet (6.9).
- **Referencia:** la app Derive. Se toma lo esencial de sus flujos (lápiz, presentación de correcciones); no se copia marca, nombre, logos ni assets.
- **Materias iniciales:** Ecuaciones Diferenciales, Circuitos Eléctricos I (notación de Hayt), Dinámica y Métodos Numéricos. Cada semestre se agregarán materias nuevas **sin tocar código**.
- **Materias previstas en la carrera** (el tutor debe poder con material avanzado, no solo álgebra):
  - Matemáticas: cálculo multivariable, Laplace y Z, álgebra lineal, series de Fourier.
  - Control: funciones de transferencia, diagramas de bloques, lugar de las raíces, Bode y Nyquist, espacio de estados, PID, control digital.
  - Circuitos y electrónica: nodal y mallas, RLC, fasores, amplificadores operacionales, electrónica de potencia.
  - Mecánica: estática, dinámica, cuerpo libre, vibraciones, modelado mecánico y electromecánico.
  - Automatización: escalera, diagramas de estados, GRAFCET, neumática e hidráulica, sensores y actuadores.
- **Objetivo:** escribir a mano como en un cuaderno, seleccionar un desarrollo y obtener tres cosas:
  1. En qué paso me equivoqué y por qué.
  2. La solución correcta explicada.
  3. Un chat para preguntar sobre ese ejercicio.
- **Objetivo secundario:** registrar mis errores para detectar patrones y repasar antes de los parciales.

## 2. Flujo principal

1. Abro la app en el iPad, elijo materia y cuaderno, y escribo con el Pencil.
2. Encierro con el lazo un desarrollo y toco **Revisar**.
3. La app muestra la **transcripción** en LaTeX renderizado, paso por paso, para que confirme que leyó bien. Puedo corregir un paso si lo leyó mal.
4. El verificador simbólico marca cada paso con uno de tres estados:
   - ✅ **correcto**
   - ❌ **error**
   - ⚠️ **no verificable:** no se pudo comprobar simbólicamente y solo lo revisó el modelo.
5. **Niveles de ayuda.** El panel lateral muestra el nivel 1 primero y los siguientes están a un toque:
   - **Nivel 1, Pista:** qué paso falla y una pista, sin dar la respuesta.
   - **Nivel 2, Paso corregido:** cómo debió quedar ese paso y por qué.
   - **Nivel 3, Solución completa:** desarrollo completo explicado paso a paso, con el porqué de cada decisión (qué método, qué regla y por qué aplica).
6. En cualquier nivel puedo abrir el **chat** de ese ejercicio y preguntar. El chat conoce:
   - la imagen,
   - la transcripción,
   - los resultados de verificación,
   - la materia,
   - el historial de esa conversación.
7. Cada error confirmado se guarda en el **banco de errores**.

## 3. Alcance

**Dentro (v1):**
- Canvas de escritura.
- Organización semestre → materia → cuaderno, con archivo de semestres pasados.
- Búsqueda en todas mis notas y revisiones de la carrera.
- Revisar con los niveles 1 a 3.
- Chat por ejercicio.
- Verificación simbólica.
- Banco de errores.
- Modo repaso.
- Exportar a PDF y LaTeX.
- Graficar ecuaciones escritas a mano (2D primero).
- Respaldo en el servidor y exportación JSON + PDF para guardar en Nextcloud.
- Límite de gasto de API.
- Uso offline: notas e historial de revisiones sin conexión, y cola de revisiones pendientes.

**Fuera (no implementar):**
- App nativa.
- Sincronización multiplataforma o multi-dispositivo.
- Cuentas o multiusuario, y colaboración.
- Revisión en vivo trazo por trazo.
- Verificación simbólica de diagramas (circuitos, bloques, DCL, Bode, escalera). El modelo **sí debe leerlos y revisarlos** (convenciones, signos, modelado), pero su juicio queda como `no verificable`.
- Grabación de audio.
- Importar PDFs.

## 4. Stack y restricciones

- **Frontend:** PWA con React + Vite + TypeScript. Se usa en Safari de iPadOS, instalada en la pantalla de inicio.
  - Tinta: Pointer Events (`pointerType === "pen"`, `pressure`) y `perfect-freehand` para el trazo. Usa `getCoalescedEvents` y `getPredictedEvents` si están disponibles.
  - Almacenamiento local: IndexedDB con Dexie.
  - Offline: service worker que cachea toda la app (app shell).
  - Render de matemáticas: KaTeX. Render del chat: Markdown.
  - Exportar a PDF: jsPDF.
- **Backend:** Python 3.12 con FastAPI.
  - Datos: SQLite con SQLModel.
  - Matemáticas: SymPy y NumPy.
  - IA: SDK oficial `anthropic`.
  - Respuestas del chat: streaming por SSE.
- **Modelo:** configurable por variable de entorno `ANTHROPIC_MODEL`, con valor por defecto `claude-sonnet-5`. Usa visión para leer la imagen y salida JSON estructurada (tool use) para la transcripción. **Consulta la documentación actual de Anthropic para el uso del SDK en lugar de depender de memoria.**
  - Las revisiones usan el modelo más capaz que el eval justifique (12.4). `ANTHROPIC_MODEL_CHAT` (opcional) permite un modelo más barato para dudas simples del chat; si no se define, se usa `ANTHROPIC_MODEL`.
- **Desarrollo en Windows:**
  - El README debe explicar cómo correr todo en Windows.
  - Para probar en el iPad hace falta HTTPS, porque la PWA y el service worker lo requieren. Usa un túnel (p. ej. `cloudflared`) y documéntalo.
- **Secretos:** van en `.env`, nunca en el repo. Incluye un `.env.example`.
- **Idioma:**
  - Interfaz, explicaciones y chat en **español**.
  - Código, nombres de variables y commits en inglés.

## 5. Arquitectura

```
iPad (PWA)                                   Backend (FastAPI)
┌──────────────────────────┐   HTTPS/JSON   ┌───────────────────────────────┐
│ Canvas + lazo            │ ─────────────▶ │ /recognize → Claude (visión)  │
│ IndexedDB (fuente local) │                │ /verify    → SymPy verifier   │
│ Panel Revisar / Niveles  │ ◀───────────── │ /solve     → Claude + SymPy   │
│ Chat (SSE)               │ ◀── stream ─── │ /chat      → Claude (stream)  │
│ Banco de errores / Repaso│                │ SQLite: checks, chats, errores│
└──────────────────────────┘                │ uso de tokens, respaldos      │
                                            └───────────────────────────────┘
```

- **Semestre en curso:** vive en IndexedDB en el iPad para que escribir sea rápido. Se sube al servidor automáticamente en segundo plano (solo subida, sin resolución de conflictos, porque solo hay un dispositivo).
- **Fuente de verdad a largo plazo:** el servidor. Safari puede borrar almacenamiento local y el iPad tiene espacio limitado, así que el iPad no se trata como almacén permanente.
  - Pedir `navigator.storage.persist()` al iniciar la app.
  - Al archivar un semestre, sus cuadernos salen del iPad y se descargan bajo demanda (solo lectura por defecto).
- **Revisiones, chats, banco de errores y registro de uso:** viven en el backend (SQLite). El iPad guarda en IndexedDB una copia de las revisiones y chats del semestre en curso para consultarlos sin conexión.
- **La API key nunca vive en el iPad** ni aparece en el código del frontend; el backend es el único que habla con Anthropic.

## 6. Módulos

### 6.1 Canvas
- **Páginas:** tamaño carta con fondo cuadriculado (opciones: cuadrícula, rayado, blanco) y scroll vertical. Las páginas crecen solas hacia abajo: en cuanto la última tiene algo escrito, aparece otra en blanco después; no hay botón de «agregar página». Cuadernos y páginas se pueden crear, renombrar, borrar y reordenar.
- **Entrada por tipo:**
  - El Pencil dibuja.
  - Un dedo hace scroll y dos dedos hacen zoom.
  - Rechazo de palma: ignorar el toque mientras el Pencil está activo.
- **Herramientas:** en una barra flotante centrada arriba, con plumas preconfiguradas que muestran su color (un toque cambia de pluma, sin abrir menús).
  - Pluma con 3 grosores y 4 colores.
  - Resaltador.
  - Borrador por trazo. Modo de **un solo uso**: se activa, borra y al levantar el lápiz vuelve sola la pluma anterior.
    - El doble toque del Apple Pencil **no llega a las páginas web** (Safari no lo expone; solo las apps nativas lo reciben), así que el borrador se activa desde la pantalla: con su botón o con un **doble toque de un dedo** sobre la hoja (otro doble toque regresa a la pluma). Si algún día hay app nativa (12.8), el doble toque se conecta a este mismo modo.
  - **Formas por pausa:** si trazo una línea y mantengo el lápiz quieto sin levantarlo, el trazo se endereza en una recta perfecta; mientras sigo sin levantar, puedo mover el extremo para alargarla o girarla. Lo mismo para círculo, triángulo y rectángulo. Una forma ya hecha se mueve y se estira con el lazo.
  - Lazo para seleccionar, mover o borrar.
  - Deshacer/rehacer.
- **Ajustes de Safari:** `touch-action: none` en el canvas y desactivar la selección de texto y el menú contextual de iOS.
- **Guardado:** los trazos se guardan como vectores (puntos + presión) y hay autoguardado.
- **Nitidez:** la tinta se dibuja siempre como vectores a la resolución real de la pantalla, a cualquier zoom. Nunca queda como una imagen estirada más allá de lo que dura un gesto.
- **Rendimiento:** el trazo debe sentirse inmediato. Meta: sin retraso perceptible ni saltos, y renderizado incremental (no redibujar toda la página por trazo).
- **Revisar:** exporta la región seleccionada (o la página completa si no hay selección) como PNG con fondo blanco, a la resolución mínima que siga siendo legible, para ahorrar tokens.

### 6.2 Reconocimiento (`/recognize`)
- **Entrada:** imagen de la selección y materia.
- **Salida:** JSON con una lista de pasos. Cada paso incluye:
  - `latex`
  - `sympy` (expresión parseable, o `null`)
  - `kind` (`expression` | `equation` | `system` | `ode` | `numeric_iteration` | `text` | `diagram`)
  - `confidence` (0–1)
  - `notes`
- **Baja confianza:** si algún paso tiene `confidence < 0.7`, la UI lo resalta y pide confirmación antes de verificar.
- **Regla:** el modelo **nunca** inventa pasos que no ve. Si algo es ilegible, lo marca como ilegible.

### 6.3 Verificador simbólico (`/verify`)
Implementarlo como un **registro de estrategias**: una clase por `kind` con una interfaz común, para agregar tipos en semestres futuros sin tocar las existentes. Tipos futuros previstos: transformada de Laplace, funciones de transferencia, matrices y espacio de estados, fasores, Fourier/Z. Cada materia declara en su configuración qué estrategias usa.

Compara cada paso con el anterior según su `kind`:

| kind | Criterio de equivalencia |
|---|---|
| `expression` | `simplify(a - b) == 0`; si no concluye, evaluación numérica en ~10 puntos aleatorios |
| `equation` | mismo conjunto solución, o `(lhs - rhs)` proporcional por un factor no nulo |
| `system` | `linsolve`/`solve` dan la misma solución (análisis nodal y de mallas) |
| `ode` | `checkodesol` para soluciones propuestas; separación de variables, factor integrante, etc. se verifican por equivalencia |
| derivadas/integrales | comprobar con `diff` |
| `numeric_iteration` | recalcular la iteración (Newton-Raphson, bisección, punto fijo, etc.) y comparar con tolerancia |
| `text` / `diagram` / sin `sympy` | estado `no_verificable`; solo lo evalúa el modelo |

- **Salida por paso:** `status` (`correct` | `error` | `unverifiable`), `detail` y `method_used`.
- **Timeout** por paso: si SymPy tarda demasiado, el paso queda `unverifiable`.
- **Tests:** módulo con pruebas en pytest y una tabla de casos reales **correctos e incorrectos** de cada materia. Incluye errores típicos: signo, regla de la cadena, constante de integración, ley de Kirchhoff mal aplicada, iteración mal calculada.

### 6.4 Tutor: niveles 1–3 y solución (`/check`, `/solve`)
- **`/check`:** usa la transcripción y la verificación para generar la pista (nivel 1).
- **Nivel 2:** da el paso corregido y la explicación del error.
- **Presentación sobre la hoja** (tomada del análisis de Derive):
  - Cada paso revisado lleva una marca pequeña junto a su renglón: ✓ verde, ✕ rojo o ⚠️ ámbar. El paso con error se subraya en rojo.
  - Tocar una marca abre una tarjeta anclada junto al paso: tipo de error como título, la **pista** (nivel 1) y un enlace «Ver explicación completa».
  - La explicación completa (nivel 2) muestra el paso tal como se leyó, en rojo, un bloque **Por qué** y un bloque **Siguiente paso**, seguidos de 2–3 preguntas sugeridas que abren el chat con esa pregunta.
  - La tarjeta se puede fijar o cerrar. Al corregir y volver a revisar, las marcas se actualizan.
  - Para anclar marcas y tarjetas, el reconocimiento debe devolver la posición de cada paso en la imagen. Es un cambio al contrato de 6.2: se decide en el plan de la Fase 2 y se mide con `app.eval` (12.4).
- **`/solve` (nivel 3):** genera la solución completa **en formato de pasos estructurados** (mismo JSON que 6.2) más una explicación en Markdown.
  - **Toda solución generada pasa por el verificador.** La UI muestra una insignia: "Solución verificada simbólicamente" o "Solución no verificada: revísala con cuidado".
  - Si el verificador encuentra un error en la solución del modelo, se le pide que la corrija una vez; si persiste, se muestra la advertencia.
- **Contenido de la explicación:**
  - Qué tipo de problema es.
  - Qué método aplica y por qué.
  - Cada paso con su justificación.
  - Verificación final (sustituir, revisar unidades o un caso límite).

### 6.5 Chat (`/chat`, SSE)
- Hay un hilo por revisión, con historial persistente.
- **Contexto que recibe:** imagen, transcripción, resultados de verificación, niveles ya mostrados, materia y mensajes previos.
- Respuestas en streaming, con Markdown y KaTeX.
- Puedo adjuntar una nueva selección del canvas al chat.
- Usa `ANTHROPIC_MODEL_CHAT` si está definido (sección 4).

### 6.6 Banco de errores y repaso
- **Registro:** cada error confirmado se guarda con `materia`, `tema`, `tipo_error`, `fecha`, `check_id` y `resuelto`.
- **Clasificación:** el modelo propone tema y tipo usando una taxonomía por materia (archivo de configuración editable); yo puedo cambiarla.
- **Vista:** errores por materia y tipo, con conteos y los más frecuentes del último mes.
- **Modo repaso:**
  - Elijo materia; la app genera 3–5 ejercicios ponderados por mis errores más frecuentes.
  - Los resuelvo en el canvas y los reviso con el mismo flujo.
  - Si repito bien un tipo de error varias veces, se marca como superado.
- **Modo examen (opcional en el repaso):** los niveles de ayuda se bloquean hasta que termine el ejercicio.

### 6.7 Exportar
- Páginas elegidas o el cuaderno completo a PDF: un diálogo lista las páginas y parte con las que tienen algo escrito. **Siempre disponible, también sin conexión**, y debe verse bien: trazos vectoriales (nítidos al hacer zoom, no una captura de pantalla), con los mismos colores, grosores y fondo que en pantalla.
- Una revisión (transcripción + solución) a LaTeX, para reportes.

### 6.10 Graficar
- Selecciono con el lazo una ecuación escrita a mano y toco **Graficar**: la app la reconoce (6.2) y muestra la gráfica en una tarjeta junto a la ecuación, que se puede fijar o cerrar.
- **Primero 2D** (`y = f(x)`), con zoom y desplazamiento. Las superficies 3D (`z = f(x, y)`) se agregan después, solo si el 2D resulta útil en clase.
- La gráfica se calcula a partir del campo `sympy` del paso; si no se pudo parsear, la app lo dice en vez de graficar algo inventado.
- Requiere conexión para reconocer la ecuación; una gráfica ya generada se conserva con la página y se ve offline.
- Respaldo manual: cuaderno a JSON (formato de trazos documentado) + PDF, descargable desde el iPad para guardarlo en Nextcloud.

### 6.8 Control de costos
- Cada llamada al API se registra con tokens de entrada/salida y costo estimado.
- Límite mensual configurable (`MONTHLY_BUDGET_USD`): al alcanzarlo, el backend rechaza llamadas con un mensaje claro.
- La interfaz muestra el costo aproximado de cada revisión y el gasto acumulado del mes.

### 6.9 Offline
- Con el iPad en modo avión la app abre y se puede escribir, navegar cuadernos, exportar a PDF y leer revisiones y chats ya hechos.
- **Cola de revisiones:** si no hay internet, **Revisar** guarda la selección (imagen + trazos + materia) en una cola local y avisa. Al volver la conexión, la app lo indica y yo decido cuándo procesar la cola; no se envía sola, para no gastar sin que me entere.
- El chat y los niveles 2–3 requieren conexión; la interfaz lo dice en vez de fallar en silencio.

## 7. API (contrato inicial)

Todas las rutas requieren el header `Authorization: Bearer <APP_TOKEN>` (usuario único, token en `.env`).

| Método | Ruta | Propósito |
|---|---|---|
| POST | `/api/recognize` | imagen + materia → pasos |
| POST | `/api/verify` | pasos → estados por paso |
| POST | `/api/check` | recognize + verify + pista (nivel 1) en una llamada |
| POST | `/api/checks/{id}/level/2` | paso corregido |
| POST | `/api/checks/{id}/solve` | solución completa verificada (nivel 3) |
| POST | `/api/checks/{id}/chat` | mensaje → respuesta en SSE |
| GET | `/api/checks` | historial filtrable por semestre, materia y tema |
| GET/POST/PATCH | `/api/semesters`, `/api/subjects` | crear semestres y materias, archivar |
| GET | `/api/search?q=` | búsqueda de texto completo (SQLite FTS5) en transcripciones, soluciones y chats |
| GET/PATCH | `/api/errors` | banco de errores |
| POST | `/api/review/generate` | ejercicios de repaso |
| POST/GET | `/api/backup` | subir/descargar respaldo de cuadernos |
| GET | `/api/usage` | gasto del mes |

## 8. Modelo de datos (backend)

- **Semester:** `id`, `name` (p. ej. "2026-2"), `start_date`, `end_date`, `archived`
- **Subject:** `id`, `semester_id`, `name`, `slug`, `config_path` (taxonomía, estrategias, notación, bibliografía), `tags` (temas, para ligar materias entre semestres)
- **Notebook / PageBackup:** `id`, `subject_id`, `title`, `strokes_path`, `format_version`, `updated_at`
- **Check:** `id`, `subject_id`, `image_path`, `strokes_json` (trazos vectoriales de la selección), `steps_json`, `verification_json`, `max_level_shown`, `solution_json`, `model`, `prompt_version`, `created_at`
- **ChatMessage:** `id`, `check_id`, `role`, `content`, `created_at`
- **ErrorEntry:** `id`, `check_id`, `subject_id`, `tema`, `tipo_error`, `resuelto`, `created_at`
- **UsageLog:** `id`, `endpoint`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `created_at`
- **Backup:** `id`, `payload_path`, `created_at`

## 9. Reglas para los prompts del tutor

Los prompts de sistema viven en archivos separados (`backend/prompts/`) para que pueda editarlos. Deben cumplir estas reglas:

1. Responder en español, directo y sin relleno.
2. No inventar contenido que no aparece en la imagen; si algo es ilegible, decirlo.
3. En el nivel 1, **no** revelar la respuesta.
4. Separar siempre lo verificado simbólicamente de lo que es solo opinión del modelo.
5. Explicar el *porqué*: qué método aplica, qué condiciones requiere y qué error conceptual hay detrás de un error.
6. Usar la notación de la materia (Circuitos: Hayt) y unidades SI. Revisar unidades y coherencia física, no solo el álgebra: señalar errores de signo, de convención y de modelado, también en diagramas.7. Salidas estructuradas siempre en JSON válido según el esquema; LaTeX con delimitadores compatibles con KaTeX.
8. No resolver más de lo necesario a menos que yo lo pida.

## 10. Plan por fases

Cada fase termina con criterios de aceptación y **se detiene** para que yo pruebe.

**Fase 0: prueba de concepto (sin interfaz)**
- Script CLI: `python -m app.poc foto.jpg --materia ED` → imprime pasos y verificación.
- Yo aporto ~10 fotos reales de mi cuaderno (ED y Circuitos), con pasos correctos e incorrectos.
- ✅ Criterios:
  - Al menos 8 de 10 transcritas correctamente.
  - El verificador detecta los errores sembrados.
  - Los tests del verificador pasan.
- Si no se cumplen, ajustamos el reconocimiento antes de seguir.
- Estas fotos, con su transcripción correcta, se guardan como **banco de pruebas permanente** (`/eval`), con un comando `python -m app.eval` que da el porcentaje de aciertos. Se ampliará cada semestre con ejercicios de las materias nuevas.

**Fase 1: canvas y cuadernos**
- Antes de diseñar: análisis breve de Derive (flujos, interacción del lápiz, cómo presenta las correcciones) y lista de lo esencial a adoptar.
- PWA instalable y offline (service worker), estructura semestre → materia → cuaderno, herramientas de 6.1, autoguardado en IndexedDB.
- Las materias se crean desde la app con una plantilla de configuración; no se hardcodean.
- Formato de trazos documentado y versionado desde el día uno.
- Túnel HTTPS para probar en el iPad.
- Exportar página o cuaderno a PDF y a JSON (6.7).
- ✅ Criterios: se instala desde Safari y abre en modo avión, escribir se siente fluido, la palma no raya, zoom y scroll funcionan, ninguna nota se pierde al cerrar la app o reiniciar el iPad, y el PDF exportado en modo avión se ve igual que la página y sigue nítido al ampliarlo.

**Fase 2: Revisar (nivel 1)**
- Flujo lazo → transcripción editable → verificación → pista, con el backend de 6.2–6.4.
- ✅ Criterio: el flujo completo funciona desde el iPad en menos de ~15 s por revisión típica.

**Fase 3: niveles 2–3 y chat**
- Paso corregido, solución completa verificada con insignia, chat con streaming e historial.
- Cola de revisiones offline e historial de revisiones consultable sin conexión (6.9).
- ✅ Criterios: una solución errónea del modelo se detecta y se marca; una revisión pedida en modo avión se procesa al volver la conexión.

**Fase 4: banco de errores, repaso, búsqueda y exportar**
- Secciones 6.6 y 6.7, más la búsqueda de texto completo.
- Graficar en 2D (6.10).
- ✅ Criterios: el repaso genera ejercicios según mis errores reales; una ecuación escrita a mano se grafica correctamente.

**Fase 5: despliegue**
- Propón 2 opciones de hosting baratas con costo estimado y espera mi decisión.
- HTTPS, límite de gasto activo, README final.
- Respaldo automático diario de la base de datos y los archivos a un almacenamiento **externo al servidor**, con retención y un script de restauración probado.
- Flujo para archivar un semestre.
- Backend en Docker.
- ✅ Criterios:
  - Funciona desde la red de la universidad sin mi laptop encendida.
  - Puedo borrar el servidor y restaurarlo desde el respaldo.

## 11. Forma de trabajar

- Usa modo de planeación al iniciar cada fase y espera mi aprobación.
- Commits pequeños y descriptivos; un commit al cerrar cada fase.
- Escribe tests para el verificador y para los endpoints críticos.
- Si una decisión de este spec resulta mala en la práctica, avísame con la alternativa antes de cambiarla.
- Explica en español las decisiones técnicas importantes: el objetivo también es que yo aprenda. Código simple y comentado.
- Mantén un `CLAUDE.md` corto con comandos para correr, probar y hacer lint, más las decisiones tomadas.
- Estructura sugerida:
  ```
  /frontend   (React + Vite + TS, PWA)
  /backend    (FastAPI, app/, prompts/, tests/)
  /docs       (este SPEC, decisiones)
  ```

## 12. Diseño para toda la carrera

La app debe durar varios años con un solo mantenedor (yo, con ayuda de Claude Code). Reglas:

1. **Los datos son el activo principal.** El código se puede reescribir; mis notas de la carrera no.
   - Todo debe poder exportarse en formatos abiertos: trazos en JSON documentado, PDF, LaTeX y la base de datos completa.
   - Nunca guardar algo solo en un formato propietario o solo en el iPad.
2. **Migraciones desde el inicio.**
   - Backend: Alembic.
   - Frontend: versiones de Dexie con funciones de migración.
   - Cada formato guardado lleva `format_version`.
3. **Independencia del modelo.**
   - El acceso a IA vive detrás de una interfaz (`LLMProvider`) para poder cambiar de modelo o proveedor.
   - Cada revisión guarda qué modelo y qué versión de prompt la generaron.
   - Los trazos se guardan en vectores para poder **re-reconocer notas viejas** con modelos mejores.
4. **Cambios medidos, no a ojo.** Antes de cambiar de modelo o de prompt, correr `app.eval`; si baja el porcentaje de aciertos, no se cambia.
5. **Crecimiento por configuración.**
   - Cada materia es un archivo de configuración con taxonomía de errores, estrategias de verificación, notación, bibliografía y notas para el tutor.
   - Agregar una materia no requiere código. Agregar un *tipo* de verificación sí, pero como estrategia nueva en el registro (6.3).
6. **Continuidad entre materias.**
   - Los temas se etiquetan (p. ej. `laplace`, `edo-lineal`, `kirchhoff`) para que en materias futuras, como Control, el chat y el repaso puedan traer mis revisiones y errores previos del mismo tema.
   - Implementar solo el etiquetado en v1; el uso cruzado se hace cuando exista una segunda materia que lo aproveche.
7. **Stack aburrido y fijado.**
   - Versiones de dependencias fijadas y actualizaciones deliberadas (una vez por semestre, con tests y eval).
   - Registrar decisiones importantes en `/docs/decisions/` como ADRs cortos.
8. **Puerta abierta a app nativa.** La API y el formato de trazos deben ser independientes de la PWA, para que en el futuro una app nativa de iPad pueda reemplazar el frontend sin tocar el backend ni perder datos. No construir nada nativo ahora.
9. **Escala esperada:** un usuario y del orden de miles de revisiones y algunos GB de imágenes en toda la carrera. SQLite y almacenamiento en disco son suficientes; no introducir servicios adicionales (colas, bases de datos separadas, microservicios) sin una razón medida.
