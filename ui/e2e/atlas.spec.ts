import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, test, type Page } from '@playwright/test';

/**
 * The SOTA constellation page (`sota-pool/atlas.html`) on its own, rendered by
 * `skills/plausibility/scripts/render_atlas.py` from a synthetic 25-system
 * atlas. These are the checks the constellation earns before it ships: it
 * shows the whole sky, falls back to the 2D constellation when the 3D sky
 * cannot or should not run, and draws nothing that nobody can see.
 *
 * Draw calls are counted by wrapping the WebGL and canvas 2D entry points, so
 * "stops drawing" is an observed fact, not a timing guess.
 */
const REPO_ROOT = new URL('../..', import.meta.url).pathname;
const SLOTS: Array<[string, number]> = [
  ['sun', 0], ['topic_app', 1], ['topic_ai', 1], ['problem', 1], ['application', 1],
  ['novelty', 1], ['family', 2], ['result', 3], ['conclusion', 3],
];

function syntheticAtlas() {
  const systems = Array.from({ length: 25 }, (_, n) => {
    const id = `s${String(n).padStart(2, '0')}`;
    return {
      id,
      title: `System ${n} title`,
      planets: SLOTS.map(([slot, orbit]) => ({
        id: `${id}-${slot}`, slot, orbit,
        label: slot === 'family' ? `Family ${n % 5}` : `${slot} of ${id}`,
        detail: 'detail', provenance: 'stated',
        evidence: { origin: 'https://example.test/p', quote: 'q', retrieved: '2026-10-21' },
      })),
    };
  });
  const links = systems.slice(1).map((s, n) => ({
    from_system: systems[n].id, from: `${systems[n].id}-novelty`, to_system: s.id, to: `${s.id}-problem`, rel: 'extends',
  }));
  return { systems, links };
}

let dir = '';
let pageUrl = '';

test.beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), 'atlas-e2e-'));
  writeFileSync(join(dir, 'atlas.json'), JSON.stringify(syntheticAtlas()));
  execFileSync(join(REPO_ROOT, '.micromamba/envs/papersmith/bin/python'), [
    join(REPO_ROOT, 'skills/plausibility/scripts/render_atlas.py'), join(dir, 'atlas.json'), '--out', join(dir, 'atlas.html'),
  ]);
  pageUrl = `file://${join(dir, 'atlas.html')}`;
});

test.afterAll(() => rmSync(dir, { recursive: true, force: true }));

async function countDraws(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __draws: number };
    w.__draws = 0;
    for (const proto of [WebGLRenderingContext.prototype, WebGL2RenderingContext.prototype]) {
      for (const name of ['drawArrays', 'drawElements', 'drawArraysInstanced', 'drawElementsInstanced'] as const) {
        const original = (proto as unknown as Record<string, (...args: unknown[]) => unknown>)[name];
        if (!original) continue;
        (proto as unknown as Record<string, unknown>)[name] = function (this: unknown, ...args: unknown[]) {
          w.__draws++;
          return original.apply(this, args);
        };
      }
    }
    const fill = CanvasRenderingContext2D.prototype.fillRect;
    CanvasRenderingContext2D.prototype.fillRect = function (...args) {
      w.__draws++;
      return fill.apply(this, args);
    };
  });
}

async function open(page: Page, query = ''): Promise<string[]> {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await countDraws(page);
  await page.goto(pageUrl + query);
  await page.waitForTimeout(600);
  return errors;
}

const draws = (page: Page) => page.evaluate(() => (window as unknown as { __draws: number }).__draws);
// The page keeps its state in top-level `let`/`const`, which are globals but not
// properties of `window`: read them as expressions in the page's global scope.
const currentView = (page: Page) => page.evaluate<string>('view');

async function setHidden(page: Page, hidden: boolean): Promise<void> {
  await page.evaluate((value) => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => value });
    document.dispatchEvent(new Event('visibilitychange'));
  }, hidden);
}

test.describe('the SOTA constellation', () => {
  test('the 3D sky frames every planet and labels suns without overlap', async ({ page }) => {
    const errors = await open(page, '?view=3d');
    expect(await currentView(page)).toBe('3d');
    const inView = await page.evaluate<number>(`(() => {
      viewer.rotate(false);
      viewer.reset();
      const all = viewer.project(Object.keys(SCENE.positions));
      return all.filter((p) => p && p.on).length / all.length;
    })()`);
    expect(inView).toBe(1);
    await page.waitForTimeout(200);
    const boxes = await page.locator('.atlas-names div:visible').evaluateAll((els) =>
      els.map((el) => el.getBoundingClientRect()).map((r) => ({ x: r.x, y: r.y, w: r.width, h: r.height })));
    expect(boxes.length).toBeGreaterThan(5);
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
        expect(overlap, `names ${i} and ${j} overlap`).toBe(false);
      }
    }
    await page.click('#names');
    await expect(page.locator('.atlas-names div:visible')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('without WebGL it opens the 2D constellation and says why', async ({ page }) => {
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...rest: unknown[]) {
        if (type === 'webgl' || type === 'webgl2') return null;
        return (original as (...a: unknown[]) => unknown).call(this, type, ...rest);
      } as typeof original;
    });
    const errors = await open(page);
    expect(await currentView(page)).toBe('2d');
    await expect(page.locator('#gpunote')).toBeVisible();
    await expect(page.locator('#gpunote')).toContainText('WebGL is not available');
    await expect(page.locator('#viewmode')).toBeDisabled();
    expect(errors).toEqual([]);
  });

  test('?view=2d opens the 2D constellation, which draws only when something changes', async ({ page }) => {
    const errors = await open(page, '?view=2d');
    expect(await currentView(page)).toBe('2d');
    await expect(page.locator('#gpunote')).toBeHidden();
    const idle = await draws(page);
    await page.waitForTimeout(800);
    expect(await draws(page)).toBe(idle);
    await page.click('#spinleft');
    await page.waitForTimeout(100);
    expect(await draws(page)).toBeGreaterThan(idle);
    expect(errors).toEqual([]);
  });

  test('the view button switches 3D and 2D and leaves one canvas behind', async ({ page }) => {
    const errors = await open(page, '?view=3d');
    for (const expected of ['2d', '3d', '2d', '3d']) {
      await page.click('#viewmode');
      expect(await currentView(page)).toBe(expected);
      await expect(page.locator('#sky canvas')).toHaveCount(1);
    }
    await expect(page.locator('#viewmode')).toHaveText('2D view');
    expect(errors).toEqual([]);
  });

  test('the 3D sky stops drawing while the page is hidden or idle', async ({ page }) => {
    const errors = await open(page, '?view=3d');
    const before = await draws(page);
    await page.waitForTimeout(300);
    expect(await draws(page), 'auto-rotation draws').toBeGreaterThan(before);

    await setHidden(page, true);
    await page.waitForTimeout(100);
    const hidden = await draws(page);
    await page.waitForTimeout(600);
    expect(await draws(page), 'hidden page draws nothing').toBe(hidden);

    await setHidden(page, false);
    await page.waitForTimeout(300);
    expect(await draws(page), 'shown again, it resumes').toBeGreaterThan(hidden);

    // With auto-rotation off the orbit damping settles within a number of
    // frames, not of seconds, and a software renderer draws few frames a
    // second: poll until a whole interval passes without a draw call.
    await page.click('#autorotate');
    await expect.poll(async () => {
      const start = await draws(page);
      await page.waitForTimeout(500);
      return (await draws(page)) - start;
    }, { message: 'an idle sky is not redrawn', timeout: 20_000 }).toBe(0);
    expect(errors).toEqual([]);
  });

  test('switching views repeatedly does not leak memory', async ({ page }) => {
    await open(page, '?view=3d');
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Performance.enable');
    const heap = async () => {
      await cdp.send('HeapProfiler.collectGarbage');
      const { metrics } = await cdp.send('Performance.getMetrics');
      return metrics.find((m) => m.name === 'JSHeapUsedSize')!.value;
    };
    for (let i = 0; i < 4; i++) await page.click('#viewmode');
    const start = await heap();
    for (let i = 0; i < 12; i++) {
      await page.click('#viewmode');
      await page.waitForTimeout(80);
    }
    const growth = (await heap()) - start;
    expect(growth, `heap grew ${Math.round(growth / 1024)} KiB`).toBeLessThan(4 * 1024 * 1024);
  });

  test('the hover label stays inside the sky', async ({ page }) => {
    await open(page, '?view=2d');
    const sky = (await page.locator('#sky').boundingBox())!;
    const target = await page.evaluate<{ x: number; y: number }>(`(() => {
      const points = viewer.project(SUNS.map((s) => s.key));
      return points.reduce((best, p) => (p.x < best.x ? p : best));
    })()`);
    await page.mouse.move(sky.x + target.x, sky.y + target.y);
    const tip = page.locator('.atlas-tip');
    await expect(tip).toBeVisible();
    const box = (await tip.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(sky.x);
    expect(box.x + box.width).toBeLessThanOrEqual(sky.x + sky.width);
  });
});

test.describe('a selected paper', () => {
  test('a software renderer (no GPU) keeps the 3D sky and is watched only for a hang', async ({ page }) => {
    await open(page);
    const result = await page.evaluate(`(() => {
      webglSupport = () => 'weak';
      return {
        choice: chooseView(),
        slowButAlive: hangs(30, 3000, 200),   // 10 fps, worst frame 200 ms
        fewFrames: hangs(12, 3000, 400),      // 4 fps
        stalledFrame: hangs(3, 1500, 1200),   // one frame over a second
      };
    })()`);
    expect(result).toEqual({ choice: { mode: '3d', reason: 'software' }, slowButAlive: false, fewFrames: true, stalledFrame: true });
  });

  test('a 3D sky that hangs drops to the 2D constellation and says why', async ({ page }) => {
    // One frame blocks the page for 1.3 s shortly after opening: a hang.
    await page.addInitScript(() => {
      const raf = window.requestAnimationFrame.bind(window);
      let stalled = false;
      const t0 = Date.now();
      window.requestAnimationFrame = (cb) => raf((t) => {
        if (!stalled && Date.now() - t0 > 2000) { stalled = true; const end = Date.now() + 1300; while (Date.now() < end) { /* hang */ } }
        cb(t);
      });
    });
    const errors = await open(page);
    await expect.poll(() => currentView(page), { timeout: 15_000 }).toBe('2d');
    await expect(page.locator('#gpunote')).toContainText('froze');
    await expect(page.locator('#viewmode')).toBeEnabled();
    expect(errors).toEqual([]);
  });

  test('a machine with little memory or few cores keeps the 3D sky', async ({ page }) => {
    await open(page);
    const choice = await page.evaluate(`(() => {
      webglSupport = () => 'ok';
      Object.defineProperty(navigator, 'deviceMemory', { configurable: true, get: () => 2 });
      Object.defineProperty(navigator, 'hardwareConcurrency', { configurable: true, get: () => 2 });
      return chooseView();
    })()`);
    expect(choice).toEqual({ mode: '3d', reason: 'auto' });
  });

  test('clicking a paper opens its summary beside the sky and dims the rest', async ({ page }) => {
    const errors = await open(page, '?view=2d');
    await page.evaluate(`select('s03.s03-problem')`);
    const side = page.locator('#side');
    await expect(side).toBeVisible();
    await expect(side.locator('h2')).toHaveText('sun of s03');
    for (const heading of ['Application topic', 'AI topic', 'Problem', 'Application', 'Main novelty', 'Family', 'Results', 'Conclusions']) {
      await expect(side.locator('dt').filter({ hasText: new RegExp(`^${heading}$`) })).toHaveCount(1);
    }
    await expect(side.locator('.side-node')).toContainText('problem of s03');
    await expect(side.locator('.side-links button')).toHaveCount(2);
    const lit = await page.evaluate(`[...selectedKeep]`) as string[];
    expect(lit).toContain('s03.s03-novelty');
    expect(lit).toContain('s02.s02-novelty');
    expect(lit).not.toContain('s10.s10-sun');
    await page.keyboard.press('Escape');
    await expect(side).toBeHidden();
    expect(errors).toEqual([]);
  });

  test('a linked paper in the panel opens its own summary', async ({ page }) => {
    await open(page, '?view=2d');
    await page.evaluate(`select('s03.s03-sun')`);
    await page.locator('#side .side-links button').first().click();
    await expect(page.locator('#side h2')).toHaveText(/sun of s0[24]/);
  });

  test("a paper's name in the 3D sky is a button to its summary", async ({ page }) => {
    await open(page, '?view=3d');
    test.skip(await currentView(page) !== '3d', 'no WebGL in this browser');
    const name = page.locator('.atlas-names div:visible').first();
    await expect(name).toBeVisible({ timeout: 5000 });
    const title = await name.textContent();
    await name.click();
    await expect(page.locator('#side')).toBeVisible();
    await expect(page.locator('#side .side-meta')).toContainText(String(title));
  });

  test('a citation opened from the dashboard selects its paper', async ({ page }) => {
    await open(page, '?view=2d');
    await page.evaluate(`focusReference('s07.s07-sun')`);
    await expect(page.locator('#side h2')).toHaveText('sun of s07');
  });
});
