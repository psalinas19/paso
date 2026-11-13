import { useEffect, useRef, useState } from "react";
import { collectNotebook, safeName, shareFile, toPdf, type NotebookExport } from "./notebook";

/** Choose which pages go into the PDF, or take the whole notebook as a JSON backup. */
export function ExportDialog({ notebookId, onClose, onError }: {
  notebookId: string;
  onClose: () => void;
  onError: (message: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<NotebookExport | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    dialog.current?.showModal();
    collectNotebook(notebookId).then(
      (d) => {
        setData(d);
        // Start with every page that has something written on it.
        setChosen(new Set(d.pages.filter((p) => p.strokes.length).map((p) => p.page.id)));
      },
      () => {
        onError("No se pudo leer el cuaderno para exportarlo.");
        onClose();
      },
    );
  }, [notebookId, onClose, onError]);

  const toggle = (id: string) =>
    setChosen((old) => {
      const next = new Set(old);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const run = async (make: (d: NotebookExport) => Promise<[Blob, string]>) => {
    if (!data) return;
    setBusy(true);
    try {
      const [blob, name] = await make(data);
      await shareFile(blob, name);
    } catch {
      onError("No se pudo exportar.");
    }
    onClose();
  };
  const pdf = () =>
    run(async (d) => {
      const pages = d.pages.filter((p) => chosen.has(p.page.id));
      const title = safeName(d.notebook.title);
      // One page: say which one. Several: the notebook's name.
      const which = pages.length === 1 ? ` - página ${d.pages.indexOf(pages[0]) + 1}` : "";
      return [await toPdf(pages), `${title}${which}.pdf`];
    });
  const json = () =>
    run(async (d) => [new Blob([JSON.stringify(d)], { type: "application/json" }), `${safeName(d.notebook.title)}.paso.json`]);

  return (
    <dialog ref={dialog} className="export" onClose={onClose} aria-labelledby="export-title">
      <h2 id="export-title">Exportar a PDF</h2>
      {!data ? (
        <p>Leyendo el cuaderno…</p>
      ) : (
        <>
          <div className="row">
            <button type="button" className="quiet" onClick={() => setChosen(new Set(data.pages.map((p) => p.page.id)))}>Todas</button>
            <button type="button" className="quiet" onClick={() => setChosen(new Set())}>Ninguna</button>
          </div>
          <ul>
            {data.pages.map((p, i) => (
              <li key={p.page.id}>
                <label>
                  <input type="checkbox" checked={chosen.has(p.page.id)} onChange={() => toggle(p.page.id)} />
                  Página {i + 1}
                  {!p.strokes.length && <span className="muted"> (vacía)</span>}
                </label>
              </li>
            ))}
          </ul>
          <button type="button" className="primary" disabled={busy || !chosen.size} onClick={() => void pdf()}>
            {busy ? "Preparando…" : `Exportar ${chosen.size} ${chosen.size === 1 ? "página" : "páginas"} a PDF`}
          </button>
          <button type="button" disabled={busy} onClick={() => void json()}>Respaldo del cuaderno completo (JSON)</button>
        </>
      )}
      <button type="button" className="quiet" onClick={onClose}>Cancelar</button>
    </dialog>
  );
}
