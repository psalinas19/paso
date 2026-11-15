import { useState, type FormEvent } from "react";
import { db, type Review } from "../db";
import { getCheck, loadConfig, searchReviews, type CheckResponse, type SearchHit } from "../review/api";
import { Result } from "../review/ReviewPanel";

const WHERE: Record<SearchHit["kinds"][number], string> = {
  steps: "tu desarrollo",
  hint: "la pista",
  explanation: "la explicación",
  solution: "la solución",
  chat: "el chat",
};

/** "tu desarrollo, la pista y el chat" */
export function describeKinds(kinds: SearchHit["kinds"]): string {
  const names = kinds.map((kind) => WHERE[kind] ?? kind);
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} y ${names.at(-1)}` : (names[0] ?? "");
}

/** A review read back from the backend, shaped like the ones kept here so it can be shown the same way. */
export function asReview(response: CheckResponse, createdAt: string): Review {
  return {
    id: response.id,
    notebook_id: "",
    page_id: "",
    box: [0, 0, 0, 0],
    created_at: Date.parse(createdAt) || 0,
    recognition: response.recognition,
    verification: response.verification,
    corrected: response.corrected ?? [],
    hint: response.hint ?? null,
    explanation: response.explanation ?? null,
    solution: response.solution ?? null,
    cost_usd: 0,
    month_spend_usd: response.usage.month_spend_usd,
    budget_usd: response.usage.budget_usd,
  };
}

/** One result: where it matched, and a way to get to the whole review. */
export function HitRow({ hit, onShow, shown, error }: {
  hit: SearchHit;
  onShow(): void;
  /** The whole review, when it is not on this device and was fetched to read it here. */
  shown?: Review;
  error?: string;
}) {
  return (
    <li className="hit">
      <p className="when">
        {new Date(hit.created_at).toLocaleDateString("es-MX", { dateStyle: "medium" })} · en {describeKinds(hit.kinds)}
      </p>
      <p className="passage">
        {hit.snippet.map((part, i) => (part.hit ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>))}
      </p>
      {!shown && <button type="button" onClick={onShow}>Abrir la revisión</button>}
      {error && <p className="bad" role="alert">{error}</p>}
      {shown && (
        <div className="review-inline">
          <p className="muted">Esta revisión no está guardada en este iPad: la muestro aquí, sin su hoja.</p>
          <Result review={shown} />
        </div>
      )}
    </li>
  );
}

type State = { kind: "idle" } | { kind: "loading" } | { kind: "error"; message: string } | { kind: "results"; query: string; hits: SearchHit[] };

/** Search across every review by what it says (SPEC 7). Needs the backend: the index lives there. */
export function SearchView({ onBack, onOpen }: {
  onBack(): void;
  onOpen(notebookId: string, pageId: string, reviewId: string): void;
}) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });
  const [remote, setRemote] = useState<Record<string, Review>>({});
  const [failed, setFailed] = useState<Record<string, string>>({});

  const run = (e: FormEvent) => {
    e.preventDefault();
    const text = query.trim();
    if (!text) return;
    setState({ kind: "loading" });
    searchReviews(loadConfig(), text).then(
      (hits) => setState({ kind: "results", query: text, hits }),
      (error: Error) => setState({ kind: "error", message: error.message }),
    );
  };

  const show = async (hit: SearchHit) => {
    // On this iPad: go to the page it was written on, with the review open.
    const local = await db.reviews.get(hit.check_id);
    if (local && (await db.notebooks.get(local.notebook_id))) return onOpen(local.notebook_id, local.page_id, local.id);
    try {
      const response = await getCheck(loadConfig(), hit.check_id);
      setRemote((now) => ({ ...now, [hit.check_id]: asReview(response, hit.created_at) }));
    } catch (error) {
      setFailed((now) => ({ ...now, [hit.check_id]: (error as Error).message }));
    }
  };

  return (
    <main className="library search">
      <header>
        <button type="button" className="quiet" onClick={onBack}>‹ Biblioteca</button>
        <h1>Buscar</h1>
      </header>
      <form className="add" onSubmit={run}>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Una palabra de la explicación, del chat o de tu desarrollo"
          aria-label="Qué buscar"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="none"
          spellCheck={false}
          enterKeyHint="search"
        />
        <button type="submit" disabled={!query.trim() || state.kind === "loading"}>{state.kind === "loading" ? "Buscando…" : "Buscar"}</button>
      </form>
      <p className="muted">
        Busca en lo que se leyó de tus revisiones y en las pistas, explicaciones, soluciones y chats. No busca en la tinta que no has revisado. Los
        acentos dan igual.
      </p>
      {state.kind === "error" && <p className="bad" role="alert">{state.message}</p>}
      {state.kind === "results" && !state.hits.length && <p>No encontré nada con «{state.query}».</p>}
      {state.kind === "results" && state.hits.length > 0 && (
        <ul className="hits">
          {state.hits.map((hit) => (
            <HitRow key={hit.check_id} hit={hit} shown={remote[hit.check_id]} error={failed[hit.check_id]} onShow={() => void show(hit)} />
          ))}
        </ul>
      )}
    </main>
  );
}
