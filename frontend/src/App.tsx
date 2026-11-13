import { useEffect, useState } from "react";
import { registerSW } from "virtual:pwa-register";
import { CanvasView } from "./canvas/CanvasView";
import { db, ensureFirstPage } from "./db";
import { Library } from "./library/Library";

const LAST_NOTEBOOK = "paso:last-notebook";

export function App() {
  // null = the library screen; undefined = still starting up.
  const [notebookId, setNotebookId] = useState<string | null | undefined>(undefined);
  const [error, setError] = useState("");
  const [offlineReady, setOfflineReady] = useState(false);

  useEffect(() => {
    // Open straight onto the last notebook: writing should be one tap away.
    ensureFirstPage()
      .then(async (first) => {
        const last = localStorage.getItem(LAST_NOTEBOOK);
        setNotebookId(last && (await db.notebooks.get(last)) ? last : first.notebook_id);
      })
      .catch(() => setError("No se pudo abrir el almacenamiento de este navegador. ¿Estás en navegación privada?"));
    // Ask Safari not to evict the notes when the iPad runs low on space.
    void navigator.storage?.persist?.();
    registerSW({ immediate: true, onOfflineReady: () => setOfflineReady(true) });
  }, []);

  useEffect(() => {
    if (notebookId) localStorage.setItem(LAST_NOTEBOOK, notebookId);
  }, [notebookId]);

  useEffect(() => {
    if (!offlineReady) return;
    const timer = setTimeout(() => setOfflineReady(false), 6000);
    return () => clearTimeout(timer);
  }, [offlineReady]);

  return (
    <>
      {notebookId && <CanvasView notebookId={notebookId} onError={setError} onLibrary={() => setNotebookId(null)} />}
      {notebookId === null && <Library onOpen={setNotebookId} onError={setError} />}
      {error && (
        <div className="banner banner-error" role="alert" onClick={() => setError("")}>
          {error} <span aria-hidden="true">✕</span>
        </div>
      )}
      {offlineReady && !error && (
        <div className="banner" role="status">
          Lista para usarse sin conexión.
        </div>
      )}
    </>
  );
}
