import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-dev',
  workers: 1,
  timeout: 30_000,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    launchOptions: {
      // Hardware-accelerated or SwiftShader WebGL fallback for headless Chromium
      args: [
        '--use-gl=angle',
        '--use-angle=swiftshader',
        '--enable-unsafe-swiftshader',
        '--enable-webgl',
      ],
    },
  },
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVER ? undefined : {
    command: 'npm run dev -- --port 5173',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
  projects: [
    {
      name: 'chromium-headless',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
        headless: true,
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
          args: process.env.PLAYWRIGHT_EXECUTABLE_PATH ? ['--no-sandbox'] : [],
        },
      },
    },
  ],
});
