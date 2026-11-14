"""Current Web/Library browser checks: saved data + intercepted submissions only."""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/api/**',lambda route:route.abort() if route.request.method=='POST' else route.continue_())
    page.goto('http://127.0.0.1:8765/search')
    assert page.locator('.engine-choice').count()==4
    assert page.locator('#collect50, #refresh-search, #collect-more').count()==0
    page.locator('#toggle-history').click();page.wait_for_selector('.history-item')
    page.locator('.history-item[data-id="12"]').click();page.wait_for_selector('.result')
    assert page.locator('.result').count()==9
    assert page.locator('.engine-badge').first.inner_text()=='Google'
    page.locator('#open-library').click();page.wait_for_selector('.source-table tbody tr')
    total=page.request.get('http://127.0.0.1:8765/api/library/sources').json()['total']
    assert total>170 and str(total) in page.locator('#library-status').inner_text()
    assert page.locator('.source-table tbody tr').count()==25
    page.locator('#library-next').click();page.wait_for_function("document.querySelector('#library-page').textContent==='Page 2'")
    page.locator('#library-query').fill('early cancer diagnosis methods');page.locator('#library-search-form button').click()
    page.wait_for_function("document.querySelector('#library-page').textContent==='Page 1'")
    assert page.locator('.source-table tbody tr').count()>0
    page.screenshot(path='artifacts/source_library_desktop.png',full_page=True)
    page.locator('#close-library').click()
    packet=page.request.get('http://127.0.0.1:8765/api/runs/18').json()
    page.unroute('**/api/**');bodies=[]
    def mocked(route):bodies.append(route.request.post_data_json);route.fulfill(json=packet)
    page.route('**/api/search',mocked)
    page.locator('.engine-choice[data-engine="bing"]').click()
    page.locator('#max-pages').select_option('1');page.locator('#search-button').click()
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert bodies[-1]['engine']=='bing' and bodies[-1]['allow_paid'] is False
    assert page.locator('.database-badge').count()>0
    assert page.locator('.engine-badge').first.inner_text()=='Bing'
    for width in [768,390]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path='artifacts/source_results_mobile.png',full_page=True)
    page.locator('#open-library').click();page.wait_for_selector('.source-table')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    browser.close()
print('Web/Library: engine buttons, saved results, database labels, full table, cosine search, pagination and mobile verified. Search submission mocked.')
