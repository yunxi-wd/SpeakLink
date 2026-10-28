/** End-to-end tests run against independently started real frontend/backend servers. */
import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests/e2e', timeout: 90000, workers: 1, use: { baseURL: process.env.E2E_URL || 'http://127.0.0.1:3000', headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure', launchOptions: process.env.PLAYWRIGHT_CHROME_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROME_PATH } : {} }, reporter: [['list'], ['json', { outputFile: 'test-results/e2e.json' }]] });
