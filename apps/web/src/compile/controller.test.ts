import { describe, expect, it } from "vitest";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { CompileController } from "./controller.ts";

function setup(init: Parameters<typeof createFakeApi>[0] = {}) {
  const fake = createFakeApi(init);
  const controller = new CompileController({ api: fake.api });
  const unsubscribe = fake.api.subscribeEvents((event) => controller.handleEvent(event));
  return { fake, controller, unsubscribe };
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("CompileController", () => {
  it("starts a compile, follows its phases and ends with the result", async () => {
    const { fake, controller } = setup();
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({ running: true, queued: false });
    fake.compile.phase("downloading");
    expect(controller.getSnapshot().phase).toBe("downloading");
    fake.compile.finish({ pdfRev: "3" });
    expect(controller.getSnapshot()).toMatchObject({ running: false, pdfAvailable: true, last: { result: { pdfRev: "3" } } });
  });

  it("compiles a chosen file when asked to", async () => {
    const { fake, controller } = setup();
    await controller.start("chapters/one.tex");
    expect(fake.calls).toContain("startCompile chapters/one.tex");
  });

  it("queues exactly one follow-up when asked again while running", async () => {
    const { fake, controller } = setup();
    await controller.start();
    await controller.start();
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({ running: true, queued: true });
    fake.compile.finish();
    expect(controller.getSnapshot()).toMatchObject({ running: true, queued: false, runningId: "c3" });
  });

  it("cancels the running compile and drops the queue", async () => {
    const { fake, controller } = setup();
    await controller.start();
    await controller.start();
    await controller.cancel();
    expect(fake.calls).toContain("cancelCompile");
    expect(controller.getSnapshot()).toMatchObject({ running: false, queued: false, last: { result: { status: "cancelled" } } });
  });

  it("shows the server's message when the engine is missing", async () => {
    const { controller } = setup({ engineAvailable: false });
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({ running: false, problem: "The LaTeX engine (Tectonic) was not found." });
  });

  it("shows a message when the server cannot be reached", async () => {
    const { fake, controller } = setup();
    fake.failNext(apiError("network", "Cannot reach the Caztor server.", 0));
    await controller.start();
    expect(controller.getSnapshot().problem).toBe("Cannot reach the Caztor server.");
  });

  it("loads the status, including a preview that exists from an earlier server run", async () => {
    const { controller } = setup({ pdf: new Uint8Array([1]) });
    expect(controller.getSnapshot().pdfAvailable).toBe(false);
    await controller.refresh();
    expect(controller.getSnapshot()).toMatchObject({ pdfAvailable: true, running: false, last: null });
  });

  it("reloads the status after the event stream reconnected", async () => {
    const { fake, controller } = setup();
    fake.compile.status = { ...fake.compile.status, running: { compileId: "c9" } };
    fake.emit({ id: null, event: "stream_resumed", data: null });
    await settle();
    expect(controller.getSnapshot()).toMatchObject({ running: true, runningId: "c9" });
  });

  it("tells subscribers when something changed and stops after unsubscribing", async () => {
    const { controller } = setup();
    let calls = 0;
    const stop = controller.subscribe(() => (calls += 1));
    await controller.start();
    expect(calls).toBeGreaterThan(0);
    stop();
    const before = calls;
    await controller.start();
    expect(calls).toBe(before);
  });
});
