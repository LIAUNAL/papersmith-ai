import { expect, test, type Page } from '@playwright/test';
import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/**
 * The read-only snapshot (`smith ui --export-snapshot`) served the way GitHub
 * Pages serves it: plain files under a sub-path (`/repo/`), no backend. The
 * page must render from the snapshot alone, never reach `/api/`, refuse every
 * write and show nothing that runs.
 */
const REPO_ROOT = new URL('../../../', import.meta.url).pathname;
const PYTHON = `${REPO_ROOT}.micromamba/envs/papersmith/bin/python`;
const PORT = 8097;
const BASE = `http://127.0.0.1:${PORT}/repo/`;

const EXPORT = String.raw`
import sys
from pathlib import Path
from papersmith.core import init as init_module
from skills._core.command_center import static_export
base = Path(sys.argv[1])
ws = base / "ws"
init_module.initialize(ws, run_npm=False, run_env=False, allow_dirty_kit=True)
(ws / "sota-pool").mkdir(exist_ok=True)
(ws / "sota-pool" / "atlas.html").write_text("<!doctype html><html><body><p id='atlas'>atlas</p></body></html>")
objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
           b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>"]
pdf, offsets = b"%PDF-1.4\n", []
for number, body in enumerate(objects, 1):
    offsets.append(len(pdf))
    pdf += b"%d 0 obj\n" % number + body + b"\nendobj\n"
xref = len(pdf)
pdf += b"xref\n0 4\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
pdf += b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
(ws / "paper").mkdir(exist_ok=True)
(ws / "paper" / "main.pdf").write_bytes(pdf)
static_export.export_snapshot(ws, base / "site" / "repo")
`;

let scratch = '';
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  test.setTimeout(120_000);
  scratch = mkdtempSync(join(tmpdir(), 'ps-snapshot-'));
  execFileSync(PYTHON, ['-c', EXPORT, scratch], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONPATH: `${REPO_ROOT}src:${REPO_ROOT}`, PYTHONDONTWRITEBYTECODE: '1' },
    stdio: 'pipe',
  });
  server = spawn(PYTHON, ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1',
    '--directory', join(scratch, 'site')], { stdio: 'ignore' });
  for (let i = 0; i < 50; i += 1) {
    try {
      if ((await fetch(BASE)).ok) return;
    } catch (_) { /* not listening yet */ }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error('the static file server did not start');
});

test.afterAll(() => {
  server?.kill();
  if (scratch) rmSync(scratch, { recursive: true, force: true });
});

function watch(page: Page): { api: string[]; errors: string[] } {
  const seen = { api: [] as string[], errors: [] as string[] };
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) seen.api.push(request.url());
  });
  page.on('response', (response) => {
    if (response.status() >= 400) seen.errors.push(`${response.status()} ${response.url()}`);
  });
  page.on('console', (message) => {
    if (message.type() === 'error') seen.errors.push(message.text());
  });
  page.on('pageerror', (error) => seen.errors.push(String(error)));
  return seen;
}

test('the snapshot renders every read-only tab from its files', async ({ page }) => {
  const seen = watch(page);
  await page.goto(BASE);
  await expect(page.locator('#psStaticBanner')).toContainText('Read-only snapshot of');
  await expect(page.locator('body')).toHaveClass(/ps-static/);
  await expect(page.locator('#metaProposalTitle')).not.toHaveText(/^(Loading|Cargando)/, { timeout: 15_000 });

  const flow = page.locator('#flowIframe');
  await expect(flow).toHaveAttribute('src', /^snapshot\/en\/api\/flow\.html$/);
  await expect(page.frameLocator('#flowIframe').locator('body')).toBeVisible({ timeout: 15_000 });

  for (const tab of ['modelo', 'experiments', 'novelty', 'atlas', 'pipeline', 'sections', 'preview']) {
    await page.evaluate((id) => (window as any).navigateTab(id), tab);
    await expect(page.locator(`#pane-${tab}`)).toBeVisible();
  }
  await page.evaluate(() => (window as any).navigateTab('atlas'));
  await expect.poll(() => page.evaluate(() => (document.getElementById('graphIframe') as HTMLIFrameElement).getAttribute('src')),
    { timeout: 15_000 }).toMatch(/^snapshot\/en\/api\/atlas\/view\.html$/);
  await expect(page.frameLocator('#graphIframe').locator('#atlas')).toHaveText('atlas', { timeout: 15_000 });
  // The page's own path check still sees the route.
  expect(await page.evaluate(() => new URL((document.getElementById('graphIframe') as HTMLIFrameElement).src).pathname))
    .toBe('/api/atlas/view');

  await page.waitForTimeout(1_000);
  expect(seen.api).toEqual([]);
  expect(seen.errors).toEqual([]);
});

test('writes are refused and nothing that runs is shown', async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator('#psStaticBanner')).toBeVisible();
  const refused = await page.evaluate(async () => {
    const response = await fetch('/api/phase/run', { method: 'POST', body: '{}' });
    return { status: response.status, body: await response.json() };
  });
  expect(refused.status).toBe(403);
  expect(refused.body.error).toBe('STATIC_SNAPSHOT');
  const absent = await page.evaluate(async () => (await fetch('/api/ai-history')).status);
  expect(absent).toBe(404);

  await expect(page.locator('#smithAssistantFab')).toBeHidden();
  await expect(page.locator('#smithTerminalWindow')).toBeHidden();
  expect(await page.evaluate(() => (window as any).sendToCli('ls', true))).toBe(false);
  await page.evaluate(() => (window as any).navigateTab('pipeline'));
  const runButtons = page.locator('[onclick^="triggerRunPhase"], [data-phase-action]');
  for (const button of await runButtons.all()) await expect(button).toBeHidden();
  await expect(page.locator('.tab-nav__btn', { hasText: 'AI History' })).toBeHidden();
});

test('the Spanish snapshot shows the Spanish banner and answers', async ({ page }) => {
  const seen = watch(page);
  await page.goto(BASE);
  await page.selectOption('#langSelect', 'es');
  await expect(page.locator('#psStaticBanner')).toContainText('Instantánea de solo lectura');
  const status = await page.evaluate(async () => (await fetch('/api/status')).status);
  expect(status).toBe(200);
  expect(seen.api).toEqual([]);
});
