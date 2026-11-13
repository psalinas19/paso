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

export interface CheckResponse {
  id: string;
  recognition: { steps: Step[]; model: string; warnings: string[] };
  verification: { steps: StepVerification[] };
  cost_usd: number;
  usage: UsageSummary;
}

export interface BackendConfig {
  url: string;
  token: string;
}

const KEY = "paso:backend";

export function loadConfig(): BackendConfig {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return { url: String(saved.url ?? ""), token: String(saved.token ?? "") };
  } catch {
    return { url: "", token: "" };
  }
}

export function saveConfig(config: BackendConfig) {
  // Tolerate a pasted trailing slash or spaces: the tunnel address changes often.
  localStorage.setItem(KEY, JSON.stringify({ url: config.url.trim().replace(/\/+$/, ""), token: config.token.trim() }));
}

/** Below 0.7 the reading is doubtful and the panel says so (SPEC 6.2). */
export const LOW_CONFIDENCE = 0.7;

async function call<T>(config: BackendConfig, path: string, init: RequestInit = {}): Promise<T> {
  if (!config.url || !config.token) throw new Error("Falta configurar la dirección del backend y el token en Ajustes de revisión.");
  if (!navigator.onLine) throw new Error("Sin conexión: la revisión necesita internet.");
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
