import type { FileEntry, RelPath } from "@caztor/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { createFakeApi, type FakeApiInit } from "../testing/fake-api.ts";
import { FileTree } from "./FileTree.tsx";
import { MAX_UPLOAD_BYTES } from "./upload.ts";

const file = (path: string, size = 10): FileEntry => ({ path: path as RelPath, kind: "file", size });
const dir = (path: string): FileEntry => ({ path: path as RelPath, kind: "dir", size: 0 });
const PROJECT: FileEntry[] = [file("main.tex", 120), dir("figs")];

function setup(init: FakeApiInit = {}) {
  const fake = createFakeApi({ files: PROJECT, ...init });
  render(<FileTree api={fake.api} selectedPath={null} onOpen={() => {}} />);
  return { fake, user: userEvent.setup() };
}

const uploadCalls = (calls: string[]) => calls.filter((call) => call.startsWith("uploadFile"));
const input = () => screen.getByLabelText("Choose files to upload");

/** A file whose reported size is `size`, without allocating that many bytes. */
function sized(name: string, size: number, content = "data"): File {
  const upload = new File([content], name);
  Object.defineProperty(upload, "size", { value: size });
  return upload;
}

describe("uploading", () => {
  it("uploads a file into the project and lists it", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.upload(input(), new File(["\\bye"], "extra.tex"));

    expect(uploadCalls(fake.calls)).toEqual(["uploadFile extra.tex 4"]);
    expect(await screen.findByRole("button", { name: /^extra\.tex/ })).toBeInTheDocument();
  });

  it("uploads into the folder that was last selected", async () => {
    const { fake, user } = setup();
    await user.click(await screen.findByRole("button", { name: /^figs/ }));
    await user.upload(input(), new File(["x"], "plot.pdf"));

    expect(uploadCalls(fake.calls)).toEqual(["uploadFile figs/plot.pdf 1"]);
  });

  it("rejects a file over 20 MB without sending it", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.upload(input(), sized("big.bin", MAX_UPLOAD_BYTES + 1));

    expect(await screen.findByRole("alert")).toHaveTextContent("big.bin is larger than 20 MB and was not uploaded.");
    expect(uploadCalls(fake.calls)).toEqual([]);
  });

  it("accepts a file of exactly 20 MB", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.upload(input(), sized("limit.bin", MAX_UPLOAD_BYTES));

    expect(uploadCalls(fake.calls)).toHaveLength(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("rejects a name that already exists, without sending it, and leaves the existing file alone", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.upload(input(), new File(["replacement"], "main.tex"));

    expect(await screen.findByRole("alert")).toHaveTextContent('"main.tex" already exists. Choose another name.');
    expect(uploadCalls(fake.calls)).toEqual([]);
    expect(fake.state.files.find((entry) => entry.path === "main.tex")?.size).toBe(120);
  });

  it("shows the server's message when it rejects the upload, such as a name created in the meantime", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    fake.state.files.push(file("late.tex"));
    await user.upload(input(), new File(["x"], "late.tex"));

    expect(await screen.findByRole("alert")).toHaveTextContent('"late.tex" already exists. Choose another name.');
    expect(fake.state.files.find((entry) => entry.path === "late.tex")?.size).toBe(10);
  });

  it("uploads the good files of a selection and reports each rejected one", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.upload(input(), [new File(["a"], "one.tex"), sized("two.bin", MAX_UPLOAD_BYTES + 1), new File(["b"], "main.tex")]);

    expect(uploadCalls(fake.calls)).toEqual(["uploadFile one.tex 1"]);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("two.bin is larger than 20 MB and was not uploaded.");
    expect(alert).toHaveTextContent('"main.tex" already exists. Choose another name.');
    expect(await screen.findByRole("button", { name: /^one\.tex/ })).toBeInTheDocument();
  });
});
