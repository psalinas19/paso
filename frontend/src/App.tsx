import { useEffect, useState } from "react";
import { registerSW } from "virtual:pwa-register";
import { CanvasView } from "./canvas/CanvasView";
import { ensureFirstPage, type Page } from "./db";

export function App() {
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState("");
  const [offlineReady, setOfflineReady] = useState(false);

  useEffect(() => {
    ensureFirstPage().then(setPage, () =>
      setError("No se pudo abrir el almacenamiento de este navegador. ¿Estás en navegación privada?"),
    );
    // Ask Safari not to evict the notes when the iPad runs low on space.
    void navigator.storage?.persist?.();
    registerSW({ immediate: true, onOfflineReady: () => setOfflineReady(true) });
  }, []);

  useEffect(() => {
    if (!offlineReady) return;
    const timer = setTimeout(() => setOfflineReady(false), 6000);
    return () => clearTimeout(timer);
  }, [offlineReady]);

  return (
    <>
      {page && <CanvasView notebookId={page.notebook_id} onError={setError} />}
      {error && (
        <div className="banner banner-error" role="alert">
          {error}
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
