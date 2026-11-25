import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProviderLogo } from "./ProviderLogo.tsx";
import { PROVIDER_META } from "./providers.ts";

describe("ProviderLogo", () => {
  it("shows the logo image from this origin and does not repeat the name as text", () => {
    const { container } = render(<ProviderLogo provider="claude" />);
    const image = screen.getByRole("img", { name: PROVIDER_META.claude.name });
    expect(image.getAttribute("src")).toMatch(/claude.*\.svg(\?no-inline)?$/);
    expect(image.getAttribute("src")).not.toMatch(/^(https?:)?\/\//);
    expect(container.textContent).toBe("");
  });

  it("shows the name as text when the image fails to load", () => {
    const { container } = render(<ProviderLogo provider="claude" />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("img")).toBeNull();
    expect(container).toHaveTextContent(PROVIDER_META.claude.name);
  });

  it("shows the OpenAI mark, from this origin, as the logo of Codex, with one file for both color schemes", () => {
    expect(PROVIDER_META.codex.logo).not.toBeNull();
    const { container } = render(<ProviderLogo provider="codex" />);
    const image = screen.getByRole("img", { name: PROVIDER_META.codex.name });
    expect(image.getAttribute("src")).toMatch(/codex.*\.svg(\?no-inline)?$/);
    expect(image.getAttribute("src")).not.toMatch(/^(https?:)?\/\//);
    expect(container.querySelector("source")).toBeNull();
    expect(container.textContent).toBe("");
  });

  it("shows the name Codex as text when its logo fails to load", () => {
    const { container } = render(<ProviderLogo provider="codex" />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("img")).toBeNull();
    expect(container).toHaveTextContent("Codex");
  });

  it("offers the dark variant of a logo that has one to dark color schemes, with the light one as the image", () => {
    const { container } = render(<ProviderLogo provider="opencode" />);
    const source = container.querySelector("source")!;
    expect(source.getAttribute("media")).toBe("(prefers-color-scheme: dark)");
    expect(source.getAttribute("srcset")).toMatch(/dark.*\.svg(\?no-inline)?$/);
    expect(screen.getByRole("img").getAttribute("src")).toMatch(/light.*\.svg(\?no-inline)?$/);
  });

  it("tries the image again when the provider changes", () => {
    const { rerender } = render(<ProviderLogo provider="claude" />);
    fireEvent.error(screen.getByRole("img"));
    rerender(<ProviderLogo provider="opencode" />);
    expect(screen.getByRole("img", { name: PROVIDER_META.opencode.name })).toBeInTheDocument();
  });
});
