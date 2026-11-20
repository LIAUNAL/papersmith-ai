// Real-browser check of the dialog: Tab and Shift+Tab move between the buttons and wrap, and after a confirmed
// delete focus is on a live element. jsdom cannot reproduce the focus handling of a native Tab.
import { loadPlaywright, makeProject, openApp, startServer } from "./lib.mjs";

const { chromium } = await loadPlaywright();
const server = await startServer(makeProject({ "main.tex": "\\documentclass{article}\\begin{document}Hi\\end{document}\n", "extra.tex": "x\n" }));
const browser = await chromium.launch();
let failed = false;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` (${detail})` : ""}`);
  if (!ok) failed = true;
};
try {
  const { page, problems } = await openApp(browser, server.url);
  await page.getByRole("button", { name: "Delete extra.tex" }).click({ force: true });
  const dialog = page.getByRole("dialog");
  await dialog.waitFor();
  const focused = () => page.evaluate(() => document.activeElement?.textContent?.trim() ?? document.activeElement?.tagName);
  check("opens on Cancel", (await focused()) === "Cancel", await focused());
  await page.keyboard.press("Tab");
  check("Tab reaches Delete", (await focused()) === "Delete", await focused());
  await page.keyboard.press("Tab");
  check("Tab wraps to Cancel", (await focused()) === "Cancel", await focused());
  await page.keyboard.press("Shift+Tab");
  check("Shift+Tab wraps back to Delete", (await focused()) === "Delete", await focused());
  await page.keyboard.press("Shift+Tab");
  check("Shift+Tab reaches Cancel", (await focused()) === "Cancel", await focused());
  await page.keyboard.press("Tab");
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await dialog.waitFor({ state: "detached" });
  await page.waitForTimeout(800);
  const live = await page.evaluate(() => {
    const element = document.activeElement;
    return element !== null && element !== document.body && element.isConnected ? (element.getAttribute("aria-label") ?? element.tagName) : null;
  });
  check("focus is on a live element after a confirmed delete", live !== null, String(live));
  const background = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const light = "rgb(238, 240, 243)";
  const dark = "rgb(16, 19, 23)";
  await page.emulateMedia({ colorScheme: "light" });
  check("the system theme applies", (await background()) === light, await background());
  const theme = page.getByRole("combobox", { name: "Theme" });
  await theme.selectOption("dark");
  check("a manual dark theme beats a light system", (await background()) === dark, await background());
  await page.reload();
  await theme.waitFor();
  check("the theme survives a reload", (await background()) === dark, await background());
  await page.emulateMedia({ colorScheme: "dark" });
  await theme.selectOption("light");
  check("a manual light theme beats a dark system", (await background()) === light, await background());
  const shadow = await page.evaluate(() => {
    const probe = document.body.appendChild(document.createElement("div"));
    probe.style.boxShadow = "var(--shadow-dialog)";
    const value = getComputedStyle(probe).boxShadow;
    probe.remove();
    return value;
  });
  check("the dialog shadow is a real shadow", shadow !== "none" && shadow !== "", shadow);
  await theme.selectOption("system");
  check("no console errors", problems.length === 0, problems.join("; "));
} finally {
  await browser.close();
  await server.stop();
}
process.exit(failed ? 1 : 0);
