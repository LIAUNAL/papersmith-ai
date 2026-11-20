import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CompileResult } from "../api/types.ts";
import { INITIAL_COMPILE_STATE, type CompileState } from "./compile-state.ts";
import { CompileToolbar } from "./CompileToolbar.tsx";

const result = (status: CompileResult["status"]): CompileResult => ({ status, pdfRev: null, diagnostics: [], durationMs: 5, logAvailable: true });
const engine = { available: true, version: "0.17.0" };

function show(state: Partial<CompileState> = {}, props: Partial<Parameters<typeof CompileToolbar>[0]> = {}) {
  const onCompile = vi.fn();
  const onCancel = vi.fn();
  render(<CompileToolbar state={{ ...INITIAL_COMPILE_STATE, ...state }} engine={engine} onCompile={onCompile} onCancel={onCancel} {...props} />);
  return { onCompile, onCancel };
}

describe("CompileToolbar", () => {
  it("offers to compile the open LaTeX file when it is not the main one", async () => {
    const onCompileFile = vi.fn();
    show({}, { currentFile: "chapters/one.tex", mainFile: "main/main.tex", onCompileFile });
    await userEvent.click(screen.getByRole("button", { name: "Compile one.tex" }));
    expect(onCompileFile).toHaveBeenCalledWith("chapters/one.tex");
    expect(screen.getByRole("button", { name: "Compile one.tex" })).toHaveAttribute("title", "Compile chapters/one.tex instead of the main file");
  });

  it.each([
    ["the open file is the main one", "main/main.tex", "main/main.tex"],
    ["no main is set and the open file is main.tex", "main.tex", null],
    ["the open file is not LaTeX", "refs.bib", null],
    ["no file is open", null, null],
  ])("does not offer it when %s", (_label, currentFile, mainFile) => {
    show({}, { currentFile, mainFile, onCompileFile: vi.fn() });
    expect(screen.queryByRole("button", { name: /^Compile .+/ })).toBeNull();
  });

  it("does not offer it while a compile runs", () => {
    show({ running: true, phase: "typesetting" }, { currentFile: "chapters/one.tex", mainFile: null, onCompileFile: vi.fn() });
    expect(screen.queryByRole("button", { name: "Compile one.tex" })).toBeNull();
  });

  it("offers Compile when idle and asks for a compile when clicked", async () => {
    const { onCompile, onCancel } = show();
    await userEvent.click(screen.getByRole("button", { name: "Compile" }));
    expect(onCompile).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Not compiled yet");
  });

  it("turns the button into Cancel while a compile runs", async () => {
    const { onCompile, onCancel } = show({ running: true, phase: "typesetting" });
    expect(screen.queryByRole("button", { name: "Compile" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onCompile).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Compiling");
  });

  it("shows the first-run download as its own state, different from compiling", () => {
    show({ running: true, phase: "downloading" });
    expect(screen.getByRole("status")).toHaveTextContent("Preparing: downloading support files");
    expect(screen.getByRole("status")).not.toHaveTextContent(/^Compiling/);
  });

  it("says a follow-up is queued", () => {
    show({ running: true, queued: true, phase: "typesetting" });
    expect(screen.getByRole("status")).toHaveTextContent("Compiling, another compile is queued");
  });

  it("shows the outcome of the last compile when idle", () => {
    show({ last: { compileId: "c1", result: result("failed-with-errors") } });
    expect(screen.getByRole("status")).toHaveTextContent("Compiled with errors");
  });

  it("disables Compile and explains why when the engine is missing", () => {
    show({}, { engine: { available: false } });
    expect(screen.getByRole("button", { name: "Compile" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("LaTeX engine not found");
  });
});
