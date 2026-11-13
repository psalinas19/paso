// Export a notebook (or some of its pages) to open formats: JSON and vector PDF.
// Both work offline: everything comes from IndexedDB and the PDF library is part
// of the precached app.
import { db, loadPages, loadStrokes, type Notebook, type Page, type Subject } from "../db";
import { BACKGROUND_COLOR, BACKGROUND_LINE_WIDTH, backgroundLines, PAGE_H, PAGE_W } from "../canvas/view";
import type { Stroke } from "../strokes/format";
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
