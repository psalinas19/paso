import { useEffect, useMemo, useRef, useState } from "react";
import { NotebookCanvas, type Tool } from "./NotebookCanvas";
import { PEN_COLORS, PEN_SIZES, Toolbar, type ToolKind } from "./Toolbar";

/** A notebook: the toolbar (React) on top of the drawing surface (NotebookCanvas). */
export function CanvasView({ notebookId, onError }: { notebookId: string; onError: (message: string) => void }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const docRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const canvas = useRef<NotebookCanvas | null>(null);

  const [active, setActive] = useState<ToolKind>("pen");
  const [pen, setPen] = useState(0);
  const [size, setSize] = useState(1);
  const [state, setState] = useState({ canUndo: false, canRedo: false, hasSelection: false });
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
  }, [notebookId, onError]);

  useEffect(() => canvas.current?.setTool(tool), [tool, notebookId]);

  const choose = (kind: ToolKind) => {
    if (kind === "pen" || kind === "highlighter") writingTool.current = kind;
    setActive(kind);
  };

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
      />
    </>
  );
}
