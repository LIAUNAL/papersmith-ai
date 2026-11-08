import { expect, test, type Page } from '@playwright/test';

/**
 * The dashboard's theme rules every panel, whatever the operating system
 * prefers: the Archify flow and the manuscript summary are iframes that used
 * to follow the system instead (white on a light Ubuntu, black on a dark Mac).
 */
const luminance = (rgb: string): number => {
  const [r, g, b] = (rgb.match(/[\d.]+/g) || ['0', '0', '0']).map(Number);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

async function frameBackground(page: Page, id: string): Promise<string> {
  const frame = page.frameLocator(`#${id}`);
  await expect(frame.locator('body')).toBeVisible({ timeout: 15_000 });
  return page.evaluate((frameId) => {
    const doc = (document.getElementById(frameId) as HTMLIFrameElement).contentDocument!;
    for (let node: Element | null = doc.body; node; node = node.parentElement) {
      const colour = getComputedStyle(node).backgroundColor;
      const parts = colour.match(/[\d.]+/g);
      if (parts && (parts.length < 4 || Number(parts[3]) > 0)) return colour;
    }
    return 'rgb(255, 255, 255)';
  }, id);
}

for (const system of ['light', 'dark'] as const) {
  for (const theme of ['dark', 'light'] as const) {
    test(`a ${system} system with the ${theme} dashboard theme`, async ({ browser }) => {
      const context = await browser.newContext({ colorScheme: system, viewport: { width: 1280, height: 900 } });
      const page = await context.newPage();
      await page.goto('/#flow');
      await expect(page.locator('#metaProposalTitle')).not.toHaveText(/^(Loading|Cargando)/, { timeout: 15_000 });
      await page.evaluate((wanted) => {
        if (document.documentElement.getAttribute('data-theme') !== wanted) (window as any).toggleTheme();
      }, theme);
      const dark = (rgb: string) => (theme === 'dark' ? luminance(rgb) < 90 : luminance(rgb) > 160);
      await expect.poll(async () => dark(await frameBackground(page, 'flowIframe')), { timeout: 10_000 }).toBe(true);
      await page.evaluate(() => (window as any).navigateTab('novelty'));
      await expect.poll(async () => dark(await frameBackground(page, 'manuscriptSummaryIframe')), { timeout: 15_000 }).toBe(true);
      await page.reload();
      await page.evaluate(() => (window as any).navigateTab('flow'));
      await expect.poll(async () => dark(await frameBackground(page, 'flowIframe')), { timeout: 15_000 }).toBe(true);
      await context.close();
    });
  }
}
