import { useEffect, useMemo, useRef, useState } from "react";
import { exportNotebookJson, exportNotebookPdf, exportPagePdf } from "../export/notebook";
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
  const docRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const canvas = useRef<NotebookCanvas | null>(null);

  const [active, setActive] = useState<ToolKind>("pen");
  const [pen, setPen] = useState(0);
  const [size, setSize] = useState(1);
  const [state, setState] = useState({ canUndo: false, canRedo: false, hasSelection: false });
  // Bumped after pages are reordered or deleted, to rebuild the surface from the database.
  const [revision, setRevision] = useState(0);
  // What the one-shot eraser returns to.
  const writingTool = useRef<"pen" | "highlighter">("pen");

  const tool = useMemo<Tool>(() => {
    if (active === "pen") return { kind: "pen", color: PEN_COLORS[pen].value, size: PEN_SIZES[size].value };
    if (active === "highlighter") return { kind: "highlighter", color: "#ffd400", size: 12 };
    return { kind: active };
  }, [active, pen, size]);

  useEffect(() => {
    const c = new NotebookCanvas(hostRef.current!, docRef.current!, overlayRef.current!, notebookId, {
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

  const failed = (what: string) => () => onError(`No se pudo ${what}.`);
  /** Run a command on the page at the centre of the screen, then rebuild if it changed the pages. */
  const onPage = (action: (pageId: string) => Promise<unknown>, what: string, rebuild = true) => () => {
    const pageId = canvas.current?.currentPageId();
    if (pageId) void action(pageId).then(() => rebuild && setRevision((r) => r + 1), failed(what));
  };
  const menu = [
    { label: "Exportar esta página a PDF", run: onPage((id) => exportPagePdf(notebookId, id), "exportar la página", false) },
    { label: "Exportar el cuaderno a PDF", run: () => void exportNotebookPdf(notebookId).catch(failed("exportar el cuaderno")) },
    { label: "Exportar el cuaderno a JSON (respaldo)", run: () => void exportNotebookJson(notebookId).catch(failed("exportar el respaldo")) },
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
        <div ref={docRef} className="doc" />
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
        onBackground={() => canvas.current?.cycleBackground()}
        onAddPage={() => canvas.current?.addPage()}
        onLibrary={onLibrary}
        menu={menu}
      />
    </>
  );
}
