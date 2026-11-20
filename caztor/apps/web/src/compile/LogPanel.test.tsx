import type { RelPath } from "@caztor/core";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CompileResult, Diagnostic } from "../api/types.ts";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { LogPanel } from "./LogPanel.tsx";
import { MAX_SHOWN_LOG_CHARS } from "./log-text.ts";

const diag = (extra: Partial<Diagnostic> & Pick<Diagnostic, "severity" | "message">): Diagnostic => ({ file: null, line: null, source: "stderr", ...extra });
const error = (file: string, line: number, message: string, extra: Partial<Diagnostic> = {}) =>
  diag({ severity: "error", file: file as RelPath, line, message, ...extra });
const result = (diagnostics: Diagnostic[], extra: Partial<CompileResult> = {}): CompileResult => ({
  status: diagnostics.some((entry) => entry.severity === "error") ? "failed-with-errors" : "success",
  pdfRev: "1",
  diagnostics,
  durationMs: 5,
  logAvailable: true,
  ...extra,
});

function setup(diagnostics: Diagnostic[] | null, options: { onOpen?: (file: string, line: number) => Promise<string | null>; log?: string | null; resultExtra?: Partial<CompileResult> } = {}) {
  const fake = createFakeApi();
  fake.compile.log = options.log === undefined ? "This is XeTeX\n! Undefined control sequence." : options.log;
  const onOpen = options.onOpen ?? vi.fn(async () => null);
  const props = (compileId: string, list: Diagnostic[] | null) => ({
    api: fake.api,
    last: list === null ? null : { compileId, result: result(list, options.resultExtra) },
    running: false,
    onOpen,
  });
  const view = render(<LogPanel {...props("c1", diagnostics)} />);
  return { fake, onOpen, view, again: (compileId: string, list: Diagnostic[] | null) => view.rerender(<LogPanel {...props(compileId, list)} />) };
}

describe("LogPanel entries", () => {
  it("asks for a compile before there is a result", () => {
    setup(null);
    expect(screen.getByText("Compile the project to see errors and warnings here.")).toBeInTheDocument();
  });

  it("says nothing was found after a clean compile", () => {
    setup([]);
    expect(screen.getByText("No errors or warnings.")).toBeInTheDocument();
  });

  it("counts errors and warnings in the header", () => {
    setup([error("a.tex", 1, "Bad"), error("a.tex", 2, "Worse"), diag({ severity: "warning", message: "Meh" })]);
    expect(screen.getByRole("button", { name: /Log/ })).toHaveTextContent("2 errors");
    expect(screen.getByRole("button", { name: /Log/ })).toHaveTextContent("1 warning");
  });

  it("uses the singular for one error and omits a zero count", () => {
    setup([error("a.tex", 1, "Bad")]);
    const header = screen.getByRole("button", { name: /Log/ });
    expect(header).toHaveTextContent("1 error");
    expect(header).not.toHaveTextContent("warning");
  });

  it("lists each diagnostic with its severity, message and location", () => {
    setup([error("chapter.tex", 7, "Undefined control sequence"), diag({ severity: "warning", file: "main.tex" as RelPath, line: 12, message: "Overfull \\hbox" })]);
    const list = screen.getByRole("list", { name: "Errors and warnings" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Error");
    expect(items[0]).toHaveTextContent("Undefined control sequence");
    expect(items[0]).toHaveTextContent("chapter.tex:7");
    expect(items[1]).toHaveTextContent("Warning");
    expect(items[1]).toHaveTextContent("main.tex:12");
  });

  it("shows the detail of a diagnostic", () => {
    setup([error("a.tex", 4, "Undefined control sequence", { detail: "halted on potentially-recoverable error as specified" })]);
    expect(screen.getByText("halted on potentially-recoverable error as specified")).toBeInTheDocument();
  });

  it("lists a diagnostic without a file or line, with no jump action", () => {
    setup([diag({ severity: "error", message: "Could not download LaTeX support files. The first compile needs a network connection." }), error("a.tex", 3, "Bad")]);
    expect(screen.getByText(/Could not download LaTeX support files/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Go to / })).toHaveLength(1);
  });

  it("gives a diagnostic with a file but no line no jump action either", () => {
    setup([diag({ severity: "warning", file: "a.tex" as RelPath, message: "Package warning" })]);
    expect(screen.getByText("Package warning")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Go to / })).toBeNull();
  });

  it("renders the biblatex notice and the outside-project read warning as readable messages", () => {
    setup([
      diag({ severity: "warning", source: "caztor", message: "This project uses biblatex, which needs biber. Biber is not supported; use BibTeX (\\bibliography) instead." }),
      diag({ severity: "warning", source: "log", message: "The document reads a file outside the project: /home/me/notes/macros.tex" }),
    ]);
    expect(screen.getByText(/This project uses biblatex, which needs biber/)).toBeInTheDocument();
    expect(screen.getByText("The document reads a file outside the project: /home/me/notes/macros.tex")).toBeInTheDocument();
    expect(screen.queryAllByRole("button", { name: /^Go to / })).toHaveLength(0);
  });
});

describe("LogPanel jumping", () => {
  it("opens the file at the line when an entry is clicked", async () => {
    const { onOpen } = setup([error("chapter.tex", 7, "Undefined control sequence")]);
    await userEvent.click(screen.getByRole("button", { name: "Go to chapter.tex line 7" }));
    expect(onOpen).toHaveBeenCalledWith("chapter.tex", 7);
  });

  it("jumps to the clicked entry, not to another one", async () => {
    const { onOpen } = setup([error("a.tex", 1, "First"), error("sections/b.tex", 22, "Second")]);
    await userEvent.click(screen.getByRole("button", { name: "Go to sections/b.tex line 22" }));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenCalledWith("sections/b.tex", 22);
  });

  it("says so when the file cannot be opened", async () => {
    setup([error("gone.tex", 2, "Bad")], { onOpen: async () => "\"gone.tex\" was not found." });
    await userEvent.click(screen.getByRole("button", { name: "Go to gone.tex line 2" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("\"gone.tex\" was not found.");
  });
});

describe("LogPanel raw log", () => {
  it("shows the raw log on request, and hides it again", async () => {
    const { fake } = setup([error("a.tex", 1, "Bad")]);
    expect(screen.queryByText(/This is XeTeX/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show raw log" }));
    expect(await screen.findByText(/This is XeTeX/)).toBeInTheDocument();
    expect(fake.calls).toContain("readLog");
    await userEvent.click(screen.getByRole("button", { name: "Show errors and warnings" }));
    expect(screen.queryByText(/This is XeTeX/)).toBeNull();
    expect(screen.getByRole("list", { name: "Errors and warnings" })).toBeInTheDocument();
  });

  it("shows only the end of a huge log and says that the rest is not shown", async () => {
    setup([error("a.tex", 1, "Bad")], { log: `${"noise\n".repeat(100_000)}THE LAST LINE` });
    await userEvent.click(screen.getByRole("button", { name: "Show raw log" }));
    const shown = await screen.findByLabelText("Raw compile log");
    expect(shown.textContent?.endsWith("THE LAST LINE")).toBe(true);
    expect(shown.textContent?.length).toBeLessThanOrEqual(MAX_SHOWN_LOG_CHARS);
    expect(screen.getByText(/Showing the last 200,000 characters of 600,013/)).toBeInTheDocument();
  });

  it("reloads the raw log after another compile", async () => {
    const { fake, again } = setup([error("a.tex", 1, "Bad")]);
    await userEvent.click(screen.getByRole("button", { name: "Show raw log" }));
    expect(await screen.findByText(/Undefined control sequence\./)).toBeInTheDocument();
    fake.compile.log = "second run output";
    await act(async () => again("c2", []));
    expect(await screen.findByText("second run output")).toBeInTheDocument();
  });

  it("explains a missing log", async () => {
    const { fake } = setup([], { log: null });
    fake.failNext(apiError("no_log", "There is no compile log yet.", 404));
    await userEvent.click(screen.getByRole("button", { name: "Show raw log" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("There is no compile log yet.");
  });

  it("does not offer the raw log when the run kept none", () => {
    setup([error("a.tex", 1, "Bad")], { resultExtra: { logAvailable: false } });
    expect(screen.getByRole("button", { name: "Show raw log" })).toBeDisabled();
  });
});

describe("LogPanel folding", () => {
  it("is open at first and the header folds and unfolds it", async () => {
    setup([error("a.tex", 1, "Bad")]);
    const header = screen.getByRole("button", { name: /Log/ });
    expect(header).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list", { name: "Errors and warnings" })).toBeNull();
    await userEvent.click(header);
    expect(screen.getByRole("list", { name: "Errors and warnings" })).toBeInTheDocument();
  });

  it("opens again by itself when a compile ends with errors", async () => {
    const { again } = setup([]);
    await userEvent.click(screen.getByRole("button", { name: /Log/ }));
    expect(screen.getByRole("button", { name: /Log/ })).toHaveAttribute("aria-expanded", "false");
    await act(async () => again("c2", [error("a.tex", 1, "Bad")]));
    expect(screen.getByRole("button", { name: /Log/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("stays folded when a compile ends with warnings only", async () => {
    const { again } = setup([]);
    await userEvent.click(screen.getByRole("button", { name: /Log/ }));
    await act(async () => again("c2", [diag({ severity: "warning", message: "Meh" })]));
    expect(screen.getByRole("button", { name: /Log/ })).toHaveAttribute("aria-expanded", "false");
  });
});
