import { useEffect, useState } from "react";
import { registerSW } from "virtual:pwa-register";
import { CanvasView } from "./canvas/CanvasView";
import { uploadPending } from "./backup/sync";
import { db, ensureFirstPage } from "./db";
import { ErrorsView } from "./errors/ErrorsView";
import { Library } from "./library/Library";
import { SearchView } from "./search/SearchView";
import { isNative } from "./native/pencil";
import { loadConfig } from "./review/api";

const LAST_NOTEBOOK = "paso:last-notebook";

export function App() {
  // null = the library screen; undefined = still starting up.
  const [notebookId, setNotebookId] = useState<string | null | undefined>(undefined);
  // Which screen is up when no notebook is open.
  const [screen, setScreen] = useState<"library" | "errors" | "search">("library");
  // The page to open the notebook on, when it is opened to practise an exercise.
  const [startPage, setStartPage] = useState<string | undefined>(undefined);
  // The saved review to show on arrival, when the notebook is opened from a search hit.
  const [openReview, setOpenReview] = useState<string | undefined>(undefined);
  const openAt = (id: string, pageId?: string, reviewId?: string) => {
    setStartPage(pageId);
    setOpenReview(reviewId);
    setNotebookId(id);
  };
  const [error, setError] = useState("");
  const [offlineReady, setOfflineReady] = useState(false);

  useEffect(() => {
    // Open straight onto the last notebook: writing should be one tap away.
    ensureFirstPage()
      .then(async (first) => {
        const last = localStorage.getItem(LAST_NOTEBOOK);
        const found = last ? await db.notebooks.get(last) : undefined;
        // A notebook whose pages are on the server opens from the library, which downloads it first.
        setNotebookId(found ? (found.evicted ? null : found.id) : (first?.notebook_id ?? null));
        // Whatever did not reach the server last time goes up now. Free and silent.
        void uploadPending(loadConfig());
      })
      .catch(() => setError("No se pudo abrir el almacenamiento de este navegador. ¿Estás en navegación privada?"));
    // Ask Safari not to evict the notes when the iPad runs low on space.
    void navigator.storage?.persist?.();
    // The native app carries its files inside: no service worker, and nothing to announce.
    if (!isNative) registerSW({ immediate: true, onOfflineReady: () => setOfflineReady(true) });
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
      {notebookId && (
        <CanvasView
          key={notebookId}
          notebookId={notebookId}
          startPageId={startPage}
          openReviewId={openReview}
          onError={setError}
          onLibrary={() => {
            // "Biblioteca" always means the library, also when the notebook was opened from the error bank.
            setScreen("library");
            setNotebookId(null);
          }}
        />
      )}
      {notebookId === null && screen === "library" && <Library onOpen={openAt} onErrors={() => setScreen("errors")} onSearch={() => setScreen("search")} onError={setError} />}
      {notebookId === null && screen === "search" && <SearchView onBack={() => setScreen("library")} onOpen={openAt} />}
      {notebookId === null && screen === "errors" && <ErrorsView onBack={() => setScreen("library")} onOpen={openAt} />}
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
