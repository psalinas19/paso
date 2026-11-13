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

## Cambios al formato

Cualquier cambio sube `format_version`, agrega una migración de Dexie en [`frontend/src/db.ts`](../frontend/src/db.ts) y se documenta aquí con su fecha.
