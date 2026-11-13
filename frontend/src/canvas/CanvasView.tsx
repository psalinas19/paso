import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { db, type Review } from "../db";
import { ExportDialog } from "../export/ExportDialog";
import { loadConfig, postCheck } from "../review/api";
import { ReviewPanel, type ReviewState } from "../review/ReviewPanel";
import { SettingsDialog } from "../review/SettingsDialog";
import { deletePage, movePage } from "../library/actions";
import { NotebookCanvas, type Tool } from "./NotebookCanvas";
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

  const [active, setActive] = useState<ToolKind>("pen");
  const [pen, setPen] = useState(0);
  const [size, setSize] = useState(1);
  const [state, setState] = useState({ canUndo: false, canRedo: false, hasSelection: false });
  // Bumped after pages are reordered or deleted, to rebuild the surface from the database.
  const [revision, setRevision] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [settings, setSettings] = useState(false);
  const [panel, setPanel] = useState<ReviewState | null>(null);
  // What the one-shot eraser returns to.
  const writingTool = useRef<"pen" | "highlighter">("pen");

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
    });
    canvas.current = c;
    return () => c.destroy();
  }, [notebookId, onError, revision]);

  useEffect(() => canvas.current?.setTool(tool), [tool, notebookId, revision]);

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
        month_spend_usd: result.usage.month_spend_usd,
        budget_usd: result.usage.budget_usd,
      };
      await db.reviews.put(saved); // kept on the iPad: readable later without connection
      setPanel({ kind: "result", review: saved });
    } catch (error) {
      setPanel({ kind: "error", message: (error as Error).message });
    }
  };
  const failed = (what: string) => () => onError(`No se pudo ${what}.`);
  /** Run a command on the page at the centre of the screen, then rebuild if it changed the pages. */
  const onPage = (action: (pageId: string) => Promise<unknown>, what: string) => () => {
    const pageId = canvas.current?.currentPageId();
    if (pageId) void action(pageId).then(() => setRevision((r) => r + 1), failed(what));
  };
  const menu = [
    { label: "Exportar…", run: () => setExporting(true) },
    { label: "Revisiones guardadas", run: () => setPanel({ kind: "history" }) },
    { label: "Ajustes de revisión…", run: () => setSettings(true) },
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
        onReview={() => void review()}
        onBackground={() => canvas.current?.cycleBackground()}
        onLibrary={onLibrary}
        menu={menu}
      />
      {exporting && <ExportDialog notebookId={notebookId} onClose={closeExport} onError={onError} />}
      {settings && <SettingsDialog onClose={closeSettings} />}
      {panel && (
        <ReviewPanel
          state={panel}
          notebookId={notebookId}
          onOpen={(opened) => setPanel({ kind: "result", review: opened })}
          onClose={() => setPanel(null)}
        />
      )}
    </>
  );
}
