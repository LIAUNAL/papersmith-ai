import type { ProviderId } from "@caztor/core";
import { PROVIDER_META } from "./providers.ts";
import "./ProviderLogo.css";

interface ProviderLogoProps {
  provider: ProviderId;
  size?: "small" | "large";
}

/** The provider's name as a text label: Caztor ships no vendor logo, so it reads the same in light and dark themes. */
export function ProviderLogo({ provider, size = "small" }: ProviderLogoProps) {
  return <span className={`provider-logo provider-logo--text provider-logo--${size}`}>{PROVIDER_META[provider].name}</span>;
}
