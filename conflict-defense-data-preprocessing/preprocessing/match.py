"""[전처리 1단계 · 보고서 3장] 수집·저장 저장소가 만든 작업 DB의 본문에서 사전 이름이 걸린 문장을 matches 테이블에 저장한다 (사용 판정 없음).

Stage 3: all dictionary matches and their sentences; no usage fields exist here.
"""
import zlib
from .common import require_collection,done,mark,register_sources,ensure_schema,atomic_json,meta
def run(c,cfg,allow_pending=False):
    require_collection(c)
    if done(c,1):return meta(c,'prep1')
    pending=c.execute("SELECT COUNT(*) FROM pages WHERE status='pending'").fetchone()[0]
    if pending and not allow_pending:raise RuntimeError('Pending URLs remain; explicitly use --allow-pending for a fixed current-data snapshot')
    # 사전 3종은 여기서 처음 검사·기록한다. 이후 단계는 사전이 바뀌면 멈춘다. 사용 표현 사전은 기록만 하고 읽지는 않는다.
    register_sources(c,cfg);ensure_schema(c)
    from .term_matcher import TermMatcher
    matcher=TermMatcher(cfg.sources_dir)
    for url,title,body in c.execute("SELECT url,title,body FROM pages WHERE status='extracted' AND url NOT IN (SELECT url FROM matched_pages) ORDER BY rowid"):
        if not body:raise ValueError('Extracted page missing body: '+url)
        text=zlib.decompress(body).decode('utf-8')
        c.executemany('INSERT INTO matches(url,sentence_no,section,category_id,matched_name,sentence,start_pos,end_pos) VALUES(?,?,?,?,?,?,?,?)',
            ((url,*row) for row in matcher.scan(title,text)))
        c.execute('INSERT INTO matched_pages VALUES(?)',(url,));c.commit()
    report=dict(matched_pages=c.execute('SELECT COUNT(*) FROM matched_pages').fetchone()[0],literal_matches=c.execute('SELECT COUNT(*) FROM matches').fetchone()[0],pages_with_matches=c.execute('SELECT COUNT(DISTINCT url) FROM matches').fetchone()[0],pending_excluded=pending,usage_classification_performed=False)
    mark(c,1,report);atomic_json(cfg.work_dir/'prep1_manifest.json',report);return report
