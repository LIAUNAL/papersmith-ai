import { expect, test, type Page } from '@playwright/test';

/**
 * The dashboard `smith ui` actually serves: the hand-written
 * `skills/_core/command_center/static/index.html`, not the Vite app the specs
 * one directory up cover. It publishes no readiness attribute, so "loaded"
 * means the first status payload reached the page: the proposal title stopped
 * saying it is loading and the run selector holds a real answer.
 */
const TABS = [
  'flow',
  'pipeline',
  'modelo',
  'experiments',
  'novelty',
  'sections',
  'atlas',
  'preview',
  'artifacts',
  'historia',
  'telemetria',
  'doctor',
] as const;

async function gotoLoaded(page: Page, hash = ''): Promise<void> {
  await page.goto(`/${hash}`);
  await expect(page.locator('#metaProposalTitle')).not.toHaveText(/^(Loading|Cargando)/, {
    timeout: 15_000,
  });
}

const tabButton = (page: Page, tab: string) =>
  page.locator(`.tab-nav__btn[onclick="navigateTab('${tab}')"]`);

test.describe('the dashboard loads', () => {
  test('is the shipped page, with a workspace identity', async ({ page }) => {
    await gotoLoaded(page);
    await expect(page).toHaveTitle(/PaperSmith AI/);
    await expect(page.locator('#metaProposalTitle')).not.toBeEmpty();
    await expect(page.locator('#totalsContainer')).not.toBeEmpty();
  });

  test('raises no uncaught page error on any tab', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await gotoLoaded(page);
    for (const tab of TABS) {
      await tabButton(page, tab).click();
      await expect(page.locator(`#pane-${tab}`)).toBeVisible();
    }
    expect(errors).toEqual([]);
  });

  test('no same-origin request fails with a server error', async ({ page }) => {
    const failures: string[] = [];
    page.on('response', (response) => {
      if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
    });
    await gotoLoaded(page);
    for (const tab of TABS) {
      await tabButton(page, tab).click();
      await expect(page.locator(`#pane-${tab}`)).toBeVisible();
    }
    expect(failures).toEqual([]);
  });
});

test.describe('tab navigation', () => {
  test('the nav offers exactly the known tabs', async ({ page }) => {
    await gotoLoaded(page);
    await expect(page.locator('.tab-nav__btn')).toHaveCount(TABS.length);
  });

  for (const tab of TABS) {
    test(`${tab}: a click activates it alone and writes the hash`, async ({ page }) => {
      await gotoLoaded(page);
      await tabButton(page, tab).click();
      await expect(tabButton(page, tab)).toHaveClass(/active/);
      await expect(page.locator('.tab-nav__btn.active')).toHaveCount(1);
      await expect(page.locator(`#pane-${tab}`)).toBeVisible();
      await expect(page.locator('.tab-pane.active')).toHaveCount(1);
      expect(new URL(page.url()).hash).toBe(`#${tab}`);
    });

    test(`${tab}: a deep link opens it`, async ({ page }) => {
      await gotoLoaded(page, `#${tab}`);
      await expect(page.locator(`#pane-${tab}`)).toBeVisible();
      await expect(tabButton(page, tab)).toHaveClass(/active/);
    });
  }

  test('the retired gates link lands on the pipeline', async ({ page }) => {
    await gotoLoaded(page, '#gates');
    await expect(page.locator('#pane-pipeline')).toBeVisible();
  });

  test('browser back returns to the previous tab', async ({ page }) => {
    await gotoLoaded(page);
    await tabButton(page, 'pipeline').click();
    await tabButton(page, 'doctor').click();
    await page.goBack();
    await expect(page.locator('#pane-pipeline')).toBeVisible();
    await expect(page.locator('.tab-pane.active')).toHaveCount(1);
  });
});

test.describe('theme and language', () => {
  test('the theme toggles and survives a reload', async ({ page }) => {
    await gotoLoaded(page);
    const html = page.locator('html');
    const before = await html.getAttribute('data-theme');
    const after = before === 'dark' ? 'light' : 'dark';
    await page.locator('#themeBtn').click();
    await expect(html).toHaveAttribute('data-theme', after);
    await page.reload();
    await expect(html).toHaveAttribute('data-theme', after);
  });

  test('the language selector relabels the nav and survives a reload', async ({ page }) => {
    await gotoLoaded(page);
    const label = tabButton(page, 'preview');
    await expect(label).toHaveText('PDF Preview');
    await page.locator('#langSelect').selectOption('es');
    await expect(label).not.toHaveText('PDF Preview');
    const spanish = await label.textContent();
    await page.reload();
    await expect(page.locator('#langSelect')).toHaveValue('es');
    await expect(label).toHaveText(spanish ?? '');
  });
});

test.describe('layout', () => {
  for (const tab of TABS) {
    test(`${tab}: the page does not scroll sideways`, async ({ page }) => {
      await gotoLoaded(page, `#${tab}`);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
});
