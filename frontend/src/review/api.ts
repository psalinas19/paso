// Client for the review backend (SPEC 7). The backend holds the Anthropic key;
// this side only knows where the backend is and our own shared token.

export type StepStatus = "correct" | "error" | "unverifiable";

/** Mirrors backend/app/schemas.py. */
export interface Step {
  id: string;
  latex: string;
  sympy: string | null;
  kind: string;
  relation: string;
  derives_from: string[];
  confidence: number;
  legible: boolean;
  notes: string | null;
}

export interface StepVerification {
  step_id: string;
  status: StepStatus;
  detail: string;
  method_used: string;
  depends_on_error: string | null;
}

export interface UsageSummary {
  month_spend_usd: number;
  budget_usd: number;
  checks_this_month: number;
}

/**
 * Level-1 help. The two sources never share a field: `verified` is what the
 * symbolic verifier established; `hint` and the error type are the model's words.
 */
export interface Hint {
  step_id: string | null;
  basis: "verified" | "model_opinion" | "none";
  verified: string;
  hint: string;
  error_type: string | null;
  error_label: string | null;
}

/**
 * Level-2 help: the model's commentary on each step, and how the failing step
 * should have read. `corrected.verified` is ours: the correction went through
 * the symbolic verifier before it was sent here.
 */
export interface Explanation {
  overview: string;
  notes: { step_id: string; note: string }[];
  failing_step_id: string | null;
  basis: "verified" | "model_opinion" | "none";
  corrected: { step_id: string; latex: string; sympy: string | null; verified: boolean; detail: string } | null;
  /** The model's correction was proved wrong by the verifier and withheld. */
  correction_rejected: boolean;
  next_step: string;
  takeaway: string;
}

/** Level-3 help: the worked solution, each step with the verifier's verdict. */
export interface Solution {
  goal: string;
  method: string;
  steps: { step: Step; why: string; status: StepStatus; detail: string; given: boolean }[];
  answer: string;
  check: string;
  verified: boolean;
  checked_steps: number;
  unchecked_steps: number;
  wrong_steps: number;
  attempts: number;
}

/** A review as it stands now. Every call that changes one returns this. */
export interface CheckResponse {
  id: string;
  /** The current steps: as read, with the student's corrections applied. */
  recognition: { steps: Step[]; model: string; warnings: string[] };
  verification: { steps: StepVerification[] };
  /** Ids of the steps the student retyped. */
  corrected?: string[];
  hint?: Hint | null;
  explanation?: Explanation | null;
  solution?: Solution | null;
  /** Cost of this call alone. */
  cost_usd: number;
  /** Seconds this call spent waiting for the model and checking the steps. */
  model_seconds?: number;
  verify_seconds?: number;
  usage: UsageSummary;
}

/** How long the model thinks before answering. Faster costs less and may read or explain worse. */
export type Speed = "fast" | "balanced" | "careful";

export const SPEEDS: { id: Speed; label: string; effort: string }[] = [
  { id: "fast", label: "Rápida", effort: "low" },
  { id: "balanced", label: "Equilibrada", effort: "medium" },
  { id: "careful", label: "Cuidadosa (la más lenta)", effort: "high" },
];

export interface BackendConfig {
  url: string;
  token: string;
  speed?: Speed;
}

const KEY = "paso:backend";

/**
 * Reduce whatever was pasted to the server's address alone. People paste the
 * link they just tested ("…/api/health"), leave a trailing slash, or drop the
 * "https://"; any of those used to end in a puzzling "Not Found".
 */
export function backendOrigin(input: string): string {
  const text = input.trim();
  if (!text) return "";
  try {
    return new URL(/^https?:\/\//i.test(text) ? text : `https://${text}`).origin;
  } catch {
    return text;
  }
}

/** Tolerate a token pasted as the whole line of the .env file, or wrapped in quotes or spaces. */
export function cleanToken(input: string): string {
  return input.trim().replace(/^APP_TOKEN\s*=\s*/i, "").replace(/^["']|["']$/g, "").trim();
}

export function loadConfig(): BackendConfig {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    // Normalised on read too, so an address saved by an older version just works.
    const speed = SPEEDS.find((s) => s.id === saved.speed)?.id ?? "careful";
    return { url: backendOrigin(String(saved.url ?? "")), token: cleanToken(String(saved.token ?? "")), speed };
  } catch {
    return { url: "", token: "", speed: "careful" };
  }
}

export function saveConfig(config: BackendConfig) {
  localStorage.setItem(KEY, JSON.stringify({ url: backendOrigin(config.url), token: cleanToken(config.token), speed: config.speed ?? "careful" }));
}

/** Below 0.7 the reading is doubtful and the panel says so (SPEC 6.2). */
export const LOW_CONFIDENCE = 0.7;

async function call<T>(config: BackendConfig, path: string, init: RequestInit = {}): Promise<T> {
  if (!config.url || !config.token) throw new Error("Falta configurar la dirección del backend y el token en Ajustes de revisión.");
  if (!navigator.onLine) throw new Error("Sin conexión: la revisión necesita internet.");
  // Every request that reaches the model says how fast the user wants it.
  if (init.method === "POST") {
    const body = init.body instanceof FormData ? init.body : new FormData();
    body.set("effort", SPEEDS.find((s) => s.id === config.speed)?.effort ?? "high");
    init = { ...init, body };
  }
  let response: Response;
  try {
    response = await fetch(config.url + path, {
      ...init,
      headers: { Authorization: `Bearer ${config.token}` },
      // A long page can take a while to read; give up rather than spin forever.
      signal: AbortSignal.timeout(90_000),
    });
  } catch (error) {
    if ((error as DOMException).name === "TimeoutError") throw new Error("El backend tardó demasiado en responder.");
    throw new Error("No se pudo conectar con el backend. ¿Está encendido y la dirección es la del túnel actual?");
  }
  if (!response.ok) {
    // The backend explains itself in Spanish in `detail`.
    const detail = await response.json().then((body) => body.detail, () => null);
    throw new Error(typeof detail === "string" ? detail : `El backend respondió con un error (${response.status}).`);
  }
  return response.json();
}

export const checkHealth = (config: BackendConfig) => call<{ ok: boolean }>(config, "/api/health");

export function postCheck(config: BackendConfig, image: Blob, subject: string, strokes: unknown): Promise<CheckResponse> {
  const body = new FormData();
  body.append("image", image, "selection.png");
  body.append("subject", subject);
  body.append("strokes", JSON.stringify(strokes));
  return call<CheckResponse>(config, "/api/check", { method: "POST", body });
}

/** Fix a misread step: the backend restructures the retyped LaTeX and verifies everything again. */
export function postCorrection(config: BackendConfig, checkId: string, stepId: string, latex: string): Promise<CheckResponse> {
  const body = new FormData();
  body.append("latex", latex);
  return call<CheckResponse>(config, `/api/checks/${encodeURIComponent(checkId)}/steps/${encodeURIComponent(stepId)}`, { method: "POST", body });
}

/** Ask for the level-1 hint of a review. Asking twice does not pay twice. */
export function postHint(config: BackendConfig, checkId: string): Promise<CheckResponse> {
  return call<CheckResponse>(config, `/api/checks/${encodeURIComponent(checkId)}/hint`, { method: "POST" });
}

/** Ask for the level-2 explanation: why each step holds, what went wrong, the corrected step. */
export function postExplain(config: BackendConfig, checkId: string): Promise<CheckResponse> {
  return call<CheckResponse>(config, `/api/checks/${encodeURIComponent(checkId)}/level/2`, { method: "POST" });
}

/** Ask for the level-3 worked solution, verified by the backend before it arrives. */
export function postSolve(config: BackendConfig, checkId: string): Promise<CheckResponse> {
  return call<CheckResponse>(config, `/api/checks/${encodeURIComponent(checkId)}/solve`, { method: "POST" });
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/** One server-sent event of the chat: a piece of the answer, the closing summary, or a failure. */
export type ChatEvent =
  | { event: "delta"; data: { text: string } }
  | { event: "done"; data: { cost_usd: number; usage: UsageSummary } }
  | { event: "error"; data: { detail: string } };

/**
 * Split what has arrived of an event stream into whole events and the
 * unfinished remainder. Events end with a blank line; the network may cut the
 * text anywhere, so the remainder is kept and parsed again with the next chunk.
 */
export function parseSse(buffer: string): { events: ChatEvent[]; rest: string } {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: ChatEvent[] = [];
  for (const block of blocks) {
    let event = "", data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (!event || !data) continue;
    try {
      events.push({ event, data: JSON.parse(data) } as ChatEvent);
    } catch {
      // A malformed event is skipped rather than breaking the whole answer.
    }
  }
  return { events, rest };
}

/**
 * Ask the tutor about a review. `onText` is called with the answer so far each
 * time more of it arrives; the promise resolves with the whole answer and what
 * it cost once it is complete.
 */
export async function streamChat(
  config: BackendConfig,
  checkId: string,
  message: string,
  onText: (soFar: string) => void,
): Promise<{ answer: string; cost_usd: number; usage: UsageSummary }> {
  if (!config.url || !config.token) throw new Error("Falta configurar la dirección del backend y el token en Ajustes de revisión.");
  if (!navigator.onLine) throw new Error("Sin conexión: el chat necesita internet.");
  const body = new FormData();
  body.append("message", message);
  body.append("effort", SPEEDS.find((s) => s.id === config.speed)?.effort ?? "high");
  let response: Response;
  try {
    response = await fetch(`${config.url}/api/checks/${encodeURIComponent(checkId)}/chat`, {
      method: "POST",
      body,
      headers: { Authorization: `Bearer ${config.token}` },
    });
  } catch {
    throw new Error("No se pudo conectar con el backend. ¿Está encendido y la dirección es la del túnel actual?");
  }
  if (!response.ok || !response.body) {
    const detail = await response.json().then((b) => b.detail, () => null);
    throw new Error(typeof detail === "string" ? detail : `El backend respondió con un error (${response.status}).`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", answer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const parsed = parseSse(done ? buffer + "\n\n" : buffer);
    buffer = parsed.rest;
    for (const item of parsed.events) {
      if (item.event === "delta") onText((answer += item.data.text));
      else if (item.event === "error") throw new Error(item.data.detail);
      else return { answer, ...item.data };
    }
    if (done) throw new Error("La respuesta se interrumpió antes de terminar. Pregunta de nuevo.");
  }
}
