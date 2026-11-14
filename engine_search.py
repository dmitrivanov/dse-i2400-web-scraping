"""Bing/Yahoo/DuckDuckGo through ScraperAPI URL retrieval, never Google substitution."""
from urllib.parse import urlencode, urlsplit, parse_qs, urljoin
from bs4 import BeautifulSoup
import requests
from config import get_scraper_config
from google_search import SearchError

ENDPOINTS = {'bing':'https://www.bing.com/search', 'yahoo':'https://search.yahoo.com/search',
             'duckduckgo':'https://html.duckduckgo.com/html/'}


def search_url(engine: str, query: str, start: int = 0) -> str:
    if engine not in ENDPOINTS:
        raise ValueError('Unsupported URL search engine')
    params = {'p':query,'b':start or 1} if engine=='yahoo' else ({'q':query,'s':start} if engine=='duckduckgo' else {'q':query,'first':start or 1})
    return ENDPOINTS[engine]+'?'+urlencode(params)


def fetch_html(engine: str, query: str, start: int = 0) -> str:
    settings=get_scraper_config()
    try:
        response=requests.get(settings['base_url'].rstrip('/')+'/',
            params={'api_key':settings['api_key'],'url':search_url(engine,query,start)},
            timeout=(10,90),allow_redirects=False)
    except requests.RequestException:
        raise SearchError(f'{engine.title()} retrieval failed or timed out; no retry made') from None
    if response.status_code!=200:
        raise SearchError(f'{engine.title()} returned HTTP {response.status_code}; no substitution made')
    return response.text


def parse_page(engine: str, html: str, query: str, start: int = 0) -> tuple[list[dict], int | None]:
    soup=BeautifulSoup(html,'html.parser')
    if soup.select_one('#b_captcha, #captcha, .anomaly-modal, .g-recaptcha, form[action*="challenge"]'):
        raise SearchError(f'{engine.title()} returned a verification challenge; stopped')
    selectors={'bing':('#b_results li.b_algo','h2 a[href]','.b_caption p'),
               'yahoo':('#web .algo','.compTitle a[href]:has(h3)','div.compText p'),
               'duckduckgo':('.result.results_links:not(.result--ad)','a.result__a[href]','.result__snippet')}
    cards,link_selector,snippet_selector=selectors[engine]
    rows=[]
    for card in soup.select(cards):
        link=card.select_one(link_selector)
        if not link:continue
        heading=link.select_one('h3') if engine=='yahoo' else link
        snippet=card.select_one(snippet_selector)
        rows.append({'title':(heading or link).get_text(' ',strip=True),
            'original_url':urljoin(ENDPOINTS[engine],link['href']),
            'snippet':snippet.get_text(' ',strip=True) if snippet else None,
            'result_rank':(start if engine=='duckduckgo' else max(0,start-1))+len(rows)+1,'is_ad':False})
    if not rows:
        if soup.select_one('.no-results, .no-results__message'):
            return [],None
        raise SearchError(f'{engine.title()} returned no supported organic cards; stopped')
    next_start=None
    if engine=='duckduckgo':
        for form in soup.select('form'):
            q=form.select_one('input[name="q"]');offset=form.select_one('input[name="s"]')
            if q and q.get('value')==query and offset:
                try:
                    candidate=int(offset.get('value',''))
                    if start<candidate<=500:next_start=candidate
                except ValueError:pass
    else:
        candidates=soup.select('a.sb_pagN[href]') if engine=='bing' else [a for a in soup.select('a[href]') if a.get_text(' ',strip=True)=='Next']
        for link in candidates:
            parts=urlsplit(urljoin(ENDPOINTS[engine],link['href']));params=parse_qs(parts.query)
            field,query_field=('b','p') if engine=='yahoo' else ('first','q')
            try:
                candidate=int(params.get(field,[''])[0])
                if (parts.scheme=='https' and parts.hostname==urlsplit(ENDPOINTS[engine]).hostname
                    and parts.path.split(';')[0]=='/search' and params.get(query_field)==[query]
                    and start<candidate<=500):next_start=candidate
            except ValueError:pass
    return rows,next_start


def fetch_page(engine: str, query: str, start: int = 0) -> tuple[list[dict], int | None]:
    return parse_page(engine,fetch_html(engine,query,start),query,start)
