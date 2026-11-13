// Export a notebook (or some of its pages) to open formats: JSON and vector PDF.
// Both work offline: everything comes from IndexedDB and the PDF library is part
// of the precached app.
import Dexie from "dexie";
import { db, loadPages, loadStrokes, type Notebook, type Page, type Subject } from "../db";
import { BACKGROUND_COLOR, BACKGROUND_LINE_WIDTH, backgroundLines, PAGE_H, PAGE_W } from "../canvas/view";
import { STROKE_FORMAT_VERSION, type Point, type Stroke } from "../strokes/format";
import { outlinePoints, quadSegments } from "../strokes/outline";

export const EXPORT_FORMAT_VERSION = 1;

export interface ExportedPage {
  page: Page;
  strokes: Stroke[];
}

export interface NotebookExport {
  format: "paso-notebook";
  format_version: typeof EXPORT_FORMAT_VERSION;
  exported_at: string;
  subject: Pick<Subject, "name" | "slug" | "template" | "tags"> | null;
  notebook: Notebook;
  pages: ExportedPage[];
}

export async function collectNotebook(notebookId: string): Promise<NotebookExport> {
  const notebook = await db.notebooks.get(notebookId);
  if (!notebook) throw new Error("notebook not found");
  const subject = await db.subjects.get(notebook.subject_id);
  const pages = await loadPages(notebookId);
  return {
    format: "paso-notebook",
    format_version: EXPORT_FORMAT_VERSION,
    exported_at: new Date().toISOString(),
    subject: subject ? { name: subject.name, slug: subject.slug, template: subject.template, tags: subject.tags } : null,
    notebook,
    pages: await Promise.all(pages.map(async (page) => ({ page, strokes: await loadStrokes(page.id) }))),
  };
}

/** Why a file could not be imported. The message is shown to the user, in Spanish. */
export class ImportError extends Error {}

const BACKGROUNDS: Page["background"][] = ["grid", "ruled", "blank"];
const isNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function readStroke(raw: unknown, pageId: string, where: string): Stroke {
  const s = raw as Partial<Stroke> | null;
  if (!s || typeof s !== "object") throw new ImportError(`${where}: hay un trazo que no se puede leer.`);
  if (s.format_version !== STROKE_FORMAT_VERSION) {
    throw new ImportError(`${where}: los trazos son de un formato (versión ${String(s.format_version)}) que esta versión de la app no conoce.`);
  }
  const points = Array.isArray(s.points) ? s.points : [];
  const valid =
    (s.tool === "pen" || s.tool === "highlighter") && typeof s.color === "string" && isNumber(s.size) && isNumber(s.created_at) &&
    points.length > 0 && points.every((p) => Array.isArray(p) && p.length === 3 && p.every(isNumber));
  if (!valid) throw new ImportError(`${where}: hay un trazo dañado.`);
  return {
    format_version: STROKE_FORMAT_VERSION,
    id: crypto.randomUUID(),
    page_id: pageId,
    tool: s.tool!,
    color: s.color!,
    size: s.size!,
    points: points.map((p): Point => [p[0], p[1], p[2]]),
    created_at: s.created_at!,
  };
}

/**
 * Restore a `.paso.json` backup as a **new** notebook inside `subjectId`.
 *
 * Every id is minted fresh, so importing never overwrites anything: bringing
 * the same file in twice gives two notebooks. The whole file is checked before
 * the first write, and the write is one transaction: all of it lands or none.
 */
export async function importNotebook(data: unknown, subjectId: string): Promise<string> {
  const file = data as Partial<NotebookExport> | null;
  if (!file || typeof file !== "object" || file.format !== "paso-notebook") {
    throw new ImportError("Ese archivo no es un respaldo de cuaderno de Paso.");
  }
  if (file.format_version !== EXPORT_FORMAT_VERSION) {
    throw new ImportError(`El respaldo es de un formato (versión ${String(file.format_version)}) que esta versión de la app no conoce.`);
  }
  if (!Array.isArray(file.pages)) throw new ImportError("El respaldo no trae páginas.");

  const notebookId = crypto.randomUUID();
  const pages: Page[] = [];
  const strokes: Stroke[] = [];
  file.pages.forEach((entry, index) => {
    const where = `Página ${index + 1}`;
    const background = entry?.page?.background;
    if (!entry || !Array.isArray(entry.strokes) || !BACKGROUNDS.includes(background)) {
      throw new ImportError(`${where}: no se puede leer.`);
    }
    // The order of the file is the order of the notebook, whatever positions it carried.
    const page: Page = { id: crypto.randomUUID(), notebook_id: notebookId, position: index, background };
    pages.push(page);
    for (const raw of entry.strokes) strokes.push(readStroke(raw, page.id, where));
  });
  if (!pages.length) pages.push({ id: crypto.randomUUID(), notebook_id: notebookId, position: 0, background: "grid" });

  const wanted = typeof file.notebook?.title === "string" && file.notebook.title.trim() ? file.notebook.title.trim() : "Cuaderno importado";
  await db.transaction("rw", db.subjects, db.notebooks, db.pages, db.strokes, async () => {
    if (!(await db.subjects.get(subjectId))) throw new ImportError("La materia donde ibas a importar ya no existe.");
    const siblings = await db.notebooks.where("[subject_id+position]").between([subjectId, Dexie.minKey], [subjectId, Dexie.maxKey]).toArray();
    const taken = new Set(siblings.map((n) => n.title));
    let title = wanted;
    for (let n = 2; taken.has(title); n++) title = `${wanted} (importado${n > 2 ? ` ${n - 1}` : ""})`;
    const position = siblings.length ? siblings[siblings.length - 1].position + 1 : 0;
    await db.notebooks.add({ id: notebookId, subject_id: subjectId, title, position });
    await db.pages.bulkAdd(pages);
    await db.strokes.bulkAdd(strokes);
  });
  return notebookId;
}

/** Read a file the user picked and import it. */
export async function importNotebookFile(file: Blob, subjectId: string): Promise<string> {
  let data: unknown;
  try {
    data = JSON.parse(await file.text());
  } catch {
    throw new ImportError("Ese archivo no es un respaldo de cuaderno de Paso.");
  }
  return importNotebook(data, subjectId);
}

/**
 * Vector PDF: each stroke is the same filled outline the screen draws, so the
 * page looks identical and stays sharp at any zoom. Page units are PDF points,
 * so coordinates go in unchanged.
 */
export async function toPdf(pages: ExportedPage[], compress = true): Promise<Blob> {
  const { jsPDF, GState } = await import("jspdf"); // loaded on first export only
  const doc = new jsPDF({ unit: "pt", format: [PAGE_W, PAGE_H], compress });
  pages.forEach(({ page, strokes }, index) => {
    if (index) doc.addPage([PAGE_W, PAGE_H]);
    doc.setDrawColor(BACKGROUND_COLOR);
    doc.setLineWidth(BACKGROUND_LINE_WIDTH);
    for (const [x1, y1, x2, y2] of backgroundLines(page.background)) doc.line(x1, y1, x2, y2);

    for (const stroke of strokes) {
      const highlighter = stroke.tool === "highlighter";
      const curve = quadSegments(outlinePoints(stroke.points, stroke.size, true, highlighter ? 0 : 0.3));
      if (!curve) continue;
      // jsPDF takes cubic segments relative to where each one starts.
      let [x, y] = curve.start;
      const segments = curve.segments.map(([c, end]) => {
        const seg = [
          ((c[0] - x) * 2) / 3, ((c[1] - y) * 2) / 3,
          end[0] - x + ((c[0] - end[0]) * 2) / 3, end[1] - y + ((c[1] - end[1]) * 2) / 3,
          end[0] - x, end[1] - y,
        ];
        [x, y] = end;
        return seg;
      });
      doc.setGState(new GState({ opacity: highlighter ? 0.35 : 1 }));
      doc.setFillColor(stroke.color);
      doc.lines(segments, curve.start[0], curve.start[1], [1, 1], "F", true);
    }
  });
  return doc.output("blob");
}

/** Hand a file to the iOS share sheet (Files, Nextcloud...), or download it where sharing is unavailable. */
export async function shareFile(blob: Blob, filename: string) {
  const file = new File([blob], filename, { type: blob.type });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: filename });
      return;
    } catch (error) {
      if ((error as DOMException).name === "AbortError") return; // the user closed the sheet
      // Anything else (e.g. the tap "expired" while the PDF was built): fall through to a download.
    }
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export const safeName = (name: string) => name.replace(/[\/:*?"<>|]+/g, "-").trim() || "cuaderno";
