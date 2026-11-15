import { useLiveQuery } from "dexie-react-hooks";
import { db, type SavedPlot } from "../db";
import { Latex } from "../review/ReviewPanel";

/** The graphs made in this notebook. They are kept on the iPad: opening one needs no connection. */
export function PlotsPanel({ notebookId, onOpen, onClose }: {
  notebookId: string;
  onOpen(plot: SavedPlot): void;
  onClose(): void;
}) {
  const plots = useLiveQuery(() => db.plots.where("notebook_id").equals(notebookId).reverse().sortBy("created_at"), [notebookId]);
  return (
    <aside className="review" aria-label="Gráficas guardadas">
      <header>
        <h2>Gráficas guardadas</h2>
        <button type="button" className="quiet" onClick={onClose} aria-label="Cerrar gráficas">✕</button>
      </header>
      {plots && !plots.length && (
        <p className="muted">Todavía no hay gráficas en este cuaderno. Rodea una ecuación con el lazo y toca Graficar.</p>
      )}
      <ul className="history plots">
        {(plots ?? []).map((plot) => (
          <li key={plot.id}>
            <button type="button" onClick={() => onOpen(plot)}>
              <Latex source={plot.latex} />
              <span className="muted">{new Date(plot.created_at).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" })}</span>
            </button>
            <button type="button" className="quiet" aria-label="Borrar esta gráfica" onClick={() => void db.plots.delete(plot.id)}>Borrar</button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
