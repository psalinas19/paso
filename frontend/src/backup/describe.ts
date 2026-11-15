// The words for the state of the backups. Pure, so they can be tested.
import type { BackupState } from "../review/api";

/** The line under the library's title: are my notes anywhere but this iPad? */
export function describeNotebookBackup(configured: boolean, pending: number): { tone: "ok" | "warn"; text: string } {
  if (!configured) {
    return { tone: "warn", text: "Tus notas están solo en este iPad. Configura el servidor en ⋯ → Ajustes de revisión (dentro de un cuaderno) para que se respalden solas." };
  }
  if (!pending) return { tone: "ok", text: "Todos tus cuadernos tienen copia en el servidor." };
  return { tone: "warn", text: pending === 1 ? "1 cuaderno tiene cambios sin copia en el servidor." : `${pending} cuadernos tienen cambios sin copia en el servidor.` };
}

/** How the server's own daily backup is doing, for the settings dialog. */
export function describeServerBackup(state: BackupState, now = Date.now()): string {
  if (!state.enabled) return "Este backend no hace respaldos de sí mismo (es lo normal en tu laptop).";
  if (!state.at) return "El servidor aún no hace su primer respaldo.";
  const hours = Math.max(0, Math.round((now - Date.parse(state.at)) / 3_600_000));
  const when = hours < 1 ? "hace menos de una hora" : hours === 1 ? "hace 1 hora" : hours < 48 ? `hace ${hours} horas` : `hace ${Math.round(hours / 24)} días`;
  if (!state.ok) return `El último respaldo del servidor FALLÓ (${when}): ${state.detail || "sin detalle"}`;
  return state.offsite
    ? `Último respaldo del servidor: ${when}, con copia fuera del servidor.`
    : `Último respaldo del servidor: ${when}, pero SIN copia fuera del servidor: si el servidor se pierde, se pierde con él.`;
}
