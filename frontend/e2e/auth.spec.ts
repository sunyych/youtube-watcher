import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('should show login page when not authenticated', async ({ page }) => {
    await page.goto('/');
    
    // Should redirect to login
    await expect(page).toHaveURL(/.*login/);
    await expect(page.locator('h1')).toContainText('YouTube Watcher');
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('should login with correct password', async ({ page }) => {
    await page.goto('/login');
    
    // Fill in password
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    
    // Should redirect to home page
    await expect(page).toHaveURL('/');
    await expect(page.locator('h1')).toContainText('YouTube Watcher');
  });

  test('should show error with wrong password', async ({ page }) => {
    await page.goto('/login');
    
    // Fill in wrong password
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');
    
    // Should show error message
    await expect(page.locator('.error')).toBeVisible();
    await expect(page.locator('.error')).toContainText('登录失败');
  });
});
