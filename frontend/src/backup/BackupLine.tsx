import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useState } from "react";
import { loadConfig } from "../review/api";
import { describeNotebookBackup } from "./describe";
import { BACKUP_EVENT, pendingNotebooks, uploadPending } from "./sync";

/** Under the library's title: whether the notes exist anywhere but on this iPad, and a way to fix it now. */
export function BackupLine({ onError }: { onError(message: string): void }) {
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const changed = () => setTick((t) => t + 1);
    window.addEventListener(BACKUP_EVENT, changed);
    return () => window.removeEventListener(BACKUP_EVENT, changed);
  }, []);
  const pending = useLiveQuery(() => pendingNotebooks(), [tick]);
  if (!pending) return null;
  const config = loadConfig();
  const configured = !!config.url && !!config.token;
  const { tone, text } = describeNotebookBackup(configured, pending.length);
  const now = () => {
    setBusy(true);
    // "Now" means now: nothing is left for the next round.
    void uploadPending(config, Date.now() + 60_000).then(({ error }) => {
      if (error) onError(`No se pudo respaldar: ${error}`);
      setBusy(false);
    });
  };
  return (
    <p className={`backup-line ${tone}`} role="status">
      {text}{" "}
      {configured && pending.length > 0 && (
        <button type="button" className="quiet" disabled={busy} onClick={now}>{busy ? "Respaldando…" : "Respaldar ahora"}</button>
      )}
    </p>
  );
}
