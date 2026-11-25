import { useEffect, useState, useSyncExternalStore } from "react";
import type { ProviderId } from "@caztor/core";
import { PROVIDER_META } from "./providers.ts";
import "./ProviderLogo.css";

interface ProviderLogoProps {
  provider: ProviderId;
  size?: "small" | "large";
}

const followTheme = (changed: () => void) => {
  const observer = new MutationObserver(changed);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
};
const chosenTheme = () => document.documentElement.getAttribute("data-theme");
/** `<source media>` sees only the system's preference, so a manual theme is expressed as a query that always or never matches. */
const DARK_MEDIA = (theme: string | null) => (theme === "dark" ? "all" : theme === "light" ? "not all" : "(prefers-color-scheme: dark)");

/** The provider's official logo. Its name appears as text only when there is no logo or it fails to load. */
export function ProviderLogo({ provider, size = "small" }: ProviderLogoProps) {
  const [failed, setFailed] = useState(false);
  const meta = PROVIDER_META[provider];
  const theme = useSyncExternalStore(followTheme, chosenTheme);
  useEffect(() => setFailed(false), [provider]);

  if (meta.logo === null || failed) {
    return <span className={`provider-logo provider-logo--text provider-logo--${size}`}>{meta.name}</span>;
  }
  return (
    <picture className={`provider-logo provider-logo--${size}`}>
      {meta.logo.dark === undefined ? null : <source media={DARK_MEDIA(theme)} srcSet={meta.logo.dark} />}
      <img src={meta.logo.light} alt={meta.name} draggable={false} onError={() => setFailed(true)} />
    </picture>
  );
}
