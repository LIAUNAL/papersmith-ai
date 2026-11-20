import type { FileEntry, RelPath } from "@caztor/core";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createFakeApi } from "../testing/fake-api.ts";
import { FileTree } from "./FileTree.tsx";

const file = (path: string, size = 10): FileEntry => ({ path: path as RelPath, kind: "file", size });
const listCalls = (calls: string[]) => calls.filter((call) => call === "listFiles").length;

function setup() {
  const fake = createFakeApi({ files: [file("main.tex")] });
  const view = render(<FileTree api={fake.api} selectedPath={null} onOpen={() => {}} />);
  return { fake, view };
}

describe("refreshing on server events", () => {
  it("lists the files again when a file changed on disk", async () => {
    const { fake } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    fake.state.files.push(file("added-by-agent.tex"));

    act(() => fake.emit({ id: 1, event: "file_changed", data: { path: "added-by-agent.tex", hash: "sha256:x" } }));
    expect(await screen.findByRole("button", { name: /^added-by-agent\.tex/ })).toBeInTheDocument();
    expect(listCalls(fake.calls)).toBe(2);
  });

  it("drops an entry that disappeared on disk", async () => {
    const { fake } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    fake.state.files = [];

    act(() => fake.emit({ id: 1, event: "file_changed", data: { path: "main.tex", hash: null } }));
    expect(await screen.findByText("This project has no files yet")).toBeInTheDocument();
  });

  it("lists again after the stream was re-established, because events may have been missed", async () => {
    const { fake } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    act(() => fake.emit({ id: null, event: "stream_resumed", data: null }));
    await screen.findByRole("button", { name: /^main\.tex/ });
    expect(listCalls(fake.calls)).toBe(2);
  });

  it("ignores events that do not concern files", async () => {
    const { fake } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    act(() => fake.emit({ id: 2, event: "compile.started", data: {} }));
    expect(listCalls(fake.calls)).toBe(1);
  });

  it("merges a burst of changes into one more listing", async () => {
    const { fake } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    act(() => {
      for (let id = 1; id <= 5; id++) fake.emit({ id, event: "file_changed", data: { path: "main.tex", hash: "sha256:x" } });
    });
    await screen.findByRole("button", { name: /^main\.tex/ });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(listCalls(fake.calls)).toBeLessThanOrEqual(3);
    expect(listCalls(fake.calls)).toBeGreaterThanOrEqual(2);
  });

  it("stops listening when the tree goes away", async () => {
    const { fake, view } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    expect(fake.subscribers()).toBe(1);
    view.unmount();
    expect(fake.subscribers()).toBe(0);
  });
});
