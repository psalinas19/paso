# La app nativa para iPad (envoltorio con Capacitor)

**Estado (2026-11-13):** el proyecto está preparado y **nunca se ha ejecutado en un iPad ni abierto en Xcode**. Lo que sigue es la guía para el día que tengas la Mac. Los pasos dentro de Xcode están escritos de memoria, no comprobados en esta sesión: si un menú se llama distinto, busca el nombre parecido.

## Qué es

La misma libreta web metida en una cáscara nativa. No es una reescritura: el código de `frontend/src/` es el mismo. La cáscara agrega una sola cosa por ahora:

- **El doble toque del Apple Pencil** activa el borrador de un solo uso. Otro doble toque regresa a la pluma. Si en Ajustes → Apple Pencil el doble toque está en «Desactivado», la app lo respeta y no hace nada.

Lo que **no** cambia: la latencia del trazo es la misma que en Safari, y la revisión con IA usa el mismo backend.

## Lo que debes saber antes

- **Con cuenta de Apple gratuita la app caduca a los 7 días.** Después no abre hasta volver a instalarla desde Xcode con el iPad conectado. Por eso la PWA sigue siendo tu libreta de diario; esta es para probar el doble toque.
- **La app nativa empieza vacía.** Sus notas son un almacén aparte del de la PWA. Para pasar un cuaderno: en la PWA, **⋯ → Exportar… → JSON**; en la nativa, biblioteca → *Importar cuaderno desde un respaldo*.
- **No guardes notas solo ahí.** Mientras no se pruebe qué pasa con los datos al caducar y reinstalar, trata la app nativa como desechable.
- **Xcode pide una Mac reciente.** Capacitor 8 necesita Xcode 26, y Xcode 26 solo se instala en versiones nuevas de macOS. Si la Mac de tu papá es antigua, puede que no se pueda. Compruébalo primero: en la Mac, abre la App Store, busca Xcode y mira si deja instalarlo.

## Qué hay en el repositorio

| Archivo | Para qué |
|---|---|
| `frontend/capacitor.config.ts` | Nombre de la app e identificador (`app.paso.libreta`). |
| `frontend/ios/` | El proyecto de Xcode. Se versiona. |
| `frontend/ios/App/App/PencilPlugin.swift` | Escucha el doble toque y lo avisa a la web. |
| `frontend/src/native/pencil.ts` | Lado web: qué hace el doble toque. Fuera de la app nativa no hace nada. |
| `.github/workflows/ios-build.yml` | Compila el proyecto en una Mac de GitHub, sin firmar, en cada cambio. Solo dice si arma. |

## El día de la Mac

### 1. Preparar la Mac (una vez)

1. Instala **Xcode** desde la App Store (pesa varios GB; ábrelo una vez y acepta lo que pida instalar).
2. Instala **Node 22** desde nodejs.org.
3. Descarga el proyecto. En la app Terminal:

```bash
git clone https://github.com/psalinas19/paso.git
```

```bash
cd paso && git switch phase-2 && cd frontend
```

```bash
npm ci
```

### 2. Armar y abrir en Xcode (cada vez que haya cambios)

```bash
npm run build && npx cap sync ios
```

```bash
npx cap open ios
```

### 3. Firmar con tu cuenta (una vez)

1. En Xcode: menú **Xcode → Settings → Accounts**, botón **+**, agrega tu cuenta de Apple.
2. En la columna izquierda, clic en **App** (el ícono azul de arriba) → pestaña **Signing & Capabilities**.
3. Marca **Automatically manage signing** y en **Team** elige tu nombre («Personal Team»).
4. Si marca error en **Bundle Identifier**, cámbialo por algo tuyo y único, por ejemplo `mx.tunombre.paso`.

### 4. Preparar el iPad (una vez)

1. Conecta el iPad a la Mac con cable y toca **Confiar**.
2. En el iPad: **Ajustes → Privacidad y seguridad → Modo de desarrollador**, actívalo. El iPad se reinicia y pide confirmar.

### 5. Instalar

1. Arriba en Xcode, junto al botón ▶, elige tu iPad.
2. Pulsa ▶. La primera vez tarda unos minutos.
3. Si el iPad dice que el desarrollador no es de confianza: **Ajustes → General → VPN y gestión de dispositivos**, toca tu cuenta y **Confiar**. Vuelve a pulsar ▶.

### 6. Probar

- Escribe algo y haz **doble toque** en el Pencil: debe activarse el borrador (se marca en la barra). Borra un trazo: vuelve la pluma sola.
- Importa un cuaderno de respaldo y revisa que se vea igual.
- Para **Revisar**: en `backend\.env` de tu laptop, la línea `ALLOWED_ORIGINS` debe incluir `capacitor://localhost` (si copiaste el `.env` antes de este cambio, no lo tiene; agrégalo al final, separado por coma, y reinicia el backend). Luego pega la dirección del túnel y el token en los ajustes de la app, igual que en la PWA.

### 7. Cada semana

A los 7 días la app deja de abrir. Conecta el iPad a la Mac, abre el proyecto y pulsa ▶ otra vez. **Antes de hacerlo la primera vez, deja un cuaderno de prueba dentro** y comprueba si sigue ahí después: eso todavía no lo sabemos.

## Si algo falla

- **El doble toque no hace nada.** Revisa Ajustes → Apple Pencil (que no esté en «Desactivado») y que el Pencil sea de 2.ª generación o Pro. Si aun así no, en Xcode mira el panel de abajo (la consola) al hacer el doble toque y copia lo que salga.
- **No compila.** Copia el primer error en rojo. La compilación de GitHub (pestaña *Actions* del repositorio) sirve de referencia: si ahí pasa y en la Mac no, el problema es de la Mac o de la firma, no del código.
- **La app abre en blanco.** Faltó `npm run build && npx cap sync ios` antes de abrir Xcode.

## Pendiente (no construido)

- Copia automática de los cuadernos a la carpeta Documentos de la app, que iOS no borra y entra al respaldo de iCloud.
- El apretón del Pencil Pro.
- Cualquier mejora de latencia: exigiría dibujar con herramientas nativas, que es reescribir el lienzo.
