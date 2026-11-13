# Formato de trazos — versión 1

Los trazos son el dato más valioso de la app (SPEC §12.1): se guardan como vectores para poder exportarlos, redibujarlos a cualquier tamaño y volver a reconocerlos con modelos futuros. Este documento describe exactamente qué se guarda. El tipo en código es `Stroke`, en [`frontend/src/strokes/format.ts`](../frontend/src/strokes/format.ts).

## Un trazo

```json
{
  "format_version": 1,
  "id": "3f0c…",
  "page_id": "a81b…",
  "tool": "pen",
  "color": "#111111",
  "size": 1.8,
  "points": [[173.07, 110.36, 0.6], [174.2, 110.9, 0.62]],
  "created_at": 1794535667614
}
```

| Campo | Significado |
|---|---|
| `format_version` | Versión de este formato. Hoy siempre `1`. |
| `id` | UUID del trazo. |
| `page_id` | UUID de la página a la que pertenece. |
| `tool` | `"pen"` o `"highlighter"`. |
| `color` | Color CSS en hexadecimal. |
| `size` | Diámetro nominal del trazo, en unidades de página. |
| `points` | Lista de `[x, y, presión]` en el orden en que se escribieron. |
| `created_at` | Milisegundos desde 1970 (UTC). También define el orden de dibujo dentro de la página. |

## Unidades

- **Página:** tamaño carta, 612 × 792 unidades. Una unidad es un **punto tipográfico** (1/72 de pulgada), la misma unidad que usa PDF. Por eso exportar a PDF no necesita conversión.
- **Origen:** esquina superior izquierda; `x` crece a la derecha, `y` hacia abajo.
- **Presión:** de 0 a 1. Con ratón o lápiz sin sensor vale `0.5`.

Las coordenadas no dependen del zoom ni de la pantalla donde se escribió.

## Cómo se dibuja

`points` es la línea central. El contorno visible se calcula con `perfect-freehand` (parámetros en [`frontend/src/strokes/outline.ts`](../frontend/src/strokes/outline.ts)) y se rellena con `color`. El contorno **no** se guarda: si algún día cambia el algoritmo de dibujo, los datos siguen siendo válidos.

## Dónde vive

En el iPad, en IndexedDB (base `paso`, tabla `strokes`), **un registro por trazo**. Así el autoguardado escribe solo el trazo nuevo.

## Formas

Una recta, una flecha, un círculo, un triángulo o un rectángulo hechos «por pausa» se guardan como un trazo común: sus `points` recorren la figura con presión `0.5`. No existe un tipo de forma en el formato.

## Exportación de un cuaderno (`.paso.json`)

El respaldo de un cuaderno es un solo archivo JSON. Tipo en código: `NotebookExport`, en [`frontend/src/export/notebook.ts`](../frontend/src/export/notebook.ts).

```json
{
  "format": "paso-notebook",
  "format_version": 1,
  "exported_at": "2026-11-12T20:40:00.000Z",
  "subject": { "name": "Dinámica", "slug": "dinamica", "template": "generic", "tags": [] },
  "notebook": { "id": "…", "subject_id": "…", "title": "General", "position": 0 },
  "pages": [
    {
      "page": { "id": "…", "notebook_id": "…", "position": 0, "background": "grid" },
      "strokes": [ { "format_version": 1, "…": "un trazo, como arriba" } ]
    }
  ]
}
```

- `pages` va en el orden del cuaderno; `strokes`, en orden de dibujo.
- `background` es `"grid"` (cuadrícula de 5 mm), `"ruled"` (rayado de 8 mm) o `"blank"`.
- `format_version` del archivo y el de cada trazo son independientes.

**Importar** (desde 2026-11-13): en la biblioteca, cada materia tiene «Importar cuaderno desde un respaldo». El archivo entra como un cuaderno **nuevo**: todos los identificadores se generan de nuevo, así que nunca pisa nada, e importar dos veces el mismo archivo da dos cuadernos. Se valida completo antes de escribir: un archivo dañado no deja nada a medias. El orden de `pages` en el archivo es el orden del cuaderno.

## Cambios al formato

Cualquier cambio sube `format_version`, agrega una migración de Dexie en [`frontend/src/db.ts`](../frontend/src/db.ts) y se documenta aquí con su fecha.
