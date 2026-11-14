"""Full saved Web-result Library and local TF-IDF cosine keyword retrieval."""
from collections import Counter
from math import log, sqrt
import re
from fastapi import APIRouter, HTTPException, Query
from mysql.connector import Error
import db
from gemini_provider import grounded_excerpt

router=APIRouter()
STOP={'the','a','an','of','and','or','to','in','for','with','on','at','is','are','find','show','me','about','please'}


def tokens(text: str) -> Counter:
    return Counter(word for word in re.findall(r'[^\W_]+',text.lower()) if word not in STOP and len(word)>1)


def rank_sources(rows: list[dict], query: str) -> list[dict]:
    """Local lexical similarity, no embeddings, API calls or claims of semantic AI."""
    documents=[tokens((row.get('title') or '')+' '+(row.get('snippet') or '')) for row in rows]
    request=tokens(query)
    frequencies=Counter(word for document in documents for word in document)
    weights={word:log((1+len(rows))/(1+count))+1 for word,count in frequencies.items()}
    def vector(counts):return {word:(1+log(count))*weights.get(word,log(1+len(rows))+1) for word,count in counts.items()}
    q=vector(request);qn=sqrt(sum(value*value for value in q.values()))
    ranked=[]
    for row,counts in zip(rows,documents):
        values=vector(counts);norm=sqrt(sum(value*value for value in values.values()))
        score=sum(value*values.get(word,0) for word,value in q.items())/(norm*qn) if norm and qn else 0
        if score>0:ranked.append({**row,'similarity':round(score,6)})
    return sorted(ranked,key=lambda row:(-row['similarity'],-row['id']))


def read_sources(query: str, page: int, page_size: int, search_type: str | None = None) -> dict:
    with db.get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute('''SELECT s.id,s.run_id,s.title,s.snippet,s.original_url,s.normalized_url,
                s.result_rank,s.is_duplicate,s.is_ad,s.created_at,r.engine,q.query_text,
                EXISTS(SELECT 1 FROM search_results older WHERE older.source_id=s.source_id
                    AND older.run_id<>s.run_id AND older.id<s.id) AS previously_seen
                FROM search_results s JOIN search_runs r ON r.id=s.run_id
                JOIN search_queries q ON q.id=r.query_id ORDER BY s.created_at DESC,s.id DESC''')
            rows=cursor.fetchall()
            if search_type != 'web':
                cursor.execute("""SELECT g.id,a.id AS ai_response_id,a.run_id,g.title,g.chunk_index,a.grounding_metadata,'' AS snippet,
                    g.url AS original_url,g.url AS normalized_url,0 AS is_duplicate,0 AS is_ad,
                    a.created_at,'gemini' AS engine,q.query_text,0 AS previously_seen
                    FROM ai_sources g JOIN ai_responses a ON a.id=g.response_id
                    JOIN search_queries q ON q.id=a.query_id""")
                ai_rows=cursor.fetchall()
                for row in ai_rows:
                    row['snippet']=grounded_excerpt(row.pop('grounding_metadata') or {},row.pop('chunk_index'))
                rows.extend(ai_rows)
    rows.sort(key=lambda row:(str(row.get('created_at','')),row['id'],bool(row.get('ai_response_id'))),reverse=True)
    stored_count=len(rows)
    if query.strip():rows=rank_sources(rows,query)
    start=(page-1)*page_size
    return {'items':rows[start:start+page_size],'page':page,'has_more':start+page_size<len(rows),
            'total':len(rows),'stored_count':stored_count}


@router.get('/api/library/sources')
def sources(q: str = Query('',max_length=1000),page: int = Query(1,ge=1,le=100000),page_size: int = Query(25,ge=1,le=100),search_type: str | None = Query(None,pattern='^web$')):
    try:return read_sources(q,page,page_size,search_type)
    except (Error,ValueError):raise HTTPException(503,'Source Library unavailable; check MySQL configuration') from None
