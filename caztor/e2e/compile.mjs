// Real-browser, real-server, real-tectonic check of the compile UI. Needs the web app built, tectonic installed and
// its package bundle cached (the first compile downloads it otherwise). Screenshots go to $CAZTOR_E2E_OUT (default: the
// system temp folder) and are not meant to be committed.
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadPlaywright, makeProject, openApp, startServer } from "./lib.mjs";

const outDir = process.env.CAZTOR_E2E_OUT ?? mkdtempSync(join(tmpdir(), "caztor-shots-"));
mkdirSync(outDir, { recursive: true });
const { chromium } = await loadPlaywright();

const paragraphs = Array.from({ length: 160 }, (_, i) => `Paragraph ${i + 1}: the quick brown fox jumps over the lazy dog while citing \\cite{knuth} again and again to fill the page with text.\n`);
const intro = ["\\section{Introduction}\n", ...paragraphs.slice(0, 80), "\\section{Methods}\n", ...paragraphs.slice(80)].join("\n");
const mainTex = "\\documentclass{article}\n\\begin{document}\n\\title{Caztor check}\\author{E2E}\\maketitle\n\\input{sections/intro}\n\\bibliographystyle{plain}\n\\bibliography{refs}\n\\end{document}\n";
const refs = "@book{knuth, author={Donald Knuth}, title={The TeXbook}, publisher={Addison-Wesley}, year={1984}}\n";

const dir = makeProject({ "main.tex": mainTex, "refs.bib": refs });
mkdirSync(join(dir, "sections"));
writeFileSync(join(dir, "sections", "intro.tex"), intro);
const server = await startServer(dir);
const browser = await chromium.launch();
let failed = false;
const results = [];
const check = (name, ok, detail = "") => {
  results.push(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` (${detail})` : ""}`);
  console.log(results.at(-1));
  if (!ok) failed = true;
};
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

try {
  const { page, problems } = await openApp(browser, server.url);
  globalThis.__shot = () => page.screenshot({ path: join(outDir, "99-failure.png") });
  const preview = page.getByRole("region", { name: "PDF preview" });
  const status = () => preview.locator(".compile-toolbar__status").innerText();
  const waitIdle = async (ms = 120000) => preview.getByRole("button", { name: "Compile", exact: true }).waitFor({ timeout: ms });
  // A short compile can finish before a poll sees the transient "Cancel" button, so runs are counted by a page-side
  // observer that never misses a commit; the checks wait for that durable count and for the resulting state.
  const installRunCounter = () =>
    page.evaluate(() => {
      window.__runsStarted = 0;
      let running = false;
      const isRunning = () => [...document.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Cancel");
      new MutationObserver(() => {
        const now = isRunning();
        if (now && !running) window.__runsStarted += 1;
        running = now;
      }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    });
  const runsStarted = () => page.evaluate(() => window.__runsStarted);
  const waitForRun = (after, timeout = 8000) =>
    page.waitForFunction((count) => window.__runsStarted > count, after, { timeout }).then(
      () => true,
      () => false,
    );
  const waitForStatus = (pattern, timeout = 20000) =>
    page
      .waitForFunction(
        ({ source, flags }) => new RegExp(source, flags).test(document.querySelector(".compile-toolbar__status")?.textContent ?? ""),
        { source: pattern.source, flags: pattern.flags },
        { timeout },
      )
      .then(
        () => true,
        () => false,
      );
  const pageCount = () => page.locator(".pdf-viewer__page").count();
  const inkOnCanvas = () =>
    page.evaluate(() => {
      const canvas = document.querySelector(".pdf-viewer__canvas");
      if (!(canvas instanceof HTMLCanvasElement) || canvas.width === 0) return 0;
      const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      let dark = 0;
      for (let i = 0; i < data.length; i += 4) if (data[i] < 170 && data[i + 3] > 0) dark += 1;
      return dark;
    });

  await installRunCounter();

  // 2. Compile: running, then success, then the PDF on canvas.
  check("empty state before the first compile", (await preview.getByText("No preview yet").count()) === 1);
  await page.screenshot({ path: join(outDir, "01-empty.png") });
  let runs = await runsStarted();
  await preview.getByRole("button", { name: "Compile", exact: true }).click();
  check("a compile started (the button became Cancel)", await waitForRun(runs), `${await runsStarted()} runs`);
  await waitIdle();
  check("status after the run", await waitForStatus(/^Compiled/), await status());
  await page.locator(".pdf-viewer__canvas").first().waitFor({ timeout: 15000 });
  await pause(500);
  const pages = await pageCount();
  check("the PDF has several pages", pages >= 3, `${pages} pages`);
  const ink = await inkOnCanvas();
  check("the first page has text drawn on the canvas", ink > 500, `${ink} dark pixels`);
  await page.screenshot({ path: join(outDir, "02-compiled-light.png") });

  // 4. Zoom, scroll to page 2, recompile: zoom and scroll are kept.
  await preview.getByRole("button", { name: "Zoom in" }).click();
  await preview.getByRole("button", { name: "Zoom in" }).click();
  const zoomLabel = await preview.locator(".preview__percent").innerText();
  await page.evaluate(() => {
    const scroller = document.querySelector(".pdf-viewer");
    const second = document.querySelector('.pdf-viewer__page[data-page="2"]');
    scroller.scrollTop = second.offsetTop + 120;
  });
  await pause(800);
  const before = await page.evaluate(() => document.querySelector(".pdf-viewer").scrollTop);
  runs = await runsStarted();
  await preview.getByRole("button", { name: "Compile", exact: true }).click();
  await waitForRun(runs, 5000);
  await waitIdle();
  await pause(1500);
  const after = await page.evaluate(() => document.querySelector(".pdf-viewer").scrollTop);
  const labelAfter = await preview.locator(".preview__percent").innerText();
  check("zoom kept across a recompile", labelAfter === zoomLabel, `${zoomLabel} -> ${labelAfter}`);
  check("scroll position kept across a recompile", Math.abs(after - before) < 4 && before > 500, `${before} -> ${after}`);
  check("the reloaded pages are drawn", (await inkOnCanvas()) > 0);
  await page.screenshot({ path: join(outDir, "03-zoomed-page2.png") });

  // 5. Cancel a running compile.
  const original = readFileSync(join(dir, "main.tex"), "utf8");
  writeFileSync(join(dir, "main.tex"), original.replace("\\begin{document}", "\\begin{document}\n\\count1=0 \\loop \\advance\\count1 by 1 \\ifnum\\count1<2000000000 \\repeat\n"));
  await pause(1500);
  await preview.getByRole("button", { name: "Compile", exact: true }).click();
  await preview.getByRole("button", { name: "Cancel" }).waitFor({ timeout: 5000 });
  await pause(1500);
  check("still compiling after a pause", (await preview.getByRole("button", { name: "Cancel" }).count()) === 1, await status());
  await preview.getByRole("button", { name: "Cancel" }).click();
  await waitIdle(20000);
  check("cancel ends the run", /cancelled/i.test(await status()), await status());
  check("the previous PDF is still shown and marked out of date", (await pageCount()) >= 3 && (await preview.getByText(/Out of date/).count()) === 1);
  await page.screenshot({ path: join(outDir, "04-cancelled.png") });
  writeFileSync(join(dir, "main.tex"), original);
  await pause(1500);

  // 6 and 7. Auto-compile after a save, and an external edit right after the app's own save (watcher).
  const editor = page.getByRole("region", { name: "LaTeX editor" });
  await page.getByRole("button", { name: /^intro\.tex/ }).click();
  const box = editor.getByRole("textbox", { name: "sections/intro.tex" });
  await box.waitFor();
  const goTo = async (line) => {
    await box.click();
    await page.keyboard.press("Control+Home");
    for (let i = 1; i < line; i += 1) await page.keyboard.press("ArrowDown");
    await page.keyboard.press("End");
  };
  await goTo(5);
  runs = await runsStarted();
  await page.keyboard.type(" extra words");
  await editor.getByText("Saved", { exact: true }).waitFor({ timeout: 5000 });
  const savedAt = Date.now();
  writeFileSync(join(dir, "sections", "intro.tex"), readFileSync(join(dir, "sections", "intro.tex"), "utf8").replace("Paragraph 3:", "EXTERNAL EDIT 3:"));
  await box.getByText("EXTERNAL EDIT 3:").waitFor({ timeout: 5000 });
  const reloadMs = Date.now() - savedAt;
  check("an external edit right after the app's own save reaches the editor within about a second", reloadMs < 1500, `${reloadMs} ms`);
  check("auto-compile started after the save", await waitForRun(runs), await status());
  await waitIdle();
  check("auto-compile finished", await waitForStatus(/^Compiled/), await status());

  // Stop on first error: a failed run keeps the last good PDF, marked out of date.
  await preview.getByRole("checkbox", { name: "Stop on first error" }).check();
  await goTo(6);
  runs = await runsStarted();
  await page.keyboard.type(" \\undefinedcontrolsequence");
  await editor.getByText("Saved", { exact: true }).waitFor({ timeout: 5000 });
  // The halting compile can end before any poll sees "Cancel"; wait for the state it leaves behind instead.
  await waitForRun(runs);
  check("a run with an error and stop-on-first-error ends as failed", await waitForStatus(/failed/i), await status());
  await waitIdle();
  check("the last good PDF stays visible", (await pageCount()) >= 3 && (await inkOnCanvas()) > 0);
  await preview.getByText(/Out of date/).waitFor({ timeout: 5000 }).catch(() => {});
  check("it is marked out of date", (await preview.getByText(/Out of date/).count()) === 1);
  await page.screenshot({ path: join(outDir, "05-failed-out-of-date.png") });

  // 3. The log panel: the error with file and line, click-to-line, the raw log.
  const logPanel = preview.getByRole("group", { name: "Compile log" });
  const entryButton = logPanel.getByRole("button", { name: /^Go to sections\/intro\.tex line \d+$/ }).first();
  console.log("LOG PANEL:", (await logPanel.innerText()).replace(/\s+/g, " "));
  check("the log panel lists the error with its file and line", (await entryButton.count()) >= 1, (await logPanel.innerText()).replace(/\s+/g, " ").slice(0, 160));
  check("the log header counts the error", /1 error/.test(await logPanel.getByRole("button", { name: /^Log/ }).innerText()));
  const errorLine = Number(/line (\d+)$/.exec((await entryButton.getAttribute("aria-label")) ?? "")?.[1]);
  await page.getByRole("button", { name: /^main\.tex/ }).click();
  await editor.getByRole("textbox", { name: "main.tex" }).waitFor();
  await entryButton.click();
  await editor.getByRole("textbox", { name: "sections/intro.tex" }).waitFor();
  await pause(300);
  const gutter = await page.locator(".cm-activeLineGutter").first().innerText();
  const activeText = await page.locator(".cm-activeLine").first().innerText();
  check("clicking the error opens its file with the cursor on that line", Number(gutter) === errorLine && /undefinedcontrolsequence/.test(activeText), `line ${gutter} of ${errorLine}: ${activeText.slice(0, 50)}`);
  check("the editor has focus after the jump", await page.evaluate(() => document.activeElement?.classList.contains("cm-content") ?? false));
  await logPanel.getByRole("button", { name: "Show raw log" }).click();
  const rawLog = await logPanel.getByLabel("Raw compile log").innerText();
  check("the raw log can be read", /undefinedcontrolsequence|Undefined control sequence/i.test(rawLog) || rawLog.length > 50, `${rawLog.length} characters`);
  await page.screenshot({ path: join(outDir, "06-log-raw.png") });
  await logPanel.getByRole("button", { name: "Show errors and warnings" }).click();
  await page.screenshot({ path: join(outDir, "07-log-panel.png") });

  // Persistence of the switches and the zoom after a reload.
  await preview.getByRole("checkbox", { name: "Auto-compile" }).uncheck();
  await pause(500);
  await page.reload({ waitUntil: "load" });
  await page.getByRole("region", { name: "PDF preview" }).waitFor();
  await installRunCounter();
  check("stop-on-first-error is remembered", await page.getByRole("checkbox", { name: "Stop on first error" }).isChecked());
  check("auto-compile off is remembered", !(await page.getByRole("checkbox", { name: "Auto-compile" }).isChecked()));
  await page.locator(".pdf-viewer__canvas").first().waitFor({ timeout: 15000 });
  check("the preview that exists on the server is shown after a reload, with no compile", (await pageCount()) >= 3);
  check("zoom is remembered after a reload", (await page.locator(".preview__percent").innerText()) === zoomLabel, await page.locator(".preview__percent").innerText());
  check("scroll is remembered after a reload", Math.abs((await page.evaluate(() => document.querySelector(".pdf-viewer").scrollTop)) - before) < 4);

  // 8. The whole app with a compiled PDF, in the light and the dark theme.
  writeFileSync(join(dir, "sections", "intro.tex"), intro);
  await pause(1500);
  await page.getByRole("checkbox", { name: "Stop on first error" }).uncheck();
  await page.getByRole("button", { name: /^intro\.tex/ }).click();
  runs = await runsStarted();
  await preview.getByRole("button", { name: "Compile", exact: true }).click();
  await waitForRun(runs, 5000);
  await waitIdle();
  await pause(1500);
  check("a clean compile after the fix", await waitForStatus(/^Compiled/), await status());
  await preview.getByRole("button", { name: "Fit width" }).click();
  await pause(800);
  await page.screenshot({ path: join(outDir, "08-final-light.png") });
  await page.emulateMedia({ colorScheme: "dark" });
  await pause(800);
  await page.screenshot({ path: join(outDir, "09-final-dark.png") });

  console.log(`\nScreenshots: ${outDir}`);
  check("no console errors or CSP violations", problems.length === 0, problems.join(" | "));
} catch (error) {
  await globalThis.__shot?.().catch(() => {});
  console.log(`\nFAILED: ${String(error).split("\n")[0]}`);
  failed = true;
} finally {
  await browser.close();
  await server.stop();
}
console.log(failed ? "\nSOME CHECKS FAILED" : "\nALL CHECKS PASSED");
process.exit(failed ? 1 : 0);
