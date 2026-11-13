import { useEffect, useRef, useState } from "react";
import { loadPages, loadStrokes, type Page } from "../db";
import { outlinePoints, svgPath } from "../strokes/outline";
import { BACKGROUND_COLOR, backgroundLines, PAGE_H, PAGE_W } from "./view";

const THUMB_W = 132; // CSS px

/** One page drawn small, from its strokes. Drawn only once it scrolls into view. */
export function Thumbnail({ page, width = THUMB_W }: { page: Page; width?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current!;
    let cancelled = false;
    const draw = async () => {
      const strokes = await loadStrokes(page.id);
      if (cancelled) return;
      const dpr = window.devicePixelRatio || 1;
      const scale = (width / PAGE_W) * dpr;
      canvas.width = Math.round(PAGE_W * scale);
      canvas.height = Math.round(PAGE_H * scale);
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.beginPath();
      for (const [x1, y1, x2, y2] of backgroundLines(page.background)) {
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
      }
      ctx.strokeStyle = BACKGROUND_COLOR;
      ctx.lineWidth = 0.5;
      ctx.stroke();
      for (const stroke of strokes) {
        const highlighter = stroke.tool === "highlighter";
        ctx.globalAlpha = highlighter ? 0.35 : 1;
        ctx.fillStyle = stroke.color;
        // Thin handwriting vanishes at this size: draw it a little heavier than it is.
        ctx.fill(new Path2D(svgPath(outlinePoints(stroke.points, Math.max(stroke.size, 3), true, highlighter ? 0 : 0.3))));
      }
      ctx.globalAlpha = 1;
    };
    // A long notebook has dozens of pages: read and draw only the ones looked at.
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      observer.disconnect();
      void draw();
    });
    observer.observe(canvas);
    return () => {
      cancelled = true;
      observer.disconnect();
    };
  }, [page.id, page.background, width]);
  return <canvas ref={ref} style={{ width, height: (width * PAGE_H) / PAGE_W }} />;
}

/** Side panel with every page of the notebook small: tap one to go there. */
export function PagesPanel({ notebookId, current, onGo, onClose }: {
  notebookId: string;
  current: number;
  onGo: (index: number) => void;
  onClose: () => void;
}) {
  const [pages, setPages] = useState<Page[]>([]);
  const here = useRef<HTMLLIElement>(null);
  useEffect(() => {
    void loadPages(notebookId).then(setPages);
  }, [notebookId]);
  // Open on the page you are on, not at the top of a long notebook.
  useEffect(() => {
    // In braces on purpose: newer browsers return a promise from scrollIntoView,
    // and an effect that returns anything but a clean-up function crashes on unmount.
    here.current?.scrollIntoView({ block: "center" });
  }, [pages]);
  return (
    <aside className="pages" aria-label="Páginas">
      <header>
        <h2>Páginas</h2>
        <button type="button" className="quiet" onClick={onClose} aria-label="Cerrar páginas">✕</button>
      </header>
      <ol>
        {pages.map((page, index) => (
          <li key={page.id} ref={index === current ? here : undefined}>
            <button type="button" aria-current={index === current ? "page" : undefined} onClick={() => onGo(index)}>
              <Thumbnail page={page} />
              <span>{index + 1}</span>
            </button>
          </li>
        ))}
      </ol>
    </aside>
  );
}
