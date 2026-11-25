import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ProviderInfo } from "../api/types.ts";
import { ProviderSelect } from "./ProviderSelect.tsx";

const providers: ProviderInfo[] = [
  { id: "opencode", installed: true, requiresModel: true, model: null },
  { id: "claude", installed: true, requiresModel: false, model: null },
  { id: "pi", installed: false, unavailableReason: "pi is not installed.", requiresModel: false, model: null },
];

function setup(props: Partial<Parameters<typeof ProviderSelect>[0]> = {}) {
  const onSelect = vi.fn();
  render(<ProviderSelect providers={providers} selected="claude" disabled={false} onSelect={onSelect} {...props} />);
  return { onSelect, group: screen.getByRole("radiogroup", { name: "Provider" }) };
}

describe("ProviderSelect", () => {
  it("lists opencode, claude and pi, with the selected one checked", () => {
    setup();
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    expect(radios.map((radio) => radio.getAttribute("aria-checked"))).toEqual(["false", "true", "false"]);
  });

  it("marks an unavailable provider and gives the reason to assistive technology, but can still be chosen", async () => {
    const { onSelect } = setup();
    const pi = screen.getByRole("radio", { name: /^pi/i });
    expect(pi).toHaveAccessibleDescription(/not installed/i);
    await userEvent.click(pi);
    expect(onSelect).toHaveBeenCalledWith("pi");
  });

  it("switches provider by click and by arrow keys, with only the selected one in the tab order", async () => {
    const { onSelect } = setup();
    expect(screen.getAllByRole("radio").map((radio) => radio.getAttribute("tabindex"))).toEqual(["-1", "0", "-1"]);
    await userEvent.click(screen.getByRole("radio", { name: /opencode/i }));
    expect(onSelect).toHaveBeenLastCalledWith("opencode");
    screen.getByRole("radio", { name: /claude/i }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onSelect).toHaveBeenLastCalledWith("pi");
    await userEvent.keyboard("{ArrowLeft}");
    expect(onSelect).toHaveBeenLastCalledWith("opencode");
  });

  it("does not switch while disabled, as during a running turn", async () => {
    const { onSelect } = setup({ disabled: true });
    await userEvent.click(screen.getByRole("radio", { name: /opencode/i }));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getAllByRole("radio").every((radio) => radio.hasAttribute("disabled"))).toBe(true);
  });

  describe("Pi in place of Codex", () => {
    const all: ProviderInfo[] = [...providers.filter((provider) => provider.id !== "pi"), { id: "codex", installed: true, requiresModel: false, model: null }, { id: "antigravity", installed: true, requiresModel: false, model: null }, { id: "pi", installed: true, requiresModel: false, model: null }];

    it("shows opencode, Claude Code, Pi and Antigravity as radios, and neither Codex nor a More providers dropdown", () => {
      setup({ providers: all });
      expect(screen.getAllByRole("radio").map((radio) => radio.textContent)).toEqual(["opencode", "Claude Code", "Pi", "Antigravity"]);
      expect(screen.queryByRole("radio", { name: "Codex" })).toBeNull();
      expect(screen.queryByRole("combobox", { name: "More providers" })).toBeNull();
    });

    it("chooses Pi like any other provider, with the arrow keys too", async () => {
      const { onSelect } = setup({ providers: all, selected: "claude" });
      await userEvent.click(screen.getByRole("radio", { name: "Pi" }));
      expect(onSelect).toHaveBeenLastCalledWith("pi");
      screen.getByRole("radio", { name: "Claude Code" }).focus();
      await userEvent.keyboard("{ArrowRight}");
      expect(onSelect).toHaveBeenLastCalledWith("pi");
    });
  });
});
