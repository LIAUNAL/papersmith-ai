import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { CompileOptions } from "./CompileOptions.tsx";
import { useSettings } from "./useSettings.ts";
import type { ApiClient, Capability, Settings } from "../api/types.ts";

function Harness({ api, initial, sandbox }: { api: ApiClient; initial: Settings; sandbox: Capability }) {
  const { settings, change } = useSettings(api, initial);
  return <CompileOptions settings={settings} sandbox={sandbox} onChange={change} />;
}

function setup(settings: Partial<Settings> = {}, sandbox: Capability = { available: false }) {
  const fake = createFakeApi({ settings });
  render(<Harness api={fake.api} initial={fake.state.settings} sandbox={sandbox} />);
  return fake;
}

const SANDBOX = "Sandboxed compile (experimental)";

describe("CompileOptions", () => {
  it("shows stop-on-first-error off and auto-compile on by default", () => {
    setup();
    expect(screen.getByRole("checkbox", { name: "Stop on first error" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Auto-compile" })).toBeChecked();
  });

  it("saves a changed value through the settings route and shows it", async () => {
    const fake = setup();
    await userEvent.click(screen.getByRole("checkbox", { name: "Stop on first error" }));
    expect(screen.getByRole("checkbox", { name: "Stop on first error" })).toBeChecked();
    expect(fake.calls).toContain('patchSettings {"stopOnFirstError":true}');
    expect(fake.state.settings.stopOnFirstError).toBe(true);
  });

  it("turns auto-compile off and persists it", async () => {
    const fake = setup();
    await userEvent.click(screen.getByRole("checkbox", { name: "Auto-compile" }));
    expect(screen.getByRole("checkbox", { name: "Auto-compile" })).not.toBeChecked();
    expect(fake.calls).toContain('patchSettings {"autoCompile":false}');
  });

  it("restores the saved values when the page is opened again", () => {
    setup({ stopOnFirstError: true, autoCompile: false });
    expect(screen.getByRole("checkbox", { name: "Stop on first error" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Auto-compile" })).not.toBeChecked();
  });

  it("goes back to the old value and says so when saving fails", async () => {
    const fake = setup();
    fake.failNext(apiError("network", "The server is not reachable.", 0));
    await userEvent.click(screen.getByRole("checkbox", { name: "Stop on first error" }));
    expect(screen.getByRole("checkbox", { name: "Stop on first error" })).not.toBeChecked();
    expect(await screen.findByRole("alert")).toHaveTextContent("The server is not reachable.");
  });

  describe("sandboxed compile", () => {
    it("is not offered when the sandbox is not available", () => {
      setup();
      expect(screen.queryByRole("checkbox", { name: SANDBOX })).toBeNull();
    });

    it("is offered, off, when the sandbox is available, and saved per project when turned on", async () => {
      const fake = setup({}, { available: true, version: "bubblewrap, Tectonic 0.17.0" });
      const box = screen.getByRole("checkbox", { name: SANDBOX });
      expect(box).not.toBeChecked();
      await userEvent.click(box);
      expect(screen.getByRole("checkbox", { name: SANDBOX })).toBeChecked();
      expect(fake.calls).toContain('patchSettings {"sandboxedCompile":true}');
    });

    it("stays visible when it is on but no longer available, so it can be turned off, and says why it cannot start", async () => {
      const fake = setup({ sandboxedCompile: true }, { available: false, reason: "Unprivileged user namespaces are not available." });
      expect(screen.getByRole("checkbox", { name: SANDBOX })).toBeChecked();
      expect(screen.getByText(/user namespaces are not available/i)).toBeInTheDocument();
      await userEvent.click(screen.getByRole("checkbox", { name: SANDBOX }));
      expect(fake.state.settings.sandboxedCompile).toBe(false);
    });
  });
});
