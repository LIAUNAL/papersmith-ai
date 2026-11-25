import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ProviderId } from "@caztor/core";
import { ProviderLogo } from "./ProviderLogo.tsx";
import { PROVIDER_META } from "./providers.ts";

const ALL = Object.keys(PROVIDER_META) as ProviderId[];

describe("ProviderLogo", () => {
  it.each(ALL)("shows %s by its name as text, with no image", (provider) => {
    const { container } = render(<ProviderLogo provider={provider} />);
    expect(container).toHaveTextContent(PROVIDER_META[provider].name);
    expect(container.querySelector("img, picture, source, svg")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("ships no third-party logo: no provider carries a logo asset", () => {
    for (const provider of ALL) expect(PROVIDER_META[provider]).not.toHaveProperty("logo");
  });

  it("uses the larger text size in the header", () => {
    const { container } = render(<ProviderLogo provider="claude" size="large" />);
    expect(container.querySelector(".provider-logo--large")).toHaveTextContent("Claude Code");
  });

  it("follows the provider when it changes", () => {
    const { container, rerender } = render(<ProviderLogo provider="claude" />);
    rerender(<ProviderLogo provider="opencode" />);
    expect(container).toHaveTextContent("opencode");
    expect(container).not.toHaveTextContent("Claude Code");
  });
});
