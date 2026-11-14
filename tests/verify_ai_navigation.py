"""Gemini provider, research and summary controls must never navigate to Library."""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page()
    pending=[]
    def intercept(route):
        if route.request.method=='POST':pending.append(route)
        else:route.continue_()
    page.route('**/api/**',intercept)
    page.goto('http://127.0.0.1:8765/search')
    page.locator('#ai-mode').click();page.locator('#ai-engine').dispatch_event('click')
    assert page.locator('#library').is_hidden(), 'Gemini provider control opened Library'
    page.locator('#ai-search-button').click()
    page.wait_for_function("!document.querySelector('#loading').hidden")
    assert page.locator('#library').is_hidden(), 'Research start opened Library'
    page.wait_for_timeout(100);assert pending
    packet={'response':{'id':1,'run_id':1,'provider':'gemini','query_text':'childhood cancer early diagnosis methods','response_text':'Fixture only'},'sources':[],'summary':None}
    pending.pop().fulfill(json=packet)
    page.wait_for_function("document.querySelector('#loading').hidden")
    page.locator('#summarize-ai').click()
    page.wait_for_function("!document.querySelector('#loading').hidden")
    assert page.locator('#library').is_hidden(), 'Summary start opened Library'
    page.wait_for_timeout(100);assert pending
    pending.pop().fulfill(json=packet)
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert page.locator('#library').is_hidden()
    browser.close()
print('Gemini navigation: provider, pending research and pending summary stay on the search page.')
