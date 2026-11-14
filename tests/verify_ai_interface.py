"""Browser Gemini workflow with intercepted API responses; no model calls or writes."""
from copy import deepcopy
from playwright.sync_api import sync_playwright

QUERY='childhood cancer early diagnosis methods'
packet={'response':{'id':101,'run_id':201,'query_id':301,'query_text':QUERY,'provider':'gemini','model_name':'fixture-model',
        'response_text':'## Findings\n\n**Fixture only.** [Source](https://example.org/research)\n\n<script>bad()</script> [Unverified](https://unverified.invalid)',
        'created_at':'2026-11-13T12:00:00','prompt_version':'research-v1'},
        'sources':[{'chunk_index':0,'title':'Fixture grounded source','url':'https://example.org/research'}], 'summary':None}
summary={**packet,'summary':{'id':401,'summary_text':'## Conclusion\n\nFixture saved summary.','summarizer':'fixture-model','created_at':'2026-11-13T12:00:00'}}
with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    research=[];summaries=[];generated=[]
    def mock(route):
        url=route.request.url
        if url.endswith('/search'):
            body=route.request.post_data_json;research.append(body)
            if not body['allow_paid'] and not generated:
                route.fulfill(status=409,json={'detail':{'requires_confirmation':True,'message':'Authorize one fixture research request?'}});return
            generated.append(True);route.fulfill(json=packet);return
        if url.endswith('/summarize'):
            body=route.request.post_data_json;summaries.append(body)
            if len(summaries)==1:
                route.fulfill(status=409,json={'detail':{'requires_confirmation':True,'message':'Authorize one fixture summary request?'}});return
            route.fulfill(json=summary);return
        route.fulfill(json=summary)
    page.route('**/api/ai/**',mock)
    # A faulty Web submission during the AI test must never reach the local ETL.
    page.route('**/api/search',lambda route:route.abort())
    page.on('dialog',lambda dialog:dialog.accept())
    page.goto('http://127.0.0.1:8765/search')
    page.locator('#ai-mode').click()
    assert page.locator('#ai-engine').input_value()=='gemini'
    page.locator('#query').fill(QUERY)
    page.locator('#ai-search-button').click()
    page.wait_for_selector('#ai-response strong')
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert len(research)==2 and sum(item['allow_paid'] for item in research)==1
    assert page.locator('#query').input_value()==QUERY
    assert page.locator('#ai-response script').count()==0
    assert page.locator('#ai-response a').count()==1
    assert page.locator('#ai-sources a').first.get_attribute('href')=='https://example.org/research'
    assert page.locator('#summarize-ai').is_visible()
    page.locator('#summarize-ai').click()
    page.wait_for_selector('#ai-downloads a')
    page.wait_for_function("document.querySelector('#loading').hidden")
    assert len(summaries)==2 and len(research)==2
    assert 'Fixture saved summary.' in page.locator('#ai-summary').inner_text()
    assert 'format=markdown' in page.locator('#ai-downloads a').first.get_attribute('href')
    assert 'format=pdf' in page.locator('#ai-downloads a').last.get_attribute('href')
    page.screenshot(path='artifacts/milestone09_ai_desktop.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path='artifacts/milestone09_ai_mobile.png',full_page=True)
    page.locator('#toggle-history').click();page.locator('#new-search').click();page.locator('#ai-mode').click()
    assert not page.locator('#ai-response').inner_text()
    assert not page.locator('#summarize-ai').is_visible()
    assert not errors,errors
    browser.close()
print('AI browser: explicit confirmation, research, safe Markdown, sources, summary, export links, mobile and new-search reset passed. All AI calls mocked.')
