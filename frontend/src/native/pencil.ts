// The native iPad shell (Capacitor, see docs/app-nativa.md). In the browser and
// in the installed PWA none of this does anything: `isNative` is false.
import { Capacitor, registerPlugin, type PluginListenerHandle } from "@capacitor/core";

/** True inside the native app, false in Safari and in the home-screen PWA. */
export const isNative = Capacitor.isNativePlatform();

interface PencilPlugin {
  addListener(event: "doubleTap", listener: () => void): Promise<PluginListenerHandle>;
}

/** Implemented in frontend/ios/App/App/PencilPlugin.swift. */
const Pencil = registerPlugin<PencilPlugin>("Pencil");

/**
 * Call `listener` on every Apple Pencil double tap. Returns how to stop
 * listening. Outside the native app there is no such event, so this is a no-op.
 */
export function onPencilDoubleTap(listener: () => void): () => void {
  if (!isNative) return () => {};
  const handle = Pencil.addListener("doubleTap", listener);
  return () => void handle.then((h) => h.remove(), () => {});
}

/**
 * What a double tap does to the toolbar (SPEC 6.1): it arms the one-shot
 * eraser, and a second double tap puts the writing tool back.
 */
export function afterDoubleTap<T extends string>(active: T | "eraser", writing: T): T | "eraser" {
  return active === "eraser" ? writing : "eraser";
}
