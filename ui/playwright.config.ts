import { defineConfig, devices } from '@playwright/test';

/**
 * Browser checks for the Paper Command Center.
 *
 * Everything runs against the real FastAPI server from
 * `skills/_core/command_center/server.py`. Checking `vite preview` instead
 * would verify a stand-in: the server we ship resolves assets differently and
 * validates the `Host` header, and both have broken the dashboard before.
 *
 * The repository holds two frontends (see "Two frontends" in `docs/cli.md`),
 * so there are two servers:
 *
 * - `shipped` (port 8098) serves `skills/_core/command_center/static/` and its
 *   hand-written `index.html`, the dashboard `smith ui` gives every user. Its
 *   specs live in `e2e/shipped/`.
 * - `desktop` and `narrow` (port 8099) serve a fresh Vite build of `ui/src`.
 *   That build goes under `node_modules/.cache`, never to `ui/dist`, which the
 *   server would prefer over `static/`, and never to `static/`, which the
 *   default `npm run build` empties, shipped dashboard included.
 *
 * `PAPERSMITH_UI_DIST` is set on both, so neither depends on what happens to
 * sit in `ui/dist`. The server's allow-list accepts `127.0.0.1:<port>` on a
 * loopback bind, so no `--allowed-host` is needed, and both ports stay clear
 * of the 8080 default a developer is likely to be running.
 *
 * The interpreter is the one `package.json` names, provisioned by
 * `scripts/setup_env.py`.
 *
 * Vitest owns `src/**\/*.test.*`; this owns `e2e/**\/*.spec.ts`. They never
 * collide, and they are never the same command.
 */
const VITE_PORT = 8099;
const SHIPPED_PORT = 8098;
const REPO_ROOT = new URL('..', import.meta.url).pathname;
const PYTHON = '.micromamba/envs/papersmith/bin/python';
const VITE_DIST = `${REPO_ROOT}ui/node_modules/.cache/e2e-dist`;
const SHIPPED_DIST = `${REPO_ROOT}skills/_core/command_center/static`;

const serve = (port: number): string =>
  `${PYTHON} -m skills._core.command_center.server --port ${port} --no-browser --log-level warning`;

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  // A layout assertion that fails because a neighbour shifted is a real
  // failure, not a flake to retry away.
  retries: 0,
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: `http://127.0.0.1:${VITE_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'shipped',
      testMatch: 'shipped/**/*.spec.ts',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        baseURL: `http://127.0.0.1:${SHIPPED_PORT}`,
      },
    },
    {
      name: 'desktop',
      testIgnore: 'shipped/**',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      // The stylesheet turns the element panel into a bottom sheet under 900px;
      // that breakpoint needs a viewport that actually crosses it.
      name: 'narrow',
      use: { ...devices['Desktop Chrome'], viewport: { width: 820, height: 900 } },
      testMatch: '**/layout.spec.ts',
      testIgnore: 'shipped/**',
    },
  ],
  webServer: [
    {
      command: serve(SHIPPED_PORT),
      cwd: REPO_ROOT,
      env: { PAPERSMITH_UI_DIST: SHIPPED_DIST },
      url: `http://127.0.0.1:${SHIPPED_PORT}/api/state`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `(cd ui && npx vite build --outDir "${VITE_DIST}" --emptyOutDir) && ${serve(VITE_PORT)}`,
      cwd: REPO_ROOT,
      env: { PAPERSMITH_UI_DIST: VITE_DIST },
      url: `http://127.0.0.1:${VITE_PORT}/api/state`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
