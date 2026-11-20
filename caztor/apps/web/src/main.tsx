import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App.tsx";
import { createApiClient } from "./api/client.ts";
import { readLaunchToken } from "./api/token.ts";
import { createLayoutStore } from "./layout/storage.ts";
import { createThemeStore } from "./theme/theme.ts";
import "./styles/tokens.css";
import "./styles/base.css";

const root = document.getElementById("root");
if (root === null) throw new Error("The page has no #root element.");

/** `localStorage` can throw when the browser blocks storage; the layout store then runs without persistence. */
function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const token = readLaunchToken(document);

/**
 * A refused launch token means the server restarted with a new one (a PaperSmith dashboard restarts Caztor when it
 * needs to): loading the page again gets the new token. Once per half minute, so a token that keeps failing shows its
 * error instead of reloading for ever.
 */
function reloadForNewToken(): void {
  const key = "caztor.token-reload";
  try {
    const last = Number(window.sessionStorage.getItem(key) ?? "0");
    if (Date.now() - last < 30_000) return;
    window.sessionStorage.setItem(key, String(Date.now()));
  } catch {
    return;
  }
  window.location.reload();
}

createRoot(root).render(
  <StrictMode>
    {token === null ? (
      <p role="alert" style={{ padding: "var(--space-5)" }}>
        This page was not opened through the Caztor server. Start Caztor with a project folder and open the address it prints.
      </p>
    ) : (
      <App api={createApiClient({ token, onProjectChanged: () => window.location.reload(), onTokenRejected: reloadForNewToken })} layoutStore={createLayoutStore(browserStorage())} previewStorage={browserStorage()} themeStore={createThemeStore(browserStorage())} />
    )}
  </StrictMode>,
);
