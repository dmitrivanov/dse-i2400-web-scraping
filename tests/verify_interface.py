"""Browser checks against a running local app; all search POSTs are mocked.

Run: PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/playwright-browsers" .venv/bin/python tests/verify_interface.py
Only GET requests read real saved MySQL data. No capture or provider request occurs.
"""
import json
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    posts = []
    def reject_post(route):
        posts.append(route.request.url)
        route.fulfill(status=500, json={'detail': 'Unexpected POST in saved-data verification'})
    page.route('**/api/**', lambda route: reject_post(route) if route.request.method == 'POST' else route.continue_())
    page.goto(BASE + '/search')
    page.wait_for_selector('.history-item', state='attached')
    assert not page.locator('#internet-results').is_visible()
    page.locator('#ai-mode').click()
    assert page.locator('#ai-results').is_visible()
    page.locator('#query').press('Control+Enter')
    assert not posts
    page.locator('#internet-mode').click()
    page.locator('#toggle-history').click()
    page.locator('.history-item[data-id="12"]').click()
    page.wait_for_selector('.result')
    assert page.locator('.result').count() == 9
    assert page.locator('#query').input_value() == 'childhood cancer early diagnosis methods'
    assert not posts
    page.screenshot(path='artifacts/milestone07_desktop.png', full_page=True)
    page.locator('#toggle-history').click()
    page.locator('.history-item[data-id="3"]').click()
    page.locator('.details summary').click()
    page.wait_for_selector('#artifact-links a')
    links = page.locator('#artifact-links a').evaluate_all('(links) => links.map(a => a.href)')
    assert len(links) == 2
    for url in links:
        assert page.request.get(url).status == 200
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#toggle-history').click()
    assert page.locator('#sidebar-backdrop').is_visible()
    page.keyboard.press('Escape')
    assert not page.locator('#sidebar').is_visible()
    page.screenshot(path='artifacts/milestone07_mobile.png', full_page=True)
    packet = page.request.get(BASE + '/api/runs/12').json()
    page.unroute('**/api/**')
    bodies = []
    def mocked_search(route):
        bodies.append(route.request.post_data_json)
        route.fulfill(json=packet)
    page.route('**/api/search', mocked_search)
    exact = '  childhood cancer early diagnosis methods  '
    page.locator('#query').fill(exact)
    page.locator('#mode').select_option('collect')
    assert page.locator('#max-pages').is_enabled()
    page.locator('#max-pages').fill('6')
    page.locator('#search-button').click()
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert bodies[-1]['query'] == exact
    assert bodies[-1]['mode'] == 'collect' and bodies[-1]['max_pages'] == 6
    assert bodies[-1]['allow_paid'] is False
    page.unroute('**/api/search')
    page.route('**/api/search', lambda route: route.fulfill(status=422, json={'detail': [{'msg':'Use at least five meaningful words'}]}))
    page.locator('#query').fill('short')
    page.locator('#search-button').click()
    page.wait_for_function("document.querySelector('#message').textContent.includes('five meaningful')")
    page.unroute('**/api/search')
    pending = []
    page.route('**/api/search', lambda route: pending.append(route))
    page.locator('#query').fill(exact)
    page.locator('#search-button').click()
    assert page.locator('#loading').is_visible()
    assert page.locator('#search-button').is_disabled()
    page.wait_for_function("document.querySelector('#loading').hidden === false")
    page.wait_for_timeout(100)
    assert pending
    packet['results'] = [{**packet['results'][0], 'title': f'Fixture result {i}', 'normalized_url': f'https://example.org/{i}', 'destination_unverified': False} for i in range(50)]
    packet['run']['final_count'] = 50
    pending.pop().fulfill(json=packet)
    page.wait_for_function("document.querySelectorAll('.result').length === 50")
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert not page.locator('#loading').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    browser.close()
print('Browser checks passed: real saved run 12, history, artifacts, mobile; mocked search and errors. No paid calls.')
