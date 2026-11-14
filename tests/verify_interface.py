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
    page.screenshot(path='artifacts/milestone08_desktop.png', full_page=True)
    page.locator('#toggle-history').click()
    page.locator('.history-item[data-id="3"]').click()
    page.locator('#internet-results .details summary').click()
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
    page.screenshot(path='artifacts/milestone08_mobile.png', full_page=True)
    packet = page.request.get(BASE + '/api/runs/12').json()
    page.unroute('**/api/**')
    bodies = []
    def mocked_search(route):
        bodies.append(route.request.post_data_json)
        route.fulfill(json=packet)
    page.route('**/api/search', mocked_search)
    exact = '  childhood cancer early diagnosis methods  '
    page.locator('#query').fill(exact)
    assert page.locator('#engine').input_value() == 'google'
    assert page.locator('#max-pages').is_enabled()
    page.locator('#max-pages').select_option('5')
    page.locator('#search-button').click()
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert bodies[-1]['query'] == exact
    assert bodies[-1]['mode'] == 'search' and bodies[-1]['max_pages'] == 5
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
    packet['results'] = [{**packet['results'][0], 'title': f'Fixture result {i}', 'original_url': f'https://example.org/{i}', 'normalized_url': f'https://example.org/{i}', 'destination_unverified': False} for i in range(50)]
    packet['run']['final_count'] = 50
    pending.pop().fulfill(json=packet)
    page.wait_for_function("document.querySelectorAll('.result').length === 50")
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert not page.locator('#loading').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#open-library').click()
    page.wait_for_selector('.library-item')
    assert page.locator('#library').is_visible()
    page.locator('#library-filter').select_option('ai')
    page.wait_for_function("document.querySelector('#library-status').textContent === 'No saved items.'")
    page.locator('#library-filter').select_option('web')
    page.wait_for_selector('.library-item')
    assert page.locator('.library-item').count() == 15
    page.locator('.library-item').first.click()
    page.wait_for_function("document.querySelector('#library').hidden")
    assert page.locator('.result').count() == 54
    assert 'goto?' not in page.locator('#results').inner_text()
    assert page.locator('#results a').first.get_attribute('href').startswith('https://')
    # Mock historical AI output and Library pagination, without inserting research data.
    def mock_library(route):
        second = 'page=2' in route.request.url
        item = {'kind': 'response', 'id': 99, 'query_text': 'Fixture saved AI query', 'search_type': 'ai', 'provider': 'gemini', 'created_at': '2026-11-13T12:00:00', 'result_count': 1, 'summary_available': False}
        route.fulfill(json={'items': [item], 'page': 2 if second else 1, 'has_more': not second})
    page.route('**/api/library?*', mock_library)
    page.route('**/api/library/response/99', lambda route: route.fulfill(json={'responses': [{'provider': 'gemini', 'model_name': 'actual-fixture-model', 'response_text': '<script>Fixture only</script>'}], 'summaries': [{'summary_text': 'Fixture summary only'}]}))
    page.locator('#open-library').click()
    page.wait_for_selector('.library-item')
    page.locator('#library-next').click()
    page.wait_for_function("document.querySelector('#library-page').textContent === 'Page 2'")
    assert page.locator('#library-next').is_disabled()
    page.locator('.library-item').click()
    page.wait_for_selector('#saved-ai details')
    page.locator('#saved-ai summary').click()
    assert 'actual-fixture-model' in page.locator('#saved-ai').inner_text()
    assert '<script>Fixture only</script>' in page.locator('#saved-ai').inner_text()
    assert page.locator('#saved-ai script').count() == 0
    assert 'Fixture summary only' in page.locator('#saved-ai').inner_text()
    assert page.locator('#results img').count() == 0  # no fabricated website previews
    page.locator('#close-library').click()
    page.locator('#max-pages').select_option('1')
    page.unroute('**/api/search')
    confirmations = []
    page.route('**/api/search', lambda route: (confirmations.append(route.request.post_data_json), route.fulfill(status=409, json={'detail': {'requires_confirmation': True, 'message': 'Authorize one paid request?'}})))
    page.on('dialog', lambda dialog: dialog.dismiss())
    page.locator('#search-button').click()
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert len(confirmations) == 1
    assert confirmations[0]['allow_paid'] is False
    assert confirmations[0]['mode'] == 'search' and confirmations[0]['max_pages'] == 1
    assert 'No paid requests were authorized' in page.locator('#message').inner_text()
    assert not errors, errors
    browser.close()
print('Browser checks passed: saved run 12, evidence, mobile, Library/filter/pagination, mocked 50-card search and AI outputs, declined credit confirmation. No paid calls.')
