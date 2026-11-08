import { expect, test } from '@playwright/test';

/**
 * The header's run selector names each proposal revision by its short run id
 * (r07), keeps the full file name as the option's tooltip, and never widens the
 * header (#156).
 */
const LONG = 'research-concept-replica-batched-multi-colour-metropolis-for-classical-spin-Lr07.md';
const RUNS = [LONG, 'research-concept-replica-batched-multi-colour-metropolis-for-classical-spin-Lr06.md', 'notes.md'];

test('the run selector shows short run ids with the file name as tooltip', async ({ page }) => {
  await page.route('**/api/status*', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body, all_runs: RUNS, active_run: 'r07' } });
  });
  await page.goto('/');
  const select = page.locator('#runSelector');
  await expect(select.locator('option')).toHaveCount(3);
  const options = await select.locator('option').evaluateAll((nodes) =>
    nodes.map((n) => ({ text: n.textContent, value: (n as HTMLOptionElement).value, title: n.getAttribute('title') })),
  );
  expect(options).toEqual([
    { text: 'r07', value: LONG, title: LONG },
    { text: 'r06', value: RUNS[1], title: RUNS[1] },
    { text: 'notes.md', value: 'notes.md', title: 'notes.md' },
  ]);
  await expect(select).toHaveValue(LONG);
  await expect(select).toHaveAttribute('title', LONG);
  const title = page.locator('#metaProposalTitle');
  const lineHeight = await title.evaluate((n) => parseFloat(getComputedStyle(n).lineHeight) || 0);
  const height = await title.evaluate((n) => n.getBoundingClientRect().height);
  if (lineHeight) expect(height).toBeLessThanOrEqual(lineHeight * 2.2);
});
