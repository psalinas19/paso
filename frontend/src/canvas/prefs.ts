// Small per-device preferences of the notebook screen. Not notes: losing them
// only means the toolbar opens with its defaults.
import type { ToolKind } from "./Toolbar";

export interface ToolPrefs {
  active: "pen" | "highlighter";
  pen: number;
  size: number;
  /** Two-finger tap undoes, three-finger tap redoes. */
  gestures: boolean;
  /** Scribbling over ink erases it. Off from the factory: it can be mistaken for a crossing-out. */
  scribble: boolean;
}

export const DEFAULT_PREFS: ToolPrefs = { active: "pen", pen: 0, size: 1, gestures: true, scribble: false };
const KEY = "paso:tools";

const index = (value: unknown, count: number, fallback: number) =>
  Number.isInteger(value) && (value as number) >= 0 && (value as number) < count ? (value as number) : fallback;

/** Whatever was stored, reduced to something the toolbar can show. */
export function parsePrefs(raw: string | null, pens: number, sizes: number): ToolPrefs {
  try {
    const saved = JSON.parse(raw ?? "{}") ?? {};
    return {
      active: saved.active === "highlighter" ? "highlighter" : "pen",
      pen: index(saved.pen, pens, DEFAULT_PREFS.pen),
      size: index(saved.size, sizes, DEFAULT_PREFS.size),
      gestures: saved.gestures !== false,
      scribble: saved.scribble === true,
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function loadPrefs(pens: number, sizes: number): ToolPrefs {
  try {
    return parsePrefs(localStorage.getItem(KEY), pens, sizes);
  } catch {
    return DEFAULT_PREFS; // storage blocked
  }
}

/** The eraser and the lasso are momentary: reopening always starts on a writing tool. */
export function savePrefs(prefs: Omit<ToolPrefs, "active"> & { active: ToolKind }, writing: "pen" | "highlighter") {
  const active = prefs.active === "pen" || prefs.active === "highlighter" ? prefs.active : writing;
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...prefs, active }));
  } catch {
    // Nothing to do: the preference just will not stick.
  }
}
