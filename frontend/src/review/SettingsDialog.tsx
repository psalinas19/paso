import { useEffect, useRef, useState, type FormEvent } from "react";
import { checkHealth, loadConfig, saveConfig } from "./api";

/** Where the review backend is and the shared token. Stored on this iPad only. */
export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [config, setConfig] = useState(loadConfig);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => dialog.current?.showModal(), []);

  const save = (e: FormEvent) => {
    e.preventDefault();
    saveConfig(config);
    onClose();
  };

  const test = async () => {
    saveConfig(config);
    setBusy(true);
    setStatus(null);
    try {
      await checkHealth(loadConfig());
      setStatus({ ok: true, text: "Conexión correcta." });
    } catch (error) {
      setStatus({ ok: false, text: (error as Error).message });
    }
    setBusy(false);
  };

  return (
    <dialog ref={dialog} className="sheet-dialog" onClose={onClose} aria-labelledby="settings-title">
      <form onSubmit={save}>
        <h2 id="settings-title">Ajustes de revisión</h2>
        <p className="muted">
          La revisión con IA pasa por tu backend. Pega aquí la dirección que muestra el túnel al arrancarlo y el token
          que pusiste en <code>APP_TOKEN</code>.
        </p>
        <label>
          Dirección del backend
          <input
            type="url"
            inputMode="url"
            placeholder="https://….trycloudflare.com"
            value={config.url}
            onChange={(e) => setConfig({ ...config, url: e.target.value })}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
          />
        </label>
        <label>
          Token
          <input
            type="password"
            value={config.token}
            onChange={(e) => setConfig({ ...config, token: e.target.value })}
            autoComplete="off"
          />
        </label>
        {status && (
          <p className={status.ok ? "ok" : "bad"} role="status">
            {status.text}
          </p>
        )}
        <button type="button" disabled={busy || !config.url || !config.token} onClick={() => void test()}>
          {busy ? "Probando…" : "Probar conexión"}
        </button>
        <button type="submit" className="primary">Guardar</button>
        <button type="button" className="quiet" onClick={onClose}>Cancelar</button>
      </form>
    </dialog>
  );
}
