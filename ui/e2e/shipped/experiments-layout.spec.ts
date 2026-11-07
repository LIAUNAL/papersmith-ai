import { expect, test, type Page } from '@playwright/test';

/**
 * The Experiments tab in the order of the flow: the stepper first, every
 * section behind a bar that folds, the infrastructure folded at the end, and
 * the operator's choices remembered after a reload.
 */
async function gotoExperiments(page: Page): Promise<void> {
  await page.goto('/#experiments');
  await expect(page.locator('#experimentsRoot .exp-flow-steps')).toBeVisible({ timeout: 15_000 });
}

const fold = (page: Page, name: string) => page.locator(`#experimentsRoot details[data-exp-fold="${name}"]`);

test.describe('the experiments tab', () => {
  test('opens on the stepper, with the infrastructure folded at the end', async ({ page }) => {
    await page.evaluate(() => window.localStorage?.removeItem('papersmith.expFolds')).catch(() => {});
    await gotoExperiments(page);
    await page.evaluate(() => window.localStorage.removeItem('papersmith.expFolds'));
    await gotoExperiments(page);
    const steps = await page.locator('#experimentsRoot .exp-flow-steps').boundingBox();
    const infra = await fold(page, 'infrastructure').boundingBox();
    expect(steps!.y).toBeLessThan(infra!.y);
    await expect(fold(page, 'protocol')).toHaveAttribute('open', '');
    await expect(fold(page, 'infrastructure')).not.toHaveAttribute('open', '');
    await expect(page.locator('#expRunOptions')).toBeHidden();
  });

  test('a folded section opens on a click and stays open after a reload', async ({ page }) => {
    await gotoExperiments(page);
    await page.evaluate(() => window.localStorage.removeItem('papersmith.expFolds'));
    await gotoExperiments(page);
    await fold(page, 'infrastructure').locator(':scope > summary').click();
    await expect(page.locator('#expRunOptions')).toBeVisible();
    await gotoExperiments(page);
    await expect(fold(page, 'infrastructure')).toHaveAttribute('open', '');
    await fold(page, 'protocol').locator(':scope > summary').click();
    await gotoExperiments(page);
    await expect(fold(page, 'protocol')).not.toHaveAttribute('open', '');
    await page.evaluate(() => window.localStorage.removeItem('papersmith.expFolds'));
  });

  test('the tutor closes the tab, folded until asked for', async ({ page }) => {
    await gotoExperiments(page);
    await page.evaluate(() => window.localStorage.removeItem('papersmith.expFolds'));
    await gotoExperiments(page);
    const tutor = page.locator('#xtutorFold');
    await expect(tutor).not.toHaveAttribute('open', '');
    await expect(page.locator('#xtutorPanel')).toBeHidden();
    await tutor.locator(':scope > summary').click();
    await expect(page.locator('#xtutorPanel')).toBeVisible();
    await page.evaluate(() => window.localStorage.removeItem('papersmith.expFolds'));
  });
});
