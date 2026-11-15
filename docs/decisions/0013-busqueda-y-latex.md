# ADR 0013 — Búsqueda de texto y exportar una revisión a LaTeX

**Fecha:** 2026-11-15
**Estado:** aceptado; construido. Ninguna de las dos llama al modelo.

## Contexto

Entregas 4c y 4d de la Fase 4 ([plan](../plan-fase4.md)). El SPEC §7 pide `GET /api/search?q=` con SQLite FTS5 sobre transcripciones, soluciones y chats; el §6.7, exportar una revisión (transcripción y solución) a LaTeX para reportes.

## Búsqueda

**El índice lo mantiene el código, no la base.** Lo que dice una revisión vive en columnas JSON, así que no hay disparadores que valgan: cada ruta que cambia una revisión llama a `reindex` antes de confirmar (`app/search.py`). Una fila por revisión y por clase de texto (`steps`, `hint`, `explanation`, `solution`, `chat`), para que el resultado diga **dónde** se encontró.

**Las revisiones anteriores al índice se indexan al arrancar** (`index_if_empty`), una sola vez.

**Lo que se escribe se busca como palabras, nunca como sintaxis.** Cada palabra va entre comillas y como prefijo; deben aparecer todas. Los signos se descartan: `\frac{1}{s}` busca «frac», «1» y «s». Así nada de lo tecleado puede leerse como un operador de FTS5 ni romper la consulta.

**Los acentos dan igual** (`remove_diacritics 2`): en el teclado del iPad son lo primero que se pierde.

**El pasaje llega en trozos marcados**, no con HTML: la libreta pinta cada trozo como texto y resalta los que coincidieron. Lo que escribió el modelo no puede inyectar marcado.

**Abrir un resultado.** Si la revisión está en este iPad, se abre su cuaderno en la página donde se escribió, con el panel de la revisión abierto. Si no (se hizo en otro dispositivo o en la app nativa, que es otro almacén), se lee del backend (`GET /api/checks/{id}`) y se muestra ahí mismo, solo para leer.

**Solo busca en lo revisado.** La tinta sin revisar no tiene texto: reconocerla toda costaría una llamada al modelo por página. La pantalla lo dice.

**Necesita conexión.** El índice vive en el backend; sin conexión la pantalla lo dice.

## Exportar a LaTeX

**Se arma en la libreta, con la copia de la revisión que ya está en el iPad** (`frontend/src/export/latex.ts`): funciona sin conexión y no cuesta.

**El documento dice qué está comprobado y qué es del modelo.** Cada paso lleva el veredicto del verificador; la explicación se titula «del modelo»; la solución, «verificada simbólicamente» o «del modelo, no verificada»; el paso corregido dice si se comprobó. Es la misma separación del panel (SPEC §9.4), ahora en papel.

**El texto se escapa; las fórmulas no.** Lo que dice el verificador es texto y puede traer `%`, `_` o `*`; se escapa para que compile. Lo que el tutor escribió entre `$...$` ya es LaTeX y se deja igual.

**Fuera:** el chat (es conversación, no resultado) y la imagen de la hoja. El archivo no se ha compilado en esta sesión: no hay LaTeX instalado aquí; las pruebas revisan la estructura y el escapado.

## Rutas

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/search?q=` | Revisiones que contienen todas las palabras, la mejor primero |
| GET | `/api/checks/{id}` | Una revisión tal como está, sin costo |
