import { expect, test, type Page } from '@playwright/test';

/**
 * The text-size control of the shipped dashboard: ×1, ×1.25, ×1.5 and ×2,
 * remembered per browser, with a header and a tab strip that hold at every
 * size on a desktop, a tablet and a phone.
 */
const SCALES = ['1', '1.25', '1.5', '2'] as const;
const SCREENS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'phone', width: 390, height: 844 },
] as const;
const TABS = ['flow', 'modelo', 'experiments', 'novelty'] as const;

async function gotoLoaded(page: Page, hash = ''): Promise<void> {
  await page.goto(`/${hash}`);
  await expect(page.locator('#metaProposalTitle')).not.toHaveText(/^(Loading|Cargando)/, {
    timeout: 15_000,
  });
}

const rootFontSize = (page: Page) =>
  page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));

/** What of the header, the totals strip or the tab strip reaches past the screen. */
const spilled = (page: Page) =>
  page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const pageSpills = document.documentElement.scrollWidth > width + 1;
    const nodes = [...document.querySelectorAll('.topbar, .topbar > *, .meta-strip, .tabs-nav')]
      .filter((node) => node.getBoundingClientRect().right > width + 1)
      .map((node) => node.className || node.tagName);
    return pageSpills ? ['document', ...nodes] : nodes;
  });

test.describe('the text-size control', () => {
  test('offers four sizes and scales the text', async ({ page }) => {
    await gotoLoaded(page);
    const select = page.locator('#textSizeSelect');
    await expect(select).toBeVisible();
    await expect(select.locator('option')).toHaveCount(4);
    const base = await rootFontSize(page);
    for (const scale of SCALES) {
      await select.selectOption(scale);
      expect(await rootFontSize(page)).toBeCloseTo(base * Number(scale), 1);
    }
  });

  test('is remembered after a reload', async ({ page }) => {
    await gotoLoaded(page);
    const base = await rootFontSize(page);
    await page.locator('#textSizeSelect').selectOption('1.5');
    await gotoLoaded(page);
    await expect(page.locator('#textSizeSelect')).toHaveValue('1.5');
    expect(await rootFontSize(page)).toBeCloseTo(base * 1.5, 1);
    await page.locator('#textSizeSelect').selectOption('1');
  });

  for (const screen of SCREENS) {
    test(`the header and tabs hold at every size on a ${screen.name}`, async ({ page }) => {
      await page.setViewportSize({ width: screen.width, height: screen.height });
      await gotoLoaded(page);
      for (const scale of SCALES) {
        await page.locator('#textSizeSelect').selectOption(scale);
        for (const tab of TABS) {
          await page.locator(`.tab-nav__btn[onclick="navigateTab('${tab}')"]`).click();
          await page.waitForTimeout(150);
          expect(await spilled(page), `×${scale} on ${tab}`).toEqual([]);
        }
        const title = await page.locator('.topbar h1').boundingBox();
        const lineHeight = await page.locator('.topbar h1').evaluate((h1) => parseFloat(getComputedStyle(h1).lineHeight));
        expect(title!.height, `×${scale}: the title keeps to one line`).toBeLessThanOrEqual(lineHeight * 1.2);
        const header = await page.locator('.topbar').boundingBox();
        expect(header!.height, `×${scale}: the header leaves room for the page`).toBeLessThanOrEqual(screen.height * 0.4);
      }
      await page.locator('#textSizeSelect').selectOption('1');
    });
  }
});
