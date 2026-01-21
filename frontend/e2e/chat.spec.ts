import { test, expect } from '@playwright/test';

test.describe('Chat Interface', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/login');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL('/');
  });

  test('should display main interface after login', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('YouTube Watcher');
    await expect(page.locator('input[type="text"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('should show navigation links', async ({ page }) => {
    await expect(page.locator('a[href="/history"]')).toBeVisible();
    await expect(page.locator('a[href="/settings"]')).toBeVisible();
    await expect(page.locator('button:has-text("退出")')).toBeVisible();
  });

  test('should have language selector', async ({ page }) => {
    const languageSelector = page.locator('.language-selector');
    await expect(languageSelector).toBeVisible();
    
    // Check if it has options
    await languageSelector.click();
    await expect(page.locator('option')).toContainText('自动检测');
  });

  test('should submit video URL', async ({ page }) => {
    const testUrl = 'https://www.youtube.com/watch?v=jNQXAC9IVRw';
    
    // Fill in URL
    await page.fill('input[type="text"]', testUrl);
    
    // Submit form
    await page.click('button[type="submit"]');
    
    // Should show loading or processing state
    await expect(page.locator('button[type="submit"]')).toBeDisabled();
  });

  test('should navigate to history page', async ({ page }) => {
    await page.click('a[href="/history"]');
    await expect(page).toHaveURL('/history');
    await expect(page.locator('h1')).toContainText('历史记录');
  });

  test('should navigate to settings page', async ({ page }) => {
    await page.click('a[href="/settings"]');
    await expect(page).toHaveURL('/settings');
    await expect(page.locator('h1')).toContainText('设置');
  });

  test('should logout', async ({ page }) => {
    await page.click('button:has-text("退出")');
    await expect(page).toHaveURL(/.*login/);
  });
});
