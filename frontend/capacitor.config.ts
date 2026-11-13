import type { CapacitorConfig } from "@capacitor/cli";

// The native iPad shell around the same web app (docs/app-nativa.md).
// The bundle id must be unique per Apple account; change it in Xcode if it is taken.
const config: CapacitorConfig = {
  appId: "app.paso.libreta",
  appName: "Paso",
  webDir: "dist",
  ios: {
    // The page handles the notch itself with env(safe-area-inset-*).
    contentInset: "never",
  },
};

export default config;
