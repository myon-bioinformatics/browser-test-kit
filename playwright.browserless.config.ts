import {defineConfig} from '@playwright/test';

// The Playwright test runner is reused; no browser fixture or engine is required.
export default defineConfig({
  testDir: './tests/browserless',
  outputDir: 'test-results/browserless-node',
  reporter: [['list'], ['junit', {outputFile: 'test-results/junit/browserless-node.xml'}]],
  retries: 0,
});
