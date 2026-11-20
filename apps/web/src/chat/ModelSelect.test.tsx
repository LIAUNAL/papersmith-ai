import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ProviderInfo } from "../api/types.ts";
import { ModelSelect } from "./ModelSelect.tsx";

const base: ProviderInfo = { id: "claude", installed: true, requiresModel: false, model: null };

function setup(provider: ProviderInfo, props: Partial<Parameters<typeof ModelSelect>[0]> = {}) {
  const onChange = vi.fn<(model: string | null) => Promise<string | null>>(async () => null);
  render(<ModelSelect provider={provider} disabled={false} onChange={onChange} {...props} />);
  return { onChange };
}

describe("ModelSelect", () => {
  it("has no Default entry when the provider names its default model, and shows that model until another is chosen", async () => {
    const { onChange } = setup({ ...base, models: ["claude-opus-5-5", "claude-sonnet-5-5"], defaultModel: "claude-sonnet-5-5" });
    const select = screen.getByRole("combobox", { name: "Model" });
    expect(select).toHaveValue("claude-sonnet-5-5");
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["claude-opus-5-5", "claude-sonnet-5-5"]);
    await userEvent.selectOptions(select, "claude-opus-5-5");
    expect(onChange).toHaveBeenCalledWith("claude-opus-5-5");
  });

  it("is a list when the CLI offers models, with the default first, and reports a choice", async () => {
    const { onChange } = setup({ ...base, models: ["sonnet", "opus"], model: "sonnet" });
    const select = screen.getByRole("combobox", { name: "Model" });
    expect(select).toHaveValue("sonnet");
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["Default", "sonnet", "opus"]);
    await userEvent.selectOptions(select, "opus");
    expect(onChange).toHaveBeenCalledWith("opus");
    await userEvent.selectOptions(select, "Default");
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("is a text box when the CLI lists no models; Enter and the Set button save, an emptied box clears", async () => {
    const { onChange } = setup({ ...base, model: "claude-x" });
    const box = screen.getByRole("textbox", { name: "Model" });
    expect(box).toHaveValue("claude-x");
    await userEvent.clear(box);
    await userEvent.type(box, "sonnet{Enter}");
    expect(onChange).toHaveBeenLastCalledWith("sonnet");
    await userEvent.clear(box);
    await userEvent.click(screen.getByRole("button", { name: "Set model" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("offers Set only when the text differs from the saved model", async () => {
    setup({ ...base, model: "sonnet" });
    expect(screen.getByRole("button", { name: "Set model" })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Model" }), "x");
    expect(screen.getByRole("button", { name: "Set model" })).toBeEnabled();
  });

  it("says that a provider needs a model before it can start a turn", () => {
    setup({ id: "opencode", installed: true, requiresModel: true, model: null });
    expect(screen.getByText(/needs a model/i)).toBeInTheDocument();
  });

  it("shows the server's reason when it rejects the model, and keeps the typed text", async () => {
    const onChange = vi.fn(async () => "A model name cannot start with a dash.");
    render(<ModelSelect provider={base} disabled={false} onChange={onChange} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Model" }), "--bad{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot start with a dash");
    expect(screen.getByRole("textbox", { name: "Model" })).toHaveValue("--bad");
  });

  it("is disabled while a turn runs", () => {
    setup({ ...base, models: ["sonnet"] }, { disabled: true });
    expect(screen.getByRole("combobox", { name: "Model" })).toBeDisabled();
  });
});
