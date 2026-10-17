/* Run only against an isolated local fixture: NODE_PATH=<playwright packages> node tests/android-web-smoke.cjs */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');

(async () => {
  const origin = process.env.TQT_TEST_ORIGIN || 'https://127.0.0.1:18143';
  assert.match(origin, /^https:\/\/(127\.0\.0\.1|localhost):\d+$/);
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const result = { fixture: true, nativeBluetooth: 'not tested', checks: [] };
  try {
    await page.goto(origin + '/android');
    await page.waitForURL(/\/login/);
    result.checks.push('unauthenticated page redirects to login');
    const login = await context.request.post(origin + '/api/auth/login', { data: { email: 'android.qa@example.invalid', password: 'Prueba-OTA-2026!' } });
    assert.equal(login.status(), 200);
    await page.goto(origin + '/android');
    await page.getByText('Publicación pendiente', { exact: true }).waitFor();
    assert.equal(await page.locator('#apk-download').isVisible(), false);
    result.checks.push('real authenticated API returns pending approval; no download');
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: `privado/android-testing/web-${viewport.width}.png`, fullPage: true });
      result.checks.push(`responsive ${viewport.width}px without horizontal overflow`);
    }
    // UI fixture only. Does not manufacture a server approval or signed distribution.
    await page.route('**/api/android/apk/manifest', route => route.fulfill({ json: {
      available: true, version_name: '0.1.0-fixture', version_code: 1, min_sdk: 26,
      bytes: 1024, sha256: 'a'.repeat(64), download_url: '/api/android/apk/download'
    } }));
    await page.reload();
    await page.getByText('Versión aprobada', { exact: true }).waitFor();
    assert.equal(await page.locator('#apk-sha').inputValue(), 'a'.repeat(64));
    await page.locator('#apk-copy').click();
    assert.match(await page.locator('#apk-copy').textContent(), /Huella copiada|Selecciona y copia/);
    result.checks.push('approved-response UI fixture displays integrity and copy interaction');
    assert.deepEqual(errors, []);
    result.checks.push('no JavaScript page errors');
    await fs.writeFile('privado/android-testing/web-result.json', JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally { await context.close(); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
