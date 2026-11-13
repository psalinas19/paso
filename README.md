# Paso

Libreta inteligente para iPad que revisa, corrige y explica desarrollos de ingeniería escritos a mano.

El spec completo está en [docs/SPEC.md](docs/SPEC.md). Las decisiones de diseño, en [docs/decisions/](docs/decisions/).

**Estado: Fase 2 en curso** — la libreta ya puede pedirle una revisión al backend, corregir un paso mal leído y pedir una pista (esto último, aún sin probar con el modelo real):

- **La libreta** (`frontend/`): PWA para iPad que funciona sin conexión. Ver [ADR 0006](docs/decisions/0006-fase1-frontend.md).
- **El revisor** (`backend/`): transcribe y verifica un desarrollo. Se usa desde la libreta por HTTP ([ADR 0007](docs/decisions/0007-fase2-api.md)) o con dos comandos de terminal ([ADR 0001](docs/decisions/0001-fase0-scope.md)).

## La libreta (frontend)

Requiere **Node 22.12 o más nuevo**. Todo se corre desde `frontend\`.

```powershell
npm install          # instalar dependencias (versiones fijas)
npm run dev          # servidor de desarrollo en http://localhost:5173
npm test             # pruebas (sin red)
npm run build        # compila a dist\
npm run preview      # sirve dist\ en http://localhost:4173, como en producción
npm run deploy       # compila y publica en Cloudflare
```

`npm run dev` no activa el modo sin conexión: el service worker solo existe en la versión compilada. Para probar eso usa `npm run preview`.

### Probar en el iPad

El iPad exige HTTPS para instalar la app y trabajar sin conexión, así que se publica en una dirección fija de Cloudflare:

**https://paso-libreta.paso-frontend.workers.dev**

1. La primera vez, inicia sesión: `npx --yes wrangler@4.161.0 login` (abre el navegador para autorizar).
2. Publica: `npm run deploy`.
3. En el iPad, abre la dirección en Safari → Compartir → **Agregar a inicio**.
4. Ábrela desde el ícono con internet una vez; después funciona en modo avión.

Solo se suben los archivos de la app. **Las notas nunca salen del iPad**: viven en el almacenamiento de Safari para esa dirección. Por eso la dirección no debe cambiar: en otra dirección la app empieza vacía.

Tras publicar una versión nueva, el iPad la descarga al abrir la app con internet y la usa a partir de la siguiente vez que la abras (ciérrala del todo desde el selector de apps).

### Gestos y atajos de la libreta

- **Deshacer:** toque corto con dos dedos. **Rehacer:** con tres. Si la mano apoyada los dispara, apágalos en **⋯ → Gestos de deshacer**.
- **Lazo:** con algo seleccionado aparecen *Duplicar* y *Borrar*. Las esquinas cambian el tamaño sin deformar; los puntos de los lados estiran en un solo sentido.
- **Formas:** traza y deja el lápiz quieto un momento: recta, flecha (un tramo con una o dos barbas en la punta), círculo, triángulo o rectángulo. Las rectas casi horizontales, verticales o a 45° quedan exactas.
- **Páginas:** **⋯ → Páginas…** muestra las miniaturas; toca una para ir a ella.
- **Garabatear para borrar** viene apagado. Se enciende en **⋯ → Garabatear para borrar**: un zigzag apretado sobre un trazo lo borra. Una raya que tacha no borra nada.
- Abajo al centro se ve en qué página vas. La barra recuerda la pluma y el grosor que dejaste.

Estos gestos están probados en computadora, **todavía no en el iPad**.

### Respaldo de las notas

En un cuaderno, botón **⋯** → *Exportar…*: eliges qué páginas van al PDF, o sacas el cuaderno completo como JSON (respaldo). Se abre la hoja de compartir de iOS; desde ahí se guarda en Archivos o Nextcloud. El formato del JSON está en [docs/stroke-format.md](docs/stroke-format.md).

Para **restaurar** un respaldo: en la biblioteca, dentro de la materia, toca *Importar cuaderno desde un respaldo (.json)…* y elige el archivo. Entra como un cuaderno nuevo; nunca pisa uno existente.

Mientras no exista el respaldo automático al servidor (Fase 5), **exportar es la única copia fuera del iPad**. Instalada en la pantalla de inicio, la app no sufre el borrado a los 7 días que Safari aplica a las páginas web; el riesgo que queda es que iOS reclame espacio si el iPad se llena (según la documentación de WebKit, consultada vía buscador el 2026-11-13). Por eso el respaldo sigue importando.

### App nativa (opcional)

Existe un proyecto para instalar la libreta como app de iPad y así recibir el **doble toque del Apple Pencil**. Necesita una Mac con Xcode y, con cuenta gratuita, hay que reinstalarla cada 7 días. Todavía no se ha probado en ningún iPad. Guía: [docs/app-nativa.md](docs/app-nativa.md).

## El revisor (backend)

Lo que sigue (requisitos, puesta en marcha, comandos, materias, costos y banco de pruebas) es todo del backend.

## Requisitos

- **Python 3.12.** Ya lo tienes en `C:\Users\pakal\AppData\Local\Programs\Python\Python312`.
- **`uv`** para las dependencias.

Ojo con un detalle de Windows: escribir `python` a secas abre la Microsoft Store, porque el alias de ejecución apunta al stub. Usa **`py -3.12`** en su lugar. Todos los comandos de abajo ya lo hacen.

### Instalar uv

```powershell
py -3.12 -m pip install uv
```

Queda en `...\Python312\Scripts\uv.exe`, que no está en el PATH. Por eso los comandos usan `py -3.12 -m uv`. Si prefieres escribir solo `uv`, agrega esa carpeta al PATH.

## Puesta en marcha

```powershell
cd backend
py -3.12 -m uv sync
Copy-Item .env.example .env
```

Abre `backend\.env` y pon tu `ANTHROPIC_API_KEY`. Ese archivo está en `.gitignore` y nunca debe subirse.

## Comandos

Todos se corren desde `backend\`.

```powershell
# Transcribir y verificar una foto
py -3.12 -m uv run python -m app.poc ..\fotos\ed-01.jpg --materia ED

# Igual, pero imprime el JSON completo (útil para armar truth.json)
py -3.12 -m uv run python -m app.poc ..\fotos\ed-01.jpg --materia ED --json

# Correr el banco de pruebas completo
py -3.12 -m uv run python -m app.eval

# Lo mismo desde la caché, sin gastar API
py -3.12 -m uv run python -m app.eval --no-llm

# Convertir una revisión hecha desde la libreta en un caso del banco de pruebas
py -3.12 -m uv run python -m app.case list
py -3.12 -m uv run python -m app.case new <revisión> --id ed-01
py -3.12 -m uv run python -m app.case confirm ed-01

# Tests (no tocan la red: el modelo va simulado)
py -3.12 -m uv run pytest

# Lint y formato
py -3.12 -m uv run ruff check .
py -3.12 -m uv run ruff format .
```

## Materias

Una materia es un archivo YAML en `backend/app/subjects/`. Agregar una **no requiere tocar código** (SPEC §12.5): copia `ed.yaml`, cámbiale el `slug`, la notación, las estrategias de verificación y la taxonomía de errores.

Hoy existen `general`, `ed` (Ecuaciones Diferenciales) y `circuitos1` (Circuitos Eléctricos I, solo DC). `general` y `ed` entienden la transformada de Laplace y su inversa.

## Costos

Cada llamada al API se registra en `backend/usage.jsonl` con tokens y costo estimado. Los precios viven en `backend/app/llm/pricing.yaml`, con la fecha en que se consultaron.

La **caché de reconocimiento** (`backend/.cache/`) guarda la transcripción de cada imagen por (imagen, versión del prompt, modelo). Mientras no cambies el prompt ni el modelo, volver a correr el eval no cuesta nada. Borrarla solo cuesta dinero, nunca datos.

## Banco de pruebas

Cómo agregar ejercicios y anotar la transcripción correcta: [backend/eval/README.md](backend/eval/README.md).

**Hoy el banco está vacío**: nada sobre la calidad de la lectura ni de la pista está medido todavía. El camino corto para llenarlo es revisar ejercicios desde la libreta y convertirlos con `app.case` (ver abajo).

## Revisar desde la libreta

La libreta le manda al backend la selección del lazo y muestra cómo se leyó y qué dice el verificador de cada paso. El backend corre en tu laptop y el iPad lo alcanza por un túnel HTTPS.

### Una sola vez

1. **Clave de Anthropic.** Créala en console.anthropic.com (necesita saldo) y pégala en `backend\.env` como `ANTHROPIC_API_KEY`.
2. **Token de la app.** Genera uno y pégalo en `backend\.env` como `APP_TOKEN`:

```powershell
py -3.12 -c "import secrets; print(secrets.token_hex(24))"
```

3. **Túnel.** Instala cloudflared:

```powershell
winget install Cloudflare.cloudflared
```

### Cada vez que quieras revisar

En una terminal, desde `backend\`:

```powershell
py -3.12 -m uv run python -m uvicorn app.api.main:app --port 8000
```

En otra terminal:

```powershell
cloudflared tunnel --url http://localhost:8000
```

El túnel imprime una dirección `https://….trycloudflare.com`. **Cambia en cada arranque.** En la libreta: **⋯ → Ajustes de revisión…**, pega esa dirección y el token, y toca *Probar conexión*.

Luego, en un cuaderno: herramienta **lazo**, encierra el desarrollo y toca **Revisar**.

### Si un paso se leyó mal

Debajo de cada paso hay un enlace **Corregir lectura**. Escribe el paso en LaTeX tal como está en tu hoja (se ve una vista previa mientras tecleas) y toca *Guardar y verificar*. El backend lo vuelve a estructurar y verifica todo el desarrollo otra vez. El paso queda marcado «Corregido por ti».

- Los pasos de **lectura dudosa** (confianza menor a 0.7) siguen resaltados en ámbar: empieza por esos.
- Si el backend no logra convertir lo que escribiste a una forma comprobable, el paso queda como **no verificable**, nunca como error.
- Cada corrección es una llamada pequeña al modelo y se suma al costo de la revisión.

### Marcas sobre la hoja

Después de revisar, junto a cada renglón aparece una marca: **✓** verde (comprobado), **✕** rojo (error, con el renglón subrayado) o **!** ámbar (no se pudo comprobar). El enunciado no lleva marca.

- **Toca una marca**, con el lápiz o con un dedo, y se abre una tarjeta con lo que se comprobó de ese paso y un botón para pedir la pista. Se cierra al volver a escribir; con *Fijar* se queda.
- Si mueves el desarrollo con el lazo, las marcas se van con él. Si borras parte de lo revisado, se ponen **grises**: hay que revisar de nuevo.
- Las marcas por renglón solo aparecen cuando la app puede distinguir sin duda qué renglón es cada paso. Si no, pone **una sola insignia** en la esquina del desarrollo, que abre la revisión completa. Es a propósito: una ✕ junto al renglón equivocado sería peor que ninguna.
- No salen en el PDF.

### Las tres ayudas

Después de revisar, el panel ofrece tres botones. Ninguno se pide solo, porque cada uno cuesta unos centavos:

- **Pista:** dónde mirar, sin dar la respuesta.
- **Explícame:** de qué tipo es el problema y por qué aplica el método, un comentario junto a cada paso (por qué está bien, o qué idea hay detrás del error), cómo debió quedar el paso que falla y qué hacer a continuación si te quedaste a medias.
- **Ver solución:** el problema resuelto paso a paso, con el porqué de cada uno.

Lo que el modelo propone como correcto se comprueba con matemáticas antes de mostrártelo:

- El paso corregido de la explicación aparece en verde si se comprobó, en ámbar si no se pudo comprobar, y **no aparece** si resultó estar mal.
- La solución lleva la insignia «Solución verificada simbólicamente» solo si todas sus fórmulas se comprobaron, partiendo de lo que tú escribiste. Si no, dice «no verificada: revísala con cuidado».

Si en la hoja solo está el enunciado, el panel lo dice («Solo veo el enunciado») en vez de decir que todo está bien.

### La pista

Cuando la lectura esté bien, toca **Pedir pista**. Aparecen dos recuadros que nunca se mezclan:

- **Comprobado con matemáticas** (verde): lo que demostró el verificador. Si encontró un error, aquí dice en qué paso.
- **Opinión del modelo (puede equivocarse)** (ámbar): el tipo de error según la lista de la materia y una pista corta, sin la respuesta.

Qué paso falla lo decide el verificador, no el modelo. Si el verificador no encontró nada, el modelo solo puede opinar sobre pasos que no se pudieron comprobar, y nunca puede señalar un paso que ya se demostró correcto. Si todo quedó comprobado, la pista no cuesta nada porque no se llama al modelo. Corregir un paso después borra la pista, porque se escribió sobre la lectura anterior.

### Llenar el banco de pruebas con tus revisiones

Cada revisión queda guardada en el backend con su imagen. Para volverla un caso de prueba, desde `backend\`:

```powershell
py -3.12 -m uv run python -m app.case list
```

```powershell
py -3.12 -m uv run python -m app.case new a1b2c3d4 --id ed-01 --topic variables-separables
```

Eso crea `backend\eval\cases\ed-01\` con la imagen y un **borrador** (`truth.draft.json`) de cómo se leyó. El borrador **no cuenta** en el banco: primero lo abres junto a la imagen, corriges lo que haga falta y luego:

```powershell
py -3.12 -m uv run python -m app.case confirm ed-01
```

`confirm` revisa que todo esté completo, te muestra qué dice hoy el verificador de cada paso y solo entonces lo mete al banco. Si corregiste pasos desde la libreta, el borrador ya trae tu versión. Detalles en [backend/eval/README.md](backend/eval/README.md).

### Preguntarle al tutor

Al final del panel de una revisión hay un chat. Sabe qué escribiste, cómo se leyó, qué dijo el verificador y qué ayuda ya viste. La respuesta aparece mientras se escribe.

- Lo que responde es del modelo y **puede equivocarse**: es lo único de la app que no se comprueba con matemáticas.
- La conversación se guarda con la revisión y se puede releer sin conexión.
- Opcional: en `backend\.env`, `ANTHROPIC_MODEL_CHAT` usa un modelo más barato solo para el chat.

### Sin conexión

Si tocas **Revisar** sin internet (o con el backend apagado), la selección se guarda en una cola y no se pierde. Cuando vuelva la conexión la app te avisa; para enviarlas, **⋯ → Revisiones en espera**. No se envían solas porque cada una cuesta.

### Si tarda mucho

Debajo del costo, el panel dice en qué se fue la espera: «Tardó 9 s: 7 s el modelo, 1 s comprobar, 1 s la conexión».

- Casi todo suele ser **el modelo**. Se le puede pedir que piense menos: en la libreta, **⋯ → Ajustes de revisión… → Velocidad de respuesta**, elige *Equilibrada* o *Rápida*. Responde antes y cuesta menos, pero puede leer o explicar peor; no está medido. *Cuidadosa* es como venía funcionando.
- Si lo que pesa es **la conexión**, es el túnel o el wifi.

### Si la app dice que hay un error y tú crees que no

Es el fallo más grave que puede tener. Mándame la revisión tal cual:

```powershell
py -3.12 -m uv run python -m app.case list
```

```powershell
py -3.12 -m uv run python -m app.case show a1b2c3d4
```

El segundo comando imprime qué se leyó y qué dijo el verificador de cada paso. No incluye la imagen.

### Lo que conviene saber

- Cada revisión cuesta dinero (centavos de dólar), y cada corrección y cada pista un poco más. El panel muestra el costo acumulado de la revisión y el gasto del mes. Al llegar a `MONTHLY_BUDGET_USD` el backend rechaza revisiones nuevas.
- La materia del cuaderno decide la notación y las comprobaciones. La plantilla genérica usa la materia `general`.
- Las revisiones se guardan en `backend\data\` (base de datos e imágenes) y también en el iPad: **⋯ → Revisiones guardadas** funciona sin conexión.
- Quien tenga la dirección del túnel **y** el token puede gastar tu clave. No compartas el token; si se filtra, cámbialo en `.env` y reinicia.

## Qué falta

De la Fase 2:

- **Probar con el modelo real.** Corregir un paso, la pista, la explicación, la solución y el comando `app.case` están construidos y probados con un modelo simulado. La conexión y la lectura ya funcionan en el iPad; el resto no se ha ejecutado contra el API de Anthropic.
- **Medir.** Llenar el banco de pruebas y sacar la línea base con `app.eval`. Sin eso no se sabe qué tan bien lee el modelo ni si la pista es buena, y no se puede ajustar ningún prompt (SPEC §12.4).
- **Entrega 2c:** la posición de cada paso y las marcas sobre la hoja.

Hay además un plan pendiente de tu aprobación sobre gestos de la libreta y la ruta a app nativa: [docs/plan-mecanicas-y-app-nativa.md](docs/plan-mecanicas-y-app-nativa.md).

**Fase 3 construida** (explicación, solución, chat y cola sin conexión), pendiente de probar con el modelo real.

Después, la Fase 4 (banco de errores, modo repaso, búsqueda en todas las notas, exportar una revisión a LaTeX, graficar) y la Fase 5 (backend en un servidor para no depender de la laptop, respaldo automático, archivar semestres), según el plan por fases de [docs/SPEC.md](docs/SPEC.md) §10.
