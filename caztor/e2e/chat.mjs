// Real-browser, real-server check of the chat. By default the providers are scripted fakes (no tokens are spent) that
// really edit the project files. With CAZTOR_E2E_REAL=1 the real Claude Code runs instead and the script makes exactly
// two turns (one edit, then undo); the cost is printed from the server's `done` event. Screenshots go to
// $CAZTOR_E2E_OUT (default: the system temp folder) and are not meant to be committed.
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadPlaywright, makeProject, openApp, startServer } from "./lib.mjs";

const real = process.env.CAZTOR_E2E_REAL === "1";
// Which real provider the real run uses: claude (default) or opencode (needs CAZTOR_E2E_MODEL, for example openai/gpt-5.5).
const realProvider = process.env.CAZTOR_E2E_PROVIDER ?? "claude";
const providerNames = { claude: "Claude Code", opencode: "opencode", codex: "Codex", antigravity: "Antigravity", pi: "Pi" };
const outDir = process.env.CAZTOR_E2E_OUT ?? mkdtempSync(join(tmpdir(), "caztor-shots-"));
mkdirSync(outDir, { recursive: true });
const { chromium } = await loadPlaywright();

const MAIN = "\\documentclass{article}\n\\title{Old title}\n\\begin{document}\nHello.\n\\end{document}\n";
const dir = makeProject({ "main.tex": MAIN, "extra.tex": "% extra\n" });
// API keys go to a temporary configuration home: the user's own ~/.config is never read or written by this check.
const configHome = mkdtempSync(join(tmpdir(), "caztor-e2e-config-"));
const server = await startServer(dir, { entry: "e2e/chat-server.ts", env: { CAZTOR_E2E_REAL: real ? "1" : "0", XDG_CONFIG_HOME: configHome } });
const browser = await chromium.launch();
let failed = false;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` (${detail})` : ""}`);
  if (!ok) failed = true;
};
const read = (name) => readFileSync(join(dir, name), "utf8");
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

try {
  const { page, problems } = await openApp(browser, server.url);
  globalThis.__shot = () => page.screenshot({ path: join(outDir, "99-failure.png") });
  const chat = page.getByRole("region", { name: "Chat" });
  const box = chat.getByRole("textbox", { name: "Message to the assistant" });
  const log = chat.getByRole("log", { name: "Conversation" });
  const send = async (text) => {
    await box.click();
    await box.fill(text);
    await box.press("Enter");
  };
  const idle = () => chat.getByRole("button", { name: "Send" }).waitFor({ timeout: 120000 }).then(() => chat.getByRole("button", { name: "Stop" }).waitFor({ state: "detached", timeout: 120000 }));
  const providersFirst = async () => chat.getByRole("radio", { name: "Claude Code" }).click();

  if (real && realProvider === "opencode") {
    // Real opencode turns on the chat: an edit, then (unless CAZTOR_E2E_TURNS=1) a continuation of the same session; then undo of the last one.
    const model = process.env.CAZTOR_E2E_MODEL;
    if (!model) throw new Error("Set CAZTOR_E2E_MODEL, for example openai/gpt-5.5.");
    await chat.getByRole("radio", { name: "opencode" }).click();
    await chat.getByRole("heading", { name: /not available/ }).waitFor({ timeout: 3000 }).then(
      () => check("real opencode is detected", false, "the provider is unavailable"),
      () => check("real opencode is detected", true),
    );
    const modelList = chat.getByRole("combobox", { name: "Model" });
    await modelList.waitFor({ timeout: 10000 });
    check("the model list from `opencode models` is offered", (await modelList.locator("option").count()) > 3);
    await modelList.selectOption(model);
    await pause(500);
    // CAZTOR_E2E_TURNS=1 makes only the first turn (one real call): it then also asks for the permission test and the undo is of that turn.
    const oneTurn = process.env.CAZTOR_E2E_TURNS === "1";
    await send(
      `Change the title in main.tex from 'Old title' to 'Real title'. Then answer in one short sentence, and say yes or no: do you have a tool whose name starts with engram?${
        oneTurn ? " Also, as a permission test I ask for, call your bash tool once with the command `ls` and tell me exactly what it answered." : ""
      }`,
    );
    await chat.getByText("Changed files").waitFor({ timeout: 180000 });
    await idle();
    const afterFirst = read("main.tex");
    check("the first real turn edited main.tex", afterFirst.includes("Real title"), afterFirst.replace(/\n/g, "\\n"));
    check("the changed file is listed", (await chat.getByRole("button", { name: "main.tex", exact: true }).count()) === 1);
    await pause(500);
    await page.screenshot({ path: join(outDir, "opencode-1-turn-light.png") });
    await page.emulateMedia({ colorScheme: "dark" });
    await pause(500);
    await page.screenshot({ path: join(outDir, "opencode-1-turn-dark.png") });
    await page.emulateMedia({ colorScheme: "light" });
    if (!oneTurn) {
      await send("Now change 'Hello.' to 'Hello again.' in main.tex. Then, as a permission test I ask for, call your bash tool once with the command `ls` and tell me exactly what it answered.");
      await chat.getByText("Changed files").nth(1).waitFor({ timeout: 180000 });
      await idle();
      check("the continuation edited main.tex and kept the first edit", read("main.tex").includes("Hello again.") && read("main.tex").includes("Real title"), read("main.tex").replace(/\n/g, "\\n"));
      await pause(500);
      await page.screenshot({ path: join(outDir, "opencode-2-continuation-light.png") });
      await page.emulateMedia({ colorScheme: "dark" });
      await pause(500);
      await page.screenshot({ path: join(outDir, "opencode-2-continuation-dark.png") });
      await page.emulateMedia({ colorScheme: "light" });
    }
    await chat.getByRole("button", { name: "Undo this turn" }).click();
    await chat.getByText("Undone").waitFor({ timeout: 10000 });
    check(oneTurn ? "undo restored the file to its original text" : "undo restored the file as the first turn left it", read("main.tex") === (oneTurn ? MAIN : afterFirst));
    await page.screenshot({ path: join(outDir, "opencode-3-undone.png") });
    const stored = readFileSync(join(dir, ".caztor", "chat", "opencode.jsonl"), "utf8").trim().split("\n").map((line) => JSON.parse(line));
    for (const [index, turn] of stored.entries()) {
      const done = turn.events.find((event) => event.type === "done");
      const kinds = turn.events.map((event) => (event.type === "tool_start" ? `tool:${event.name}` : event.type));
      const failedTools = turn.events.filter((event) => event.type === "tool_end" && event.status === "failed").map((event) => event.summary ?? "");
      const answer = turn.events.filter((event) => event.type === "text").map((event) => event.text).join(" ");
      console.log(`Turn ${index + 1}: done=${JSON.stringify(done)} events=${kinds.join(",")} failedTools=${JSON.stringify(failedTools)} answer=${JSON.stringify(answer)}`);
    }
    check("no console errors or CSP violations", problems.length === 0, problems.join(" | "));
  } else if (real) {
    // Two real turns: one edit, then undo. Everything else is covered with the scripted runners.
    await chat.getByRole("heading", { name: /not available/ }).waitFor({ timeout: 3000 }).then(
      () => check("real Claude Code is detected", false, "the provider is unavailable"),
      () => check("real Claude Code is detected", true),
    );
    await send("Change the title in main.tex from 'Old title' to 'Real title'. Reply in one short sentence.");
    await chat.getByText("Changed files").waitFor({ timeout: 180000 });
    await idle();
    check("the real turn edited main.tex", read("main.tex").includes("Real title"), read("main.tex").replace(/\n/g, "\\n"));
    check("the changed file is listed", (await chat.getByRole("button", { name: "main.tex", exact: true }).count()) === 1);
    await page.screenshot({ path: join(outDir, "real-1-turn.png") });
    await chat.getByRole("button", { name: "Undo this turn" }).click();
    await chat.getByText("Undone").waitFor({ timeout: 10000 });
    check("undo restored main.tex", read("main.tex") === MAIN);
    await page.screenshot({ path: join(outDir, "real-2-undone.png") });
    // The cost of the real turn, from the `done` event the server stored in the project's history.
    const stored = readFileSync(join(dir, ".caztor", "chat", "claude.jsonl"), "utf8").trim().split("\n").map((line) => JSON.parse(line));
    const usage = stored.flatMap((turn) => turn.events.filter((event) => event.type === "done").map((event) => event.usage));
    console.log(`Real turns: ${stored.length}; cost per turn (USD): ${JSON.stringify(usage.map((u) => u?.costUsd ?? null))}`);
    check("no console errors or CSP violations", problems.length === 0, problems.join(" | "));
  } else {
    // 1. The header: the active provider by its name, as text (Caztor ships no vendor logo).
    const header = chat.getByRole("group", { name: "Assistant" });
    await header.waitFor();
    check("the active provider's name is shown as text", (await header.getByText("Claude Code", { exact: true }).count()) >= 1);
    check("no provider logo image is shown", (await header.getByRole("img", { name: "Claude Code" }).count()) === 0);
    check("opencode, codex and antigravity are listed", (await header.getByRole("radiogroup", { name: "Provider" }).getByRole("radio").count()) === 4);
    check("Pi is offered in the More providers dropdown, not as a radio", (await header.getByRole("combobox", { name: "More providers" }).getByRole("option", { name: "Pi" }).count()) === 1);

    // 2. Streaming with tool card, changed files and undo (strict).
    await send("please edit the title");
    // The first message of a project that never chose a provider saves the shown choice first; the log appears after that.
    await log.waitFor({ timeout: 5000 });
    const grew = await page.evaluate(
      () =>
        new Promise((resolve) => {
          const sizes = [];
          const watch = () => sizes.push(document.querySelector(".message--assistant")?.textContent?.length ?? 0);
          const observer = new MutationObserver(watch);
          observer.observe(document.querySelector('[role="log"]'), { subtree: true, childList: true, characterData: true });
          setTimeout(() => {
            observer.disconnect();
            resolve(sizes);
          }, 1500);
        }),
    );
    const distinct = new Set(grew.filter((size) => size > 0));
    check("text grows progressively while streaming", distinct.size >= 4, `${distinct.size} sizes`);
    check("text never shrinks or reorders while streaming", grew.every((size, i) => i === 0 || size >= grew[i - 1]));
    await chat.getByText("Changed files").waitFor({ timeout: 15000 });
    await idle();
    const toolCard = chat.locator(".tool-card").first();
    check("a tool card shows the tool, the file and Done", /Edit/.test(await toolCard.innerText()) && /main\.tex/.test(await toolCard.innerText()) && /Done/.test(await toolCard.innerText()), await toolCard.innerText().then((t) => t.replace(/\s+/g, " ")));
    check("the Markdown reply is rendered, a LaTeX block as code", (await chat.locator(".message--assistant strong").count()) >= 1 && (await chat.locator("pre.markdown__code code").innerText()).includes("\\title{Better title}"));
    check("the reply is not styled as a terminal", await chat.locator(".message--assistant").first().evaluate((node) => !getComputedStyle(node).fontFamily.toLowerCase().includes("mono")));
    check("the agent edit reached the disk", read("main.tex").includes("Better title"));
    await toolCard.getByRole("button").click();
    check("the tool card opens its details", (await toolCard.innerText()).includes("Replaced the title"));
    // The whole app for the screenshots: main.tex open in the editor and a compile, when the engine is there.
    await page.getByRole("region", { name: "Files" }).getByRole("button", { name: /^main\.tex/ }).click();
    await page.getByRole("region", { name: "LaTeX editor" }).getByRole("textbox", { name: "main.tex" }).waitFor({ timeout: 5000 });
    await page.getByRole("region", { name: "PDF preview" }).getByRole("button", { name: "Compile", exact: true }).click().catch(() => {});
    await page.locator(".pdf-viewer__canvas").first().waitFor({ timeout: 45000 }).catch(() => {});
    await pause(800);
    await page.screenshot({ path: join(outDir, "01-turn-light.png") });
    await page.emulateMedia({ colorScheme: "dark" });
    await pause(500);
    await page.screenshot({ path: join(outDir, "02-turn-dark.png") });
    await page.emulateMedia({ colorScheme: "light" });
    // Clicking a changed file opens it in the editor.
    await chat.getByRole("button", { name: "main.tex", exact: true }).click();
    await page.getByRole("region", { name: "LaTeX editor" }).getByRole("textbox", { name: "main.tex" }).waitFor({ timeout: 5000 });
    check("a changed file opens in the editor", true);
    await chat.getByRole("button", { name: "Undo this turn" }).click();
    await chat.getByText("Undone").waitFor({ timeout: 10000 });
    check("strict undo restores the file", read("main.tex") === MAIN);
    check("the editor stayed editable and shows the restored file", (await page.getByRole("region", { name: "LaTeX editor" }).getByRole("textbox", { name: "main.tex" }).innerText()).includes("Old title"));

    // 3. Undo when a file changed after the turn: cancel, keep my edits, overwrite.
    await send("edit two files");
    await chat.getByRole("button", { name: "Undo this turn" }).waitFor({ timeout: 15000 });
    await idle();
    writeFileSync(join(dir, "main.tex"), "MY EDIT\n");
    await pause(300);
    await chat.getByRole("button", { name: "Undo this turn" }).click();
    const choice = page.getByRole("dialog", { name: "Some files changed after this turn" });
    await choice.waitFor();
    check("the three choices are offered", (await choice.getByRole("button").count()) === 3);
    await page.screenshot({ path: join(outDir, "03-undo-choice.png") });
    await choice.getByRole("button", { name: "Cancel" }).click();
    await choice.waitFor({ state: "detached" });
    check("Cancel changes nothing", read("main.tex") === "MY EDIT\n" && read("extra.tex").includes("extra edited"));
    await chat.getByRole("button", { name: "Undo this turn" }).click();
    await choice.getByRole("button", { name: "Undo the rest and keep my edits" }).click();
    await chat.getByText(/only partial/).waitFor({ timeout: 10000 });
    check("keep my edits restores the other file and keeps mine", read("main.tex") === "MY EDIT\n" && read("extra.tex") === "% extra\n");
    check("a skipped file is reported, not shown as a full success", (await chat.getByText(/Not restored: main\.tex/).count()) === 1);
    // The partial undo is not final for that file: a second turn and the overwrite choice.
    await send("edit two files");
    await chat.getByRole("button", { name: "Undo this turn" }).waitFor({ timeout: 15000 });
    await idle();
    writeFileSync(join(dir, "main.tex"), "MY SECOND EDIT\n");
    await pause(300);
    await chat.getByRole("button", { name: "Undo this turn" }).last().click();
    await choice.getByRole("button", { name: "Overwrite my edits" }).click();
    await chat.getByText(/Undid the turn/).nth(1).waitFor({ timeout: 10000 });
    check("overwrite restores the file the turn started from", read("main.tex") === "MY EDIT\n" && read("extra.tex") === "% extra\n", read("main.tex"));

    // 4. Stop, an error, a provider that is not available, the other provider.
    await send("slow task");
    await chat.getByRole("button", { name: "Stop" }).click();
    await chat.getByText("Stopped").waitFor({ timeout: 15000 });
    check("Stop ends the turn as stopped and the interrupted tool does not spin", (await chat.getByText("Interrupted").count()) === 1 && (await chat.getByRole("button", { name: "Stop" }).count()) === 0);
    await send("make an error");
    await chat.getByRole("heading", { name: "The provider needs you to sign in" }).waitFor({ timeout: 15000 });
    await chat.getByRole("button", { name: "Show details" }).click();
    check("an error is a card with collapsible details", (await chat.getByText("HTTP 401 from the fake provider").count()) === 1);
    await chat.getByRole("radio", { name: "Codex" }).click();
    await chat.getByRole("heading", { name: /Codex is not available/ }).waitFor({ timeout: 5000 });
    check("an unavailable provider shows its reason and a re-check", (await chat.getByText(/not available yet/).count()) >= 1 && (await chat.getByRole("button", { name: "Check again" }).count()) === 1 && (await box.isDisabled()));
    check("selecting Codex shows the disclosure that it can run commands in its sandbox", (await chat.getByRole("note", { name: "Codex runs commands" }).innerText()).includes("inside its own sandbox"));
    check("the Codex choice shows its name as text", (await chat.getByRole("radio", { name: "Codex" }).getByText("Codex").count()) >= 1);
    await page.screenshot({ path: join(outDir, "05-codex-unavailable-light.png") });
    await page.emulateMedia({ colorScheme: "dark" });
    await pause(400);
    await page.screenshot({ path: join(outDir, "06-codex-unavailable-dark.png") });
    await page.emulateMedia({ colorScheme: "light" });
    await chat.getByRole("radio", { name: "opencode" }).click();
    await box.waitFor();
    await send("hello opencode");
    await chat.getByRole("alert").filter({ hasText: /model/i }).first().waitFor({ timeout: 5000 });
    check("opencode without a model is refused with a readable reason", true);
    await chat.getByRole("textbox", { name: "Model" }).fill("anthropic/test");
    await chat.getByRole("textbox", { name: "Model" }).press("Enter");
    await pause(500);
    await box.click();
    await box.press("Enter");
    await chat.getByText("Done. The title is updated.").waitFor({ timeout: 15000 });
    check("whole text parts appear complete", (await chat.getByText("Done. The title is updated.").count()) === 1);
    await providersFirst();

    // 4b. The sign-in method: a toggle, a masked write-only key form and the login hint. The key here is a fake.
    await chat.getByRole("radio", { name: "Claude Code", checked: true }).waitFor();
    const signIn = chat.getByRole("group", { name: "Sign-in method" });
    await signIn.waitFor();
    check("the sign-in toggle starts on account", (await signIn.getByRole("radio", { name: "Account" }).getAttribute("aria-checked")) === "true");
    check("API key is marked not configured", (await signIn.getByText("Not configured").count()) === 1);
    const hintText = await chat.getByTestId("login-hint").innerText();
    check("the account login hint names the CLI step", hintText.includes("claude") && hintText.includes("/login"), hintText);
    await page.screenshot({ path: join(outDir, "05-signin-account-light.png") });
    await signIn.getByRole("radio", { name: "API key" }).click();
    const keyField = chat.getByLabel("API key", { exact: true });
    await keyField.waitFor();
    check("selecting API without a key asks for one and stays on account", (await signIn.getByRole("radio", { name: "Account" }).getAttribute("aria-checked")) === "true");
    check("the key field is masked and empty", (await keyField.getAttribute("type")) === "password" && (await keyField.inputValue()) === "");
    await page.screenshot({ path: join(outDir, "05b-signin-no-key-light.png") });
    const FAKE_KEY = "sk-e2e-fake-key-0000abcd";
    await keyField.fill(FAKE_KEY);
    await chat.getByRole("button", { name: "Save key" }).click();
    await chat.getByText(/Key set/).waitFor({ timeout: 5000 });
    check("the saved key shows set and its last four only", (await chat.getByText(/Key set/).innerText()).includes("abcd") && !(await page.content()).includes(FAKE_KEY));
    check("the field is emptied after the save", (await keyField.inputValue()) === "");
    await signIn.getByRole("radio", { name: "API key" }).click();
    await page.waitForFunction(() => document.querySelector('[role="group"][aria-label="Sign-in method"] [role="radio"][aria-checked="true"]')?.textContent === "API key");
    check("with a key stored, API mode can be switched on", true);
    await page.screenshot({ path: join(outDir, "06-signin-api-light.png") });
    await page.emulateMedia({ colorScheme: "dark" });
    await pause(400);
    await page.screenshot({ path: join(outDir, "07-signin-api-dark.png") });
    await page.emulateMedia({ colorScheme: "light" });
    await signIn.getByRole("radio", { name: "Account" }).click();
    await page.waitForFunction(() => document.querySelector('[role="group"][aria-label="Sign-in method"] [role="radio"][aria-checked="true"]')?.textContent === "Account");
    await signIn.getByRole("radio", { name: "API key" }).click();
    await chat.getByRole("button", { name: "Delete key" }).click();
    await chat.getByText(/No key set/).waitFor({ timeout: 5000 });
    check("deleting the key shows not set", true);
    await signIn.getByRole("radio", { name: "Account" }).click();

    // 5. Reload restores the conversation and the draft is kept per provider.
    await box.fill("a draft for claude");
    await page.reload({ waitUntil: "load" });
    await chat.getByText("please edit the title").first().waitFor({ timeout: 10000 });
    check("history is restored after a reload", (await chat.getByText("please edit the title").count()) >= 1 && (await chat.locator(".tool-card").count()) >= 1);

    // 7. Antigravity, on a scripted runner: its name, permanent notice, account only, and how it looks at both window sizes.
    await page.reload({ waitUntil: "load" });
    const assistant = page.getByRole("region", { name: "Chat" }).getByRole("group", { name: "Assistant" });
    await assistant.getByRole("radio", { name: "Antigravity" }).click();
    const isolation = page.getByRole("note", { name: "Antigravity isolation" });
    await isolation.waitFor({ timeout: 10000 });
    check("the Antigravity notice names ~/.gemini and offers no way to dismiss it", (await isolation.innerText()).includes("~/.gemini") && (await isolation.getByRole("button").count()) === 0);
    check("Antigravity is shown by its name", (await assistant.getByText("Antigravity", { exact: true }).count()) >= 1);
    const summary = page.locator("details.auth-panel summary");
    await summary.waitFor({ timeout: 10000 });
    if (!(await page.locator("details.auth-panel").evaluate((node) => node.open))) await summary.click();
    check("Antigravity offers the account sign-in only", (await page.getByRole("group", { name: "Sign-in method" }).getByRole("radio").count()) === 1);
    await page.reload({ waitUntil: "load" });
    await isolation.waitFor({ timeout: 10000 });
    check("the Antigravity notice is still there after a reload", await isolation.isVisible());
    for (const [width, height] of [[1440, 900], [1366, 768]]) {
      await page.setViewportSize({ width, height });
      for (const scheme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: scheme });
        await pause(300);
        await page.screenshot({ path: join(outDir, `05-antigravity-${width}-${scheme}.png`) });
      }
    }
    await page.emulateMedia({ colorScheme: "light" });
    // 8. Pi, on a scripted runner, chosen from the dropdown: its name, the permanent notice, and no radio checked.
    const more = assistant.getByRole("combobox", { name: "More providers" });
    await more.selectOption("pi");
    const piIsolation = page.getByRole("note", { name: "Pi isolation" });
    await piIsolation.waitFor({ timeout: 10000 });
    check("the Pi notice names ~/.pi/agent and offers no way to dismiss it", (await piIsolation.innerText()).includes("~/.pi/agent") && (await piIsolation.getByRole("button").count()) === 0);
    check("the dropdown shows Pi as selected and no radio is checked", (await more.inputValue()) === "pi" && (await assistant.getByRole("radiogroup", { name: "Provider" }).locator('[role="radio"][aria-checked="true"]').count()) === 0);
    await page.reload({ waitUntil: "load" });
    await piIsolation.waitFor({ timeout: 10000 });
    check("Pi is still selected after a reload", (await assistant.getByRole("combobox", { name: "More providers" }).inputValue()) === "pi");
    for (const [width, height] of [[1440, 900], [1366, 768]]) {
      await page.setViewportSize({ width, height });
      await pause(300);
      await page.screenshot({ path: join(outDir, `06-pi-${width}.png`) });
    }
    // The refusals this script provokes on purpose (409 undo conflicts, a model that is required) are logged by the
    // browser as failed resource loads; anything else, a CSP violation above all, is a failure.
    const unexpected = problems.filter((p) => !/status of 409|net::ERR_FAILED/.test(p));
    check("no console errors or CSP violations in the normal flows", unexpected.length === 0 && !problems.some((p) => /Content Security Policy/i.test(p)), unexpected.join(" | "));
  }
  console.log(`\nScreenshots: ${outDir}`);
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
