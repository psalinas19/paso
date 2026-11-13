import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { db, type Review } from "../db";
import { ExportDialog } from "../export/ExportDialog";
import { useLiveQuery } from "dexie-react-hooks";
import { loadConfig, postCheck, postCorrection, postExplain, postHint, postSolve, streamChat, type CheckResponse } from "../review/api";
import { enqueue, sendQueued, toReview } from "../review/queue";
import { MarkCard, type OpenMark } from "../review/MarkCard";
import { mergeReview } from "../review/merge";
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
  // The card open beside a mark on the page, and whether it stays when writing resumes.
  const [card, setCard] = useState<OpenMark | null>(null);
  const [pinned, setPinned] = useState(false);
  const pinnedRef = useRef(false);
  pinnedRef.current = pinned;
  // Every review of this notebook: the canvas draws their marks beside the ink.
  const reviews = useLiveQuery(() => db.reviews.where("notebook_id").equals(notebookId).toArray(), [notebookId]);
  // Reviews asked for offline and still waiting to be sent.
  const waiting = useLiveQuery(() => db.queue.where("notebook_id").equals(notebookId).count(), [notebookId]) ?? 0;
  const [backOnline, setBackOnline] = useState(false);
  useEffect(() => {
    // The connection is back: say so, but send nothing. Each review costs money (SPEC 6.9).
    const online = () => setBackOnline(true);
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, []);
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
      onMark: (mark, x, y) => {
        setPinned(false);
        setCard({ mark, x, y });
      },
      // Writing again puts an unpinned card away: it would be in the way of the pen.
      onInk: () => {
        if (!pinnedRef.current) setCard(null);
      },
    });
    canvas.current = c;
    return () => c.destroy();
  }, [notebookId, onError, revision]);

  useEffect(() => canvas.current?.setTool(tool), [tool, notebookId, revision]);
  useEffect(() => canvas.current?.setGestures(gestures), [gestures, notebookId, revision]);
  useEffect(() => canvas.current?.setReviews(reviews ?? []), [reviews, notebookId, revision]);
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
    const selection = { notebookId, pageId: snapshot.pageId, box: snapshot.box, strokes: snapshot.strokes };
    // The subject of the notebook decides notation and which checks apply.
    const notebook = await db.notebooks.get(notebookId);
    const subject = notebook && (await db.subjects.get(notebook.subject_id));
    const slug = !subject || subject.template === "generic" ? "general" : subject.template;
    const image = await snapshot.image;
    const park = async (reason: string) => {
      await enqueue(selection, slug, image);
      setPanel({ kind: "queued", reason, pending: await db.queue.where("notebook_id").equals(notebookId).count() });
    };
    try {
      // No connection: keep it for later instead of failing (SPEC 6.9).
      if (!navigator.onLine) return await park("No hay conexión.");
      const started = performance.now();
      const result = await postCheck(loadConfig(), image, slug, snapshot.strokes);
      const saved = toReview(result, selection, (performance.now() - started) / 1000);
      await db.reviews.put(saved); // kept on the iPad: readable later without connection
      setPanel({ kind: "result", review: saved });
    } catch (error) {
      const message = (error as Error).message;
      // The backend could not be reached at all: nothing was spent, so the request is worth keeping.
      if (message.startsWith("No se pudo conectar") || message.startsWith("Sin conexión")) await park("No se pudo conectar con el backend.");
      else setPanel({ kind: "error", message });
    }
  };
  /** Apply the backend's answer to the review on screen and to its copy on the iPad. */
  const applyTo = async (review: Review, request: (review: Review) => Promise<CheckResponse>) => {
    const started = performance.now();
    const response = await request(review);
    const next = mergeReview(review, response, (performance.now() - started) / 1000);
    await db.reviews.put(next);
    // The panel follows only if it is showing this same review.
    setPanel((now) => (now?.kind === "result" && now.review.id === next.id ? { kind: "result", review: next } : now));
  };
  const update = async (request: (review: Review) => Promise<CheckResponse>) => {
    if (panel?.kind === "result") await applyTo(panel.review, request);
  };
  const carded = card && reviews?.find((r) => r.id === card.mark.reviewId);
  const actions = {
    onCorrect: (stepId: string, latex: string) => update((r) => postCorrection(loadConfig(), r.id, stepId, latex)),
    onHint: () => update((r) => postHint(loadConfig(), r.id)),
    onExplain: () => update((r) => postExplain(loadConfig(), r.id)),
    onSolve: () => update((r) => postSolve(loadConfig(), r.id)),
    onChat: async (message: string, onText: (soFar: string) => void) => {
      if (panel?.kind !== "result") return;
      const asked = panel.review;
      const reply = await streamChat(loadConfig(), asked.id, message, onText);
      // Read again: the review may have gained a hint or a correction meanwhile.
      const current = (await db.reviews.get(asked.id)) ?? asked;
      const next: Review = {
        ...current,
        chat: [...(current.chat ?? []), { role: "user", content: message }, { role: "assistant", content: reply.answer }],
        cost_usd: current.cost_usd + reply.cost_usd,
        month_spend_usd: reply.usage.month_spend_usd,
        budget_usd: reply.usage.budget_usd,
      };
      await db.reviews.put(next);
      setPanel((now) => (now?.kind === "result" && now.review.id === next.id ? { kind: "result", review: next } : now));
    },
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
    { label: waiting ? `Revisiones en espera (${waiting})` : "Revisiones en espera", run: () => setPanel({ kind: "queue" }) },
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
      {card && carded && (
        <MarkCard
          key={`${card.mark.reviewId}-${card.mark.stepId}`}
          open={card}
          review={carded}
          pinned={pinned}
          onPin={() => setPinned((p) => !p)}
          onHint={() => applyTo(carded, (r) => postHint(loadConfig(), r.id))}
          onOpenReview={() => {
            setPanel({ kind: "result", review: carded });
            setCard(null);
          }}
          onClose={() => setCard(null)}
        />
      )}
      {backOnline && waiting > 0 && (
        <div className="banner" role="status">
          Volvió la conexión y hay {waiting === 1 ? "una revisión" : `${waiting} revisiones`} en espera.{" "}
          <button type="button" onClick={() => { setPanel({ kind: "queue" }); setBackOnline(false); }}>Ver</button>{" "}
          <button type="button" aria-label="Cerrar aviso" onClick={() => setBackOnline(false)}>✕</button>
        </div>
      )}
      {exporting && <ExportDialog notebookId={notebookId} onClose={closeExport} onError={onError} />}
      {settings && <SettingsDialog onClose={closeSettings} />}
      {panel && (
        <ReviewPanel
          state={panel}
          notebookId={notebookId}
          actions={actions}
          onSendQueued={(item) => sendQueued(loadConfig(), item)}
          onOpen={(opened) => setPanel({ kind: "result", review: opened })}
          onClose={() => setPanel(null)}
        />
      )}
    </>
  );
}
