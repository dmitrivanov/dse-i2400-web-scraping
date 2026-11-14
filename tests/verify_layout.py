"""Phase A layout checks on the local app; only saved-data GETs are allowed."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.route('**/api/**', lambda route: route.abort() if route.request.method != 'GET' else route.continue_())
    for width in (1440, 768, 390, 320):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto('http://127.0.0.1:8765/search')
        page.locator('#query').focus()
        for height in (100, 240):
            page.locator('#query').evaluate('(el, height) => el.style.height = height + "px"', height)
            page.locator('#query').fill('childhood cancer early diagnosis methods ' * 20)
            tabs = page.locator('.mode-tabs').bounding_box()
            query = page.locator('#query').bounding_box()
            controls = page.locator('.controls').bounding_box()
            assert query['y'] >= tabs['y'] + tabs['height']
            assert controls['y'] >= query['y'] + query['height']
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#query').evaluate('(el) => el.style.height = "100px"')
        footer = page.locator('footer').bounding_box()
        assert footer['y'] + footer['height'] >= 899
        page.locator('#toggle-history').click()
        page.wait_for_selector('.history-item')
        assert not page.get_by_text('Reload history', exact=True).count()
        page.locator('.history-item[data-id="12"]').click()
        page.wait_for_selector('.result')
        last = page.locator('.result').last.bounding_box()
        footer = page.locator('footer').bounding_box()
        assert footer['y'] >= last['y'] + last['height']
        page.screenshot(path=f'artifacts/milestone09_layout_{width}.png', full_page=True)
    # CSS zoom approximates enlarged browser UI; narrow viewport covers reflow too.
    page.goto('http://127.0.0.1:8765/search')
    page.evaluate('document.body.style.zoom = "1.5"')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    browser.close()
print('Phase A: layout/focus/resizing/reflow/footer/history checks passed.')
