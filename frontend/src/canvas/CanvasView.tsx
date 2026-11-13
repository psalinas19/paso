import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { db, type Review } from "../db";
import { ExportDialog } from "../export/ExportDialog";
import { loadConfig, postCheck, postCorrection, postExplain, postHint, postSolve, type CheckResponse } from "../review/api";
import { mergeReview, timingOf } from "../review/merge";
import { ReviewPanel, type ReviewState } from "../review/ReviewPanel";
import { SettingsDialog } from "../review/SettingsDialog";
import { deletePage, movePage } from "../library/actions";
import { NotebookCanvas, type Tool } from "./NotebookCanvas";
import { afterDoubleTap, onPencilDoubleTap } from "../native/pencil";
import { PagesPanel } from "./PagesPanel";
import { loadPrefs, savePrefs } from "./prefs";
import { PEN_COLORS, PEN_SIZES, Toolbar, type ToolKind } from "./Toolbar";

/** A notebook: the toolbar (React) on top of the drawing surface (NotebookCanvas). */
export function CanvasView({ notebookId, onError, onLibrary }: {
  notebookId: string;
  onError: (message: string) => void;
  onLibrary: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const inkRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const canvas = useRef<NotebookCanvas | null>(null);

  // The toolbar reopens the way it was left: same pen, same thickness.
  const [prefs] = useState(() => loadPrefs(PEN_COLORS.length, PEN_SIZES.length));
  const [active, setActive] = useState<ToolKind>(prefs.active);
  const [pen, setPen] = useState(prefs.pen);
  const [size, setSize] = useState(prefs.size);
  const [gestures, setGestures] = useState(prefs.gestures);
  const [scribble, setScribble] = useState(prefs.scribble);
  const [pagesOpen, setPagesOpen] = useState(false);
  const [where, setWhere] = useState({ current: 1, total: 1 });
  const [state, setState] = useState({ canUndo: false, canRedo: false, hasSelection: false });
  // Bumped after pages are reordered or deleted, to rebuild the surface from the database.
  const [revision, setRevision] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [settings, setSettings] = useState(false);
  const [panel, setPanel] = useState<ReviewState | null>(null);
  // What the one-shot eraser returns to.
  const writingTool = useRef<"pen" | "highlighter">(prefs.active);

  const tool = useMemo<Tool>(() => {
    if (active === "pen") return { kind: "pen", color: PEN_COLORS[pen].value, size: PEN_SIZES[size].value };
    if (active === "highlighter") return { kind: "highlighter", color: "#ffd400", size: 12 };
    return { kind: active };
  }, [active, pen, size]);

  useEffect(() => {
    const c = new NotebookCanvas(hostRef.current!, inkRef.current!, overlayRef.current!, notebookId, {
      onError,
      onState: setState,
      onEraseEnd: () => setActive(writingTool.current),
      onPage: (current, total) => setWhere({ current, total }),
    });
    canvas.current = c;
    return () => c.destroy();
  }, [notebookId, onError, revision]);

  useEffect(() => canvas.current?.setTool(tool), [tool, notebookId, revision]);
  useEffect(() => canvas.current?.setGestures(gestures), [gestures, notebookId, revision]);
  useEffect(() => canvas.current?.setScribbleErase(scribble), [scribble, notebookId, revision]);
  useEffect(() => savePrefs({ active, pen, size, gestures, scribble }, writingTool.current), [active, pen, size, gestures, scribble]);

  // Native app only: the Apple Pencil double tap arms the one-shot eraser, and undoes that if repeated.
  useEffect(() => onPencilDoubleTap(() => setActive((now) => afterDoubleTap(now, writingTool.current))), []);

  const choose = (kind: ToolKind) => {
    if (kind === "pen" || kind === "highlighter") writingTool.current = kind;
    setActive(kind);
  };

  const closeExport = useCallback(() => setExporting(false), []);
  const closeSettings = useCallback(() => setSettings(false), []);

  /** Send the lasso selection to the backend and show how it was read and verified. */
  const review = async () => {
    const snapshot = canvas.current?.selectionSnapshot();
    if (!snapshot) return;
    setPanel({ kind: "loading", since: Date.now() });
    try {
      // The subject of the notebook decides notation and which checks apply.
      const notebook = await db.notebooks.get(notebookId);
      const subject = notebook && (await db.subjects.get(notebook.subject_id));
      const slug = !subject || subject.template === "generic" ? "general" : subject.template;
      const started = performance.now();
      const result = await postCheck(loadConfig(), await snapshot.image, slug, snapshot.strokes);
      const saved: Review = {
        id: result.id,
        notebook_id: notebookId,
        page_id: snapshot.pageId,
        box: snapshot.box,
        created_at: Date.now(),
        recognition: result.recognition,
        verification: result.verification,
        cost_usd: result.cost_usd,
        timing: timingOf(result, (performance.now() - started) / 1000),
        month_spend_usd: result.usage.month_spend_usd,
        budget_usd: result.usage.budget_usd,
      };
      await db.reviews.put(saved); // kept on the iPad: readable later without connection
      setPanel({ kind: "result", review: saved });
    } catch (error) {
      setPanel({ kind: "error", message: (error as Error).message });
    }
  };
  /** Apply the backend's answer to the review on screen and to its copy on the iPad. */
  const update = async (request: (review: Review) => Promise<CheckResponse>) => {
    if (panel?.kind !== "result") return;
    const started = performance.now();
    const response = await request(panel.review);
    const next = mergeReview(panel.review, response, (performance.now() - started) / 1000);
    await db.reviews.put(next);
    setPanel({ kind: "result", review: next });
  };
  const actions = {
    onCorrect: (stepId: string, latex: string) => update((r) => postCorrection(loadConfig(), r.id, stepId, latex)),
    onHint: () => update((r) => postHint(loadConfig(), r.id)),
    onExplain: () => update((r) => postExplain(loadConfig(), r.id)),
    onSolve: () => update((r) => postSolve(loadConfig(), r.id)),
  };
  const failed = (what: string) => () => onError(`No se pudo ${what}.`);
  /** Run a command on the page at the centre of the screen, then rebuild if it changed the pages. */
  const onPage = (action: (pageId: string) => Promise<unknown>, what: string) => () => {
    const pageId = canvas.current?.currentPageId();
    if (pageId) void action(pageId).then(() => setRevision((r) => r + 1), failed(what));
  };
  const menu = [
    { label: "Páginas…", run: () => setPagesOpen(true) },
    { label: "Exportar…", run: () => setExporting(true) },
    { label: "Revisiones guardadas", run: () => setPanel({ kind: "history" }) },
    { label: "Ajustes de revisión…", run: () => setSettings(true) },
    {
      label: gestures ? "Gestos de deshacer: activados (tocar para apagar)" : "Gestos de deshacer: apagados (tocar para activar)",
      run: () => setGestures((on) => !on),
    },
    {
      label: scribble ? "Garabatear para borrar: activado (tocar para apagar)" : "Garabatear para borrar: apagado (tocar para activar)",
      run: () => setScribble((on) => !on),
    },
    { label: "Subir esta página", run: onPage((id) => movePage(id, -1), "mover la página") },
    { label: "Bajar esta página", run: onPage((id) => movePage(id, 1), "mover la página") },
    {
      label: "Borrar esta página",
      danger: true,
      run: () => {
        if (window.confirm("¿Borrar esta página con todo lo escrito? No se puede deshacer.")) onPage(deletePage, "borrar la página")();
      },
    },
  ];

  return (
    <>
      <div ref={hostRef} className="canvas-host">
        <canvas ref={inkRef} className="ink" />
        <canvas ref={overlayRef} className="overlay" />
      </div>
      <div className="page-indicator" aria-live="off">
        Página {where.current} de {where.total}
      </div>
      <Toolbar
        active={active}
        pen={pen}
        size={size}
        {...state}
        onTool={choose}
        onPen={(i) => {
          setPen(i);
          choose("pen");
        }}
        onSize={setSize}
        onUndo={() => canvas.current?.undo()}
        onRedo={() => canvas.current?.redo()}
        onDeleteSelection={() => canvas.current?.deleteSelection()}
        onDuplicateSelection={() => canvas.current?.duplicateSelection()}
        onReview={() => void review()}
        onBackground={() => canvas.current?.cycleBackground()}
        onLibrary={onLibrary}
        menu={menu}
      />
      {pagesOpen && (
        <PagesPanel
          // Remounted when pages change, so it never shows a stale list.
          key={`${revision}-${where.total}`}
          notebookId={notebookId}
          current={where.current - 1}
          onGo={(index) => {
            canvas.current?.goToPage(index);
            setPagesOpen(false);
          }}
          onClose={() => setPagesOpen(false)}
        />
      )}
      {exporting && <ExportDialog notebookId={notebookId} onClose={closeExport} onError={onError} />}
      {settings && <SettingsDialog onClose={closeSettings} />}
      {panel && (
        <ReviewPanel
          state={panel}
          notebookId={notebookId}
          actions={actions}
          onOpen={(opened) => setPanel({ kind: "result", review: opened })}
          onClose={() => setPanel(null)}
        />
      )}
    </>
  );
}
