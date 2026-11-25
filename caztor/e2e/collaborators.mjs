// Real-browser check of sharing: the host link, an invite link opened from another site that only asks for the access
// key (the SameSite=Strict cookie must survive the form post and its redirect), the collaborator's own page token, what
// a collaborator sees, the key on a second browser, revoking one key, and revoking the person.
import { spawn } from "node:child_process";
import { rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPlaywright, makeProject } from "./lib.mjs";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const { chromium } = await loadPlaywright();
const project = makeProject({ "main.tex": "\\documentclass{article}\\begin{document}Hi\\end{document}\n" });

const child = spawn(process.execPath, ["e2e/collab-server.ts", project], { cwd: repo, stdio: ["ignore", "pipe", "pipe"] });
const started = await new Promise((done, fail) => {
  let output = "";
  const timer = setTimeout(() => fail(new Error(`The server did not start: ${output}`)), 15000);
  const onData = (chunk) => {
    output += chunk;
    const link = /Host link (\S+) config (\S+) bin (\S+)/.exec(output);
    const url = /Caztor is running at (http:\/\/127\.0\.0\.1:\d+)/.exec(output);
    if (link === null || url === null) return;
    clearTimeout(timer);
    done({ hostLink: link[1], config: link[2], bin: link[3], url: url[1] });
  };
  child.stdout.on("data", onData);
  child.stderr.on("data", onData);
  child.once("exit", (code) => fail(new Error(`The server exited with ${code}: ${output}`)));
});

const browser = await chromium.launch();
let failed = false;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` (${detail})` : ""}`);
  if (!ok) failed = true;
};
const metaToken = (page) => page.evaluate(() => document.querySelector('meta[name="caztor-token"]')?.getAttribute("content") ?? null);
const acknowledge = async (page) => {
  const notice = page.getByRole("dialog", { name: "Before you start" });
  await notice.waitFor({ timeout: 5000 }).catch(() => {});
  if ((await notice.count()) > 0) await notice.getByRole("button", { name: "I understand" }).click();
  await notice.waitFor({ state: "detached", timeout: 5000 }).catch(() => {});
};

try {
  const hostContext = await browser.newContext();
  const host = await hostContext.newPage();
  const hostProblems = [];
  host.on("pageerror", (error) => hostProblems.push(String(error)));
  await host.goto(started.hostLink);
  await host.waitForURL(`${started.url}/`);
  await host.locator(".app__user").waitFor();
  await acknowledge(host);
  check("the host link opens the app as the host", (await host.locator(".app__user").textContent()) === "Host");
  const hostToken = await metaToken(host);
  check("the host page carries a token", typeof hostToken === "string" && hostToken.length >= 16);

  await host.getByRole("button", { name: "Collaborators" }).click();
  await host.getByRole("textbox", { name: "Name" }).fill("Ana");
  await host.getByRole("combobox", { name: "Key lasts" }).selectOption({ label: "1 day" });
  await host.getByRole("button", { name: "Invite" }).click();
  const link = await host.getByRole("textbox", { name: "Invite link for Ana" }).inputValue();
  const key = await host.getByRole("textbox", { name: "Access key for Ana" }).inputValue();
  check("the invite link uses the public name", link.startsWith(`http://localhost:${new URL(started.url).port}/invite/`), link);
  check("the access key is shown in groups", /^[A-HJ-NP-Z2-9]{5}(-[A-HJ-NP-Z2-9]{5}){3}$/.test(key), key);
  check("the link does not hold the key", !link.includes(key) && !link.includes(key.replaceAll("-", "")));
  check("the dialog has a copy button for each", (await host.getByRole("button", { name: "Copy link" }).count()) === 1 && (await host.getByRole("button", { name: "Copy key" }).count()) === 1);
  check("the dialog says the key is shown only once", (await host.getByText(/The key is shown only now/).count()) === 1);
  check("the dialog shows the key's expiry", (await host.getByText("Key 1: expires in 1 day, not used yet").count()) === 1);

  // A link preview fetches the link, perhaps several times: it signs nobody in and uses nothing up.
  const preview = await browser.newContext();
  for (let fetchCount = 0; fetchCount < 3; fetchCount += 1) {
    const response = await preview.request.get(link);
    check(`a preview fetch ${fetchCount + 1} gets the sign-in page and no cookie`, response.status() === 200 && response.headers()["set-cookie"] === undefined && (await response.text()).includes("Access key"));
  }
  await preview.close();

  const guestContext = await browser.newContext();
  const guest = await guestContext.newPage();
  const guestProblems = [];
  guest.on("pageerror", (error) => guestProblems.push(String(error)));
  await guest.goto(new URL("/", link).href);
  check("a browser without a session is asked for an invite", (await guest.textContent("body"))?.includes("Ask the host for an invite link") === true);
  check("and gets no token", (await metaToken(guest)) === null);

  // 127.0.0.1 and localhost are different sites, so this is a cross-site navigation to the invite.
  await guest.goto(`${started.url}/`);
  await guest.evaluate((href) => {
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.id = "go";
    anchor.textContent = "go";
    document.body.append(anchor);
  }, link);
  await guest.click("#go");
  await guest.waitForURL(link);
  check("the link alone opens a page asking for the key", (await guest.getByRole("textbox", { name: "Access key" }).count()) === 1);
  check("and signs no one in", (await guestContext.cookies()).every((cookie) => cookie.name !== "caztor_session"));
  await guest.getByRole("textbox", { name: "Access key" }).fill("AAAAA-AAAAA-AAAAA-AAAAA");
  await guest.getByRole("button", { name: "Sign in" }).click();
  await guest.getByText("That key does not work.").waitFor({ timeout: 5000 });
  check("a wrong key is refused without a session", (await guestContext.cookies()).every((cookie) => cookie.name !== "caztor_session"));
  // Typed in lower case without dashes, as someone might from a phone.
  await guest.getByRole("textbox", { name: "Access key" }).fill(key.toLowerCase().replaceAll("-", ""));
  await guest.getByRole("button", { name: "Sign in" }).click();
  await guest.waitForURL(new URL("/", link).href);
  await guest.locator(".app__user").waitFor({ timeout: 10000 });
  await acknowledge(guest);
  check("the right key signs the collaborator in, after a link opened from another site", (await guest.locator(".app__user").textContent()) === "Ana");
  const guestToken = await metaToken(guest);
  check("the collaborator's page carries their own token, not the host's", guestToken !== null && guestToken !== hostToken);
  check("the collaborator has no Collaborators button", (await guest.getByRole("button", { name: "Collaborators" }).count()) === 0);
  check("the collaborator has the chat now", (await guest.getByText("Collaborator chat is not available yet").count()) === 0);
  // A scripted sign-in: the server's PATH has only a fake claude, run inside the collaborator's sandbox.
  const signIn = guest.getByRole("button", { name: "Sign in", exact: true });
  await signIn.waitFor({ timeout: 10000 });
  await signIn.click();
  const dialog = guest.getByRole("dialog", { name: /Sign in to Claude/ });
  await dialog.waitFor();
  const authLink = dialog.getByRole("link", { name: /claude\.com\/cai\/oauth/ });
  await authLink.waitFor({ timeout: 15000 });
  check("the sign-in dialog shows the CLI's link, opening in a new tab", (await authLink.getAttribute("target")) === "_blank" && (await authLink.getAttribute("rel"))?.includes("noopener") === true);
  await dialog.getByPlaceholder("Paste the code here").fill("e2e-pasted-code-123");
  await dialog.getByRole("button", { name: "Send" }).click();
  await dialog
    .getByText("You are signed in.")
    .waitFor({ timeout: 15000 })
    .catch(async (error) => {
      throw new Error(`${error.message}\nDialog: ${await dialog.textContent()}`);
    });
  check("the pasted code finishes the sign-in", true);
  check("the pasted code is never shown back", (await dialog.locator("pre").textContent())?.includes("e2e-pasted-code-123") === false);
  await dialog.getByRole("button", { name: "Close" }).click();
  await dialog.waitFor({ state: "detached" });
  check("the collaborator is signed in to claude afterwards", (await guest.getByRole("button", { name: "Sign in", exact: true }).count()) === 0);
  await guest.getByRole("treeitem", { name: /main\.tex/ }).first().waitFor({ timeout: 5000 }).catch(() => {});
  check("the collaborator sees the project files", (await guest.getByText("main.tex").count()) > 0);
  const cookies = await guestContext.cookies();
  const session = cookies.find((cookie) => cookie.name === "caztor_session");
  check("the session cookie is HttpOnly and SameSite=Strict", session?.httpOnly === true && session?.sameSite === "Strict");

  // The same key from a second browser, such as a phone.
  const phoneContext = await browser.newContext();
  const phone = await phoneContext.newPage();
  await phone.goto(link);
  await phone.getByRole("textbox", { name: "Access key" }).fill(key);
  await phone.getByRole("button", { name: "Sign in" }).click();
  await phone.locator(".app__user").waitFor({ timeout: 10000 });
  check("the key signs in a second browser too", (await phone.locator(".app__user").textContent()) === "Ana");

  // A second key for Ana, then revoking only the first: both of its browsers are signed out, the second key stays.
  await host.getByRole("textbox", { name: "Name" }).fill("Ana");
  await host.getByRole("combobox", { name: "Key lasts" }).selectOption({ label: "7 days" });
  await host.getByRole("button", { name: "Invite" }).click();
  await host.getByText("Key 2: expires in 7 days, not used yet").waitFor();
  check("the dialog counts the browsers signed in with a key", (await host.getByText("Key 1: expires in 1 day, on 2 browsers").count()) === 1);
  await host.getByRole("button", { name: "Revoke key 1 of Ana" }).click();
  await host.getByText("Key 1: expires in 7 days, not used yet").waitFor();
  await guest.reload();
  await phone.reload();
  check("revoking a key signs out the browsers it signed in", (await guest.textContent("body"))?.includes("Ask the host for an invite link") === true && (await phone.textContent("body"))?.includes("Ask the host for an invite link") === true);

  await host.getByRole("button", { name: "Revoke Ana" }).click();
  await host.getByText("Nobody is invited yet.").waitFor();
  check("revoking the person removes them", (await host.getByRole("list", { name: "Collaborators" }).count()) === 0);
  check("no page errors", hostProblems.length === 0 && guestProblems.length === 0, [...hostProblems, ...guestProblems].join("; "));
} catch (error) {
  console.log(`FAIL ${error instanceof Error ? error.message : String(error)}`);
  failed = true;
} finally {
  await browser.close();
  await new Promise((done) => {
    child.once("exit", done);
    child.kill("SIGTERM");
  });
  rmSync(project, { recursive: true, force: true });
  rmSync(started.config, { recursive: true, force: true });
  rmSync(started.bin, { recursive: true, force: true });
}
console.log(failed ? "\nSOME CHECKS FAILED" : "\nALL CHECKS PASSED");
process.exit(failed ? 1 : 0);
