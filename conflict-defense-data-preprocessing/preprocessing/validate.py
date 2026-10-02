"""[검증 · 보고서 8.2] 원본·DB·CSV 대조, 코드 값(0/1/2), 우선순위, 사전에 없는 카테고리, 기사 연결을 검사한다.

Source/DB/CSV readback, subset linkage, priority and no-usage article-stage checks.
"""
import csv,json
from .common import ARTICLE_COLUMNS,RESULT_COLUMNS,meta,sha256,file_info,check_sources
def same_csv(path,header,rows,check_row=None):
    count=0
    with path.open(encoding='utf-8-sig',newline='') as f:
        rd=csv.reader(f)
        if next(rd)!=header:raise ValueError('CSV header mismatch: '+str(path))
        for expected in rows:
            actual=next(rd,None)
            wanted=['' if x is None else str(x) for x in expected]
            if actual!=wanted:raise ValueError('CSV/DB mismatch at '+str(count+1)+': '+str(path))
            if check_row:check_row(actual)
            count+=1
        if next(rd,None) is not None:raise ValueError('Extra CSV row: '+str(path))
    return count
def validate(c,cfg):
    check_sources(c,cfg,['sipri_dictionary.csv','nato_dictionary.csv','usage_patterns.csv'])
    if sha256(cfg.input_csv)!=meta(c,'collect1')['input_sha256']:raise ValueError('Original input CSV changed')
    original=same_csv(cfg.input_csv,ARTICLE_COLUMNS,c.execute('SELECT article_id,conflict_id,published_date,url,title FROM input_rows ORDER BY row_no'))
    def complete(row):
        if not all(x.strip() for x in row):raise ValueError('Missing article field')
    article_path=cfg.deliverables/'articles.csv'
    articles=same_csv(article_path,ARTICLE_COLUMNS,c.execute('SELECT article_id,conflict_id,published_date,url,title FROM selected_articles ORDER BY row_no'),complete)
    selected=set(r[0] for r in c.execute('SELECT article_id FROM selected_articles'));keys=set()
    def result_row(row):
        if row[0] not in selected:raise ValueError('Result outside finalized articles')
        if row[2] not in ('0','1','2'):raise ValueError('Invalid usage code')
        key=tuple(row[:2])
        if key in keys:raise ValueError('Duplicate result key')
        keys.add(key)
    result_path=cfg.deliverables/'result.csv'
    results=same_csv(result_path,RESULT_COLUMNS,c.execute('SELECT r.* FROM selected_articles a JOIN result_rows r ON a.article_id=r.article_id ORDER BY a.row_no,r.category_id'),result_row)
    # 보고서 8.2: result의 카테고리가 두 사전(무기·기술)에 없는 코드면 오류로 본다.
    known=set()
    for name in ('sipri_dictionary.csv','nato_dictionary.csv'):
        with (cfg.sources_dir/name).open(encoding='utf-8-sig',newline='') as f:known.update(r['category_id'] for r in csv.DictReader(f))
    unknown=sorted(set(r[0] for r in c.execute('SELECT DISTINCT category_id FROM result_rows'))-known)
    if unknown:raise ValueError('Unknown result categories: '+','.join(unknown))
    from .export import grouped
    for aid,url in c.execute('SELECT article_id,url FROM selected_articles ORDER BY row_no'):
        actual=c.execute('SELECT category_id,usage_code,evidence_sentence FROM result_rows WHERE article_id=? ORDER BY category_id',(aid,)).fetchall()
        if actual!=grouped(c,url):raise ValueError('Category priority/evidence mismatch: '+aid)
    if c.execute("""SELECT 1 FROM matches m WHERE EXISTS(SELECT 1 FROM selected_articles a WHERE a.url=m.url)
        AND NOT EXISTS(SELECT 1 FROM decisions d WHERE d.match_id=m.match_id) LIMIT 1""").fetchone():raise ValueError('Missing sentence classification')
    source_values=c.execute("""SELECT 1 FROM selected_articles a JOIN input_rows i USING(row_no)
      WHERE a.article_id<>i.article_id OR a.conflict_id<>i.conflict_id OR a.published_date<>i.published_date OR a.url<>i.url LIMIT 1""").fetchone()
    if source_values:raise ValueError('Changed original field other than title')
    return dict(validation='passed',original_rows=original,articles_rows=articles,result_rows=results,
      statuses=dict(c.execute('SELECT status,COUNT(*) FROM pages GROUP BY status')),
      code_meanings={'0':'사용','1':'비사용','2':'불확실'},code_priority=[0,1,2],
      files={'articles.csv':file_info(article_path,articles),'result.csv':file_info(result_path,results)},
      article_exclusions=meta(c,'prep2'),validation_errors=[])
