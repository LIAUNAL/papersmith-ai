import { expect, test, type Page } from '@playwright/test';

/**
 * The Concept Map & Model and Novelty & Findings tabs fold like Experiments:
 * every marked block sits behind a bar with its title, the action blocks start
 * open, and the operator's choice survives a reload.
 */
async function gotoTab(page: Page, tab: string): Promise<void> {
  await page.goto(`/#${tab}`);
  await expect(page.locator('#metaProposalTitle')).not.toHaveText(/^(Loading|Cargando)/, { timeout: 15_000 });
}

const fold = (page: Page, name: string) => page.locator(`details[data-fold-name="${name}"]`);

test.describe('folded tabs', () => {
  test('the concept map tab wraps its blocks, open where they ask for action', async ({ page }) => {
    await gotoTab(page, 'modelo');
    await page.evaluate(() => window.localStorage.removeItem('papersmith.folds'));
    await gotoTab(page, 'modelo');
    for (const name of ['model:problem', 'model:noveltyTree', 'model:contribution', 'model:math']) {
      await expect(fold(page, name)).toHaveAttribute('open', '');
    }
    for (const name of ['model:pillars', 'model:hypotheses', 'model:map']) {
      await expect(fold(page, name)).not.toHaveAttribute('open', '');
    }
    await expect(fold(page, 'model:map').locator(':scope > summary')).toContainText('Concept Map');
    await expect(page.locator('#modelConceptLayers')).toBeHidden();
  });

  test('a fold the operator opens stays open after a reload', async ({ page }) => {
    await gotoTab(page, 'modelo');
    await page.evaluate(() => window.localStorage.removeItem('papersmith.folds'));
    await gotoTab(page, 'modelo');
    await fold(page, 'model:map').locator(':scope > summary').click();
    await expect(page.locator('#modelConceptLayers')).toBeVisible();
    await gotoTab(page, 'modelo');
    await expect(fold(page, 'model:map')).toHaveAttribute('open', '');
    await page.evaluate(() => window.localStorage.removeItem('papersmith.folds'));
  });

  test('the novelty tab folds its summary diagram', async ({ page }) => {
    await gotoTab(page, 'novelty');
    await expect(fold(page, 'novelty:summary').locator(':scope > summary')).toContainText('Manuscript summary');
    await expect(page.locator('#manuscriptSummaryIframe')).toBeVisible();
  });
});
