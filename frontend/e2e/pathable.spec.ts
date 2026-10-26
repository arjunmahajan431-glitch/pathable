import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

/**
 * End-to-end journeys against the real backend in demo mode.
 *
 * These coordinates are inside the committed Woodbury, Minnesota sample area
 * (config/areas.yaml). They are public sidewalk points, not a home or school.
 * Assertions are about the interface contract, not real-world accessibility.
 */
const START = { lat: '44.91569', lon: '-92.94415' };
const END = { lat: '44.91814', lon: '-92.95048' };

// Public landmarks in the Saint Paul sample: City Hall to the State Capitol.
const SAINT_PAUL_START = { lat: '44.9442823', lon: '-93.0939523' };
const SAINT_PAUL_END = { lat: '44.95526', lon: '-93.10243' };

async function fillCoordinates(page: Page, which: 'start' | 'end', point: { lat: string; lon: string }) {
  // Wait for the app boot request before touching the form.
  await expect(page.getByRole('heading', { name: 'Plan a trip' })).toBeVisible();
  await page.locator(`#${which}-lat`).fill(point.lat);
  await page.locator(`#${which}-lon`).fill(point.lon);
  const section = page.getByRole('region', { name: which === 'start' ? 'Start' : 'Destination' });
  await section.getByRole('button', { name: 'Apply' }).click();
}

async function planRoute(
  page: Page,
  start: { lat: string; lon: string } = START,
  end: { lat: string; lon: string } = END,
) {
  await fillCoordinates(page, 'start', start);
  await fillCoordinates(page, 'end', end);
  await page.getByRole('button', { name: 'Find routes' }).click();
  await expect(page.getByRole('heading', { name: 'Route comparison' })).toBeVisible();
}

async function waitForTiles(page: Page) {
  await page.waitForTimeout(800);
  await page
    .waitForFunction(
      () => {
        const tiles = Array.from(document.querySelectorAll<HTMLImageElement>('.leaflet-tile'));
        return tiles.length > 0 && tiles.every((tile) => tile.complete);
      },
      undefined,
      { timeout: 20_000 },
    )
    .catch(() => undefined);
}

async function waitForPlaybackProgress(page: Page, minimumPercent: number) {
  const progress = page.getByRole('progressbar', { name: 'Route animation progress' });
  await expect
    .poll(async () => Number(await progress.getAttribute('aria-valuenow')), { timeout: 10_000 })
    .toBeGreaterThanOrEqual(minimumPercent);
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Plan a trip' })).toBeVisible();

  // The active city is backend state, not per-page state. Reset to Woodbury so
  // the city-switch test cannot leak into the tests that follow it.
  const switcher = page.getByRole('group', { name: 'Mapping area' });
  const woodbury = switcher.getByRole('button', { name: 'Woodbury' });
  if ((await woodbury.getAttribute('aria-pressed')) !== 'true') {
    await woodbury.click();
    await expect(woodbury).toHaveAttribute('aria-pressed', 'true', { timeout: 60_000 });
  }
});

test('plan, compare, inspect, explain and report', async ({ page }) => {
  await planRoute(page);

  const preferred = page.getByRole('article', { name: 'Preferred route summary' });
  const shortest = page.getByRole('article', { name: 'Shortest (length only) route summary' });
  await expect(preferred).toBeVisible();
  await expect(shortest).toBeVisible();

  // Verified against the Woodbury sample graph: the preferred route takes a
  // 138 m detour to avoid a DEM-estimated 9.3% uphill grade on Dunmore Road.
  await expect(preferred).toContainText('1,173 m');
  await expect(shortest).toContainText('1,035 m');
  await expect(shortest).toContainText('None known');

  // The explanation states the detour in plain language.
  await expect(
    page.getByRole('region', { name: 'Route explanation' }).getByText(/138 m \(\+13%\)/),
  ).toBeVisible();

  // "Why not the shortest route" names the steep segment.
  await page.getByText('Why not the shortest route').click();
  await expect(page.getByText(/9\.3% uphill grade/).first()).toBeVisible();

  // Segment inspector shows the cost arithmetic and provenance. The text list
  // is the non-map route description.
  const segments = page.getByRole('region', { name: 'Route segments' });
  await segments.getByRole('button').first().click();
  await expect(page.getByRole('heading', { name: 'How the effort score is built' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Where each value comes from' })).toBeVisible();
  await expect(page.getByText('OSM mapped').first()).toBeVisible();
  await expect(page.getByText('DEM estimate').first()).toBeVisible();

  // Report flow: open the dialog, submit, see the unverified message.
  await page.getByRole('button', { name: 'Report a problem' }).click();
  const dialog = page.getByRole('dialog', { name: 'Report a problem' });
  await expect(dialog).toBeVisible();
  // Keep the test report away from the demo route so it does not change later
  // route results or screenshots; it is still inside the selected city.
  await dialog.getByLabel('Latitude').fill('44.918900');
  await dialog.getByLabel('Longitude').fill('-92.936600');
  await dialog.getByLabel('Category').selectOption('construction');
  await dialog.getByLabel(/Description/).fill('E2E test report: temporary fencing across the sidewalk.');
  await dialog.getByRole('button', { name: 'Send report for review' }).click();
  await expect(dialog.getByRole('status')).toContainText('unverified until');
  await dialog.getByRole('button', { name: 'Done' }).click();
  await expect(dialog).toBeHidden();

  // Editing a coordinate must not leave the previous route looking current.
  await page.locator('#start-lat').fill('44.915700');
  await page.getByRole('region', { name: 'Start' }).getByRole('button', { name: 'Apply' }).click();
  await expect(page.getByRole('heading', { name: 'Route comparison' })).toBeHidden();
  await expect(page.getByText('Start changed. Select Find routes to update the route.')).toBeAttached();
});

test('keyboard-only planning has a non-map path', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Plan a trip' })).toBeVisible();

  const activeId = () => page.evaluate(() => document.activeElement?.id ?? '');
  async function tabTo(id: string, limit = 120) {
    for (let i = 0; i < limit; i += 1) {
      if ((await activeId()) === id) return;
      await page.keyboard.press('Tab');
    }
    throw new Error(`Could not reach #${id} with the Tab key`);
  }

  await tabTo('start-lat');
  await page.keyboard.type(START.lat);
  await page.keyboard.press('Tab');
  await page.keyboard.type(START.lon);
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');

  await tabTo('end-lat');
  await page.keyboard.type(END.lat);
  await page.keyboard.press('Tab');
  await page.keyboard.type(END.lon);
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');

  // Tab from the end "Apply" button to "Find routes" and submit with Enter.
  let found = false;
  for (let i = 0; i < 30; i += 1) {
    const text = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? '');
    if (text === 'Find routes') {
      found = true;
      break;
    }
    await page.keyboard.press('Tab');
  }
  expect(found).toBe(true);
  await page.keyboard.press('Enter');

  await expect(page.getByRole('heading', { name: 'Route comparison' })).toBeVisible();
  // Results receive focus so a screen reader announces the outcome.
  await expect(page.getByLabel('Route results')).toBeFocused();
});

test('axe: no serious or critical WCAG 2.2 A/AA violations', async ({ page }) => {
  await planRoute(page);
  // "Why this route" is open by default; open the unknowns disclosure as well.
  await page.getByText("What we don't know").click();
  await page.getByRole('region', { name: 'Route segments' }).getByRole('button').first().click();

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();

  const serious = results.violations.filter(
    (violation) => violation.impact === 'serious' || violation.impact === 'critical',
  );
  expect(
    serious.map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.map((node) => node.target),
    })),
  ).toEqual([]);
});

test('Saint Paul city switch, route playback and dark mode', async ({ page }) => {
  test.setTimeout(120_000);
  await expect(page.getByRole('heading', { name: 'Plan a trip' })).toBeVisible();

  const switcher = page.getByRole('group', { name: 'Mapping area' });
  await switcher.getByRole('button', { name: 'Saint Paul' }).click();
  const saintPaulButton = switcher.getByRole('button', { name: 'Saint Paul' });
  await expect(saintPaulButton).toHaveAttribute('aria-pressed', 'true', { timeout: 60_000 });
  await expect(page.getByText('Saint Paul, Minnesota', { exact: true })).toBeVisible();

  await planRoute(page, SAINT_PAUL_START, SAINT_PAUL_END);

  // Verified against the Saint Paul sample graph: the preferred route takes a
  // 282 m detour to avoid two mapped barrier segments.
  const preferred = page.getByRole('article', { name: 'Preferred route summary' });
  const shortest = page.getByRole('article', { name: 'Shortest (length only) route summary' });
  await expect(preferred).toContainText('1,951 m');
  await expect(shortest).toContainText('1,669 m');
  await expect(
    page.getByRole('region', { name: 'Route explanation' }).getByText(/282 m \(\+17%\)/),
  ).toBeVisible();

  await page.evaluate(() => window.scrollTo(0, 0));
  await waitForTiles(page);

  // The playback control animates a dot and a flowing dash along the preferred route.
  await page.getByRole('button', { name: 'Play route' }).click();
  await expect(page.getByRole('button', { name: 'Pause route' })).toBeVisible();
  const progress = page.getByRole('progressbar', { name: 'Route animation progress' });
  await expect(progress).toBeVisible();
  await waitForPlaybackProgress(page, 40);
  const dot = page.locator('.route-dot');
  await expect(dot).toBeVisible();
  expect((await dot.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(12);
  await page.screenshot({ path: '../docs/images/saint-paul-route.png' });
  await page.getByRole('button', { name: 'Pause route' }).click();
  await expect(dot).toHaveCount(0);

  await page.getByRole('button', { name: 'Switch to dark mode' }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(page.getByRole('button', { name: 'Switch to light mode' })).toBeVisible();
  await waitForTiles(page);
  await page.screenshot({ path: '../docs/images/saint-paul-route-dark.png' });

  // The theme changes surfaces and controls, not the route semantics.
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === 'serious' || violation.impact === 'critical',
  );
  expect(
    serious.map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.map((node) => node.target),
    })),
  ).toEqual([]);
});

test('mobile layout keeps planning, map and results usable', async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Plan a trip' })).toBeVisible();

  // No page-level sideways scrolling at a phone-width viewport.
  const width = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(width.scroll).toBeLessThanOrEqual(width.client + 1);

  await planRoute(page);
  await expect(page.getByRole('region', { name: 'Route comparison' })).toBeVisible();
  await expect(page.getByRole('region', { name: /Interactive map/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Play route' })).toBeVisible();

  // The compact map controls and the full text route remain available.
  await page.getByRole('button', { name: 'Play route' }).click();
  await expect(page.getByRole('button', { name: 'Pause route' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Route segments' })).toBeVisible();

  // The page still fits after results, map legend, and segment details render.
  const after = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(after.scroll).toBeLessThanOrEqual(after.client + 1);
});

test('screenshots for the README', async ({ page }) => {
  await planRoute(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await waitForTiles(page);
  await page.getByRole('button', { name: 'Play route' }).click();
  await waitForPlaybackProgress(page, 40);
  await page.screenshot({ path: '../docs/images/desktop-route.png' });
  await page.getByRole('button', { name: 'Pause route' }).click();

  await page.getByRole('region', { name: 'Route segments' }).getByRole('button').first().click();
  await expect(page.getByRole('heading', { name: 'How the effort score is built' })).toBeVisible();
  const details = page.getByRole('region', { name: 'Selected segment details' });
  await details.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await details.screenshot({ path: '../docs/images/segment-details.png' });

  await page.getByRole('button', { name: 'Report a problem' }).click();
  await page.getByRole('dialog', { name: 'Report a problem' }).screenshot({
    path: '../docs/images/report-dialog.png',
  });
});
