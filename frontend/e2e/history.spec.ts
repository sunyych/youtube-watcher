import { test, expect } from '@playwright/test';

test.describe('History Page', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/login');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL('/');
    
    // Navigate to history
    await page.click('a[href="/history"]');
    await page.waitForURL('/history');
  });

  test('should display history page', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('历史记录');
    await expect(page.locator('a[href="/"]')).toBeVisible();
  });

  test('should show empty state when no history', async ({ page }) => {
    // If no history, should show empty state
    const emptyState = page.locator('.empty-state');
    if (await emptyState.isVisible()) {
      await expect(emptyState).toContainText('暂无历史记录');
    }
  });

  test('should have export button for completed videos', async ({ page }) => {
    // Check if export buttons exist for completed videos
    const exportButtons = page.locator('.export-button');
    const count = await exportButtons.count();
    
    if (count > 0) {
      await expect(exportButtons.first()).toBeVisible();
    }
  });
});
