"""[전처리 3단계 · 보고서 6장] 확정된 articles의 매칭 문장만 0/1/2로 판정해 decisions에 저장한다.

Stage 5: classify only stored matching sentences belonging to finalized articles.
"""
import json
from .common import require,done,mark,meta,check_sources,atomic_json,sha256
def run(c,cfg):
    require(c,2)
    if done(c,3):return meta(c,'prep3')
    if sha256(cfg.deliverables/'articles.csv')!=meta(c,'prep2')['file']['sha256']:
        raise RuntimeError('Finalized articles.csv changed after preprocessing stage 2')
    check_sources(c,cfg,['sipri_dictionary.csv','nato_dictionary.csv','usage_patterns.csv'])
    from .term_matcher import TermMatcher
    from .usage_rules import UsageClassifier,RULES_VERSION
    classifier=UsageClassifier(TermMatcher(cfg.sources_dir),cfg.sources_dir)
    rows=c.execute("""SELECT match_id,sentence,matched_name,category_id,start_pos,end_pos FROM matches m
        WHERE EXISTS(SELECT 1 FROM selected_articles a WHERE a.url=m.url)
        AND NOT EXISTS(SELECT 1 FROM decisions d WHERE d.match_id=m.match_id)
        ORDER BY match_id""")
    n=0
    for mid,*row in rows:
        code,reason,patterns=classifier.decide(row)
        c.execute('INSERT INTO decisions VALUES(?,?,?,?)',(mid,code,reason,json.dumps(patterns)));n+=1
        if n%1000==0:c.commit()
    counts=dict(c.execute("SELECT COALESCE(CAST(usage_code AS TEXT),'unclassified'),COUNT(*) FROM decisions GROUP BY usage_code"))
    report=dict(rules_version=RULES_VERSION,decisions=counts,code_meanings={'0':'사용','1':'비사용','2':'불확실'},code_priority=[0,1,2],read_source='matches table only; no URL fetch or body reread')
    mark(c,3,report);atomic_json(cfg.work_dir/'prep3_manifest.json',report);return report
