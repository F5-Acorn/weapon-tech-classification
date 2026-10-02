"""[전처리 3단계 · 보고서 4~6장] 무기 언급 타당성(plausible_reference), 사용 표현 탐지(find_patterns), 문장 판정(classify).

판정 코드: 0=사용, 1=비사용, 2=불확실 (보고서 6장). 규칙은 matching.py VERSION 20260923.4와 같다.
Actual conservative sentence rules, run only after articles are finalized.
"""
import csv,re
import ahocorasick
from .term_matcher import norm, bounded
from .codes import USED,NOT_USED,UNCERTAIN,preferred

# 판정 규칙 버전. 실제 판정에 쓴 matching.py의 VERSION과 같다. 규칙을 고치면 올리고 새 work_dir에서 다시 실행한다.
RULES_VERSION='20260923.4'

NONUSE={'can be used','will be used','is planning to build','is preparing to use','can carry','(military) exercise / drill','procurement','acquisition (of materiel)','distribution (of materiel/supplies)','maintenance','delivered (military aid)','would be delivered','should be used','plans to use','pledged to use','was not launched','did not fire','did not engage','test launch','war reserves / stockpiled'}
UNCERTAIN_PATTERNS={'no','suggests','claimed','says','has denied supplying','crashed','failed to intercept','engage (fire control order)'}
def expand(form):
 # Parentheses are explanatory dictionary annotations, not required article text.
 value=re.sub(r'\([^)]*\)','',form).strip()
 return [norm(x) for x in re.split(r'\s+/\s+',value) if x.strip()]
def load_patterns(sources):
 global P,PATTERN_RULES
 PATTERN_RULES=[]
 with (sources/'usage_patterns.csv').open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   base=r['base_form'];code=NOT_USED if base in NONUSE else UNCERTAIN if base in UNCERTAIN_PATTERNS else USED
   for col in ['base_form','trans_form']:
    if not r[col]:continue
    for phrase in set([norm(r[col])]+expand(r[col])):
     override=UNCERTAIN if re.search(r'\b(may|might|possible|possibly|likely|claimed|denied)\b',phrase) else code
     PATTERN_RULES.append((phrase,r['pattern_id'],col,override,r[col]))
 P=ahocorasick.Automaton();pmap={}
 for rule in PATTERN_RULES:pmap.setdefault(rule[0],[]).append(rule)
 for phrase,rules in pmap.items():P.add_word(phrase,(phrase,rules))
 P.make_automaton()
def find_patterns(text):
 text=norm(text);out=[]
 for end,(phrase,rules) in P.iter(text):
  start=end-len(phrase)+1
  if bounded(text,start,end+1):out.extend({'pattern_id':r[1],'column':r[2],'code':r[3],'form':r[4],'matched':phrase,'start':start,'end':end+1} for r in rules)
 return out
CONTEXT=re.compile(r'\b(?:weapons?|missiles?|aircraft|helicopters?|radars?|ships?|vessels?|submarines?|tanks?|drones?|uavs?|guns?|rockets?|torpedoes?|fighters?|systems?|military|forces|army|navy|soldiers?|troops|artillery|munitions?|cyber|electronic|technology|technologies|combat|battle|warfare)\b')
NONUSE_CONTEXT=re.compile(r'\b(?:exercises?|drills?|tests?|testing|test-fired|training|demonstration|simulation|procurement|maintenance)\b')
NEGATION=re.compile(r"\b(?:not|never|no longer|didn't|doesn't|hasn't|haven't|wasn't|weren't|isn't|aren't|cannot|can't)\b")
UNCERTAINTY=re.compile(r'\b(?:may|might|could|possibly|possible|alleged|allegedly|unconfirmed|unclear|reportedly|claimed|claims|suggests|suggested|likely)\b')
FUTURE=re.compile(r'\b(?:will|would|should|must|can|plans? to|planning to|planned to|intends? to|intended to|designed to|scheduled to|need to)\b')
ACTUAL_ACTION=re.compile(r'\b(?:used|using|employed|employs|employing|utilized|utilizes|utilizing|wielded|jammed|jams|hacked|hacks|hacking|launched|launches|launching|carried out|struck|strikes|opened fire|opens fire|fired|firing|shelled|shelling|slammed|dropped|drops|destroyed|destroys|destroying|downed|shoots down|shot down|shooting down|occupied|imposed|violated|fought|intercepted|intercepts|captured|deployed|deploys|deploying|redeployed|engaged|engaging|hit|detonated|detonates|detonating|targeted|targeting|sank|sunk|sinks)\b')
def classify(sentence,name,cat,hits):
 text=norm(sentence);term=norm(name)
 # Short identifiers and single common word designations cannot establish the named weapon.
 if len(term)<=3 or term.isdigit():return UNCERTAIN,'ambiguous_short_or_numeric_designation'
 if cat.startswith('W') and not re.search(r'\d',term) and ' ' not in term and not(name.isupper() and len(name)>=3):return UNCERTAIN,'single_word_weapon_name_requires_review'
 if not CONTEXT.search(text) and cat.startswith('W'):return UNCERTAIN,'weapon_context_unresolved'
 if cat.startswith('W') and re.search(r'\b(?:was|were|been|is|are)\s+(?:destroyed|intercepted|captured|shot down|hit|targeted)\b|\bshot down\s+(?:a |an |the )?'+re.escape(term),text):return UNCERTAIN,'weapon_as_target_does_not_establish_its_use'
 if re.search(r'\b(?:armament|equipment|weapon)\s+used\s+by\b',text) and re.search(r'\bis\b',text):return UNCERTAIN,'equipment_description_not_specific_use_event'
 clauses=re.split(r';|\bbut\b|\bwhereas\b|\bwhile\b',text)
 candidates=[]
 for clause in clauses:
  if not any(n==name and c==cat for n,c,_,_ in find_terms(clause)):continue
  local=find_patterns(clause)
  # Prefer the longest overlapping expression: "can be used" overrides its nested "used".
  local=[h for h in local if not any(g['start']<=h['start'] and g['end']>=h['end'] and g['end']-g['start']>h['end']-h['start'] for g in local)]
  for h in local:
   code=h['code'];prefix=clause[max(0,h['start']-85):h['start']]
   if code==USED:
    if NEGATION.search(prefix):code=NOT_USED
    elif UNCERTAINTY.search(prefix):code=UNCERTAIN
    elif FUTURE.search(prefix) or NONUSE_CONTEXT.search(clause):code=NOT_USED
    elif not ACTUAL_ACTION.search(clause):code=UNCERTAIN
   candidates.append(code)
 if not candidates:return UNCERTAIN,'usage_expression_in_other_clause_or_relation_unclear'
 return preferred(candidates),'rule_classification'
TYPE_CONTEXT={
 'W02':r'radar|sensor|surveillance|electronic|reconnaissance',
 'W03':r'tank|armou?red|vehicle|apc|ifv',
 'W04':r'ship|vessel|frigate|destroyer|submarine|corvette|boat|naval|patrol craft',
 'W05':r'aircraft|helicopter|plane|fighter|bomber|drone|uav|airframe',
 'W06':r'missile|munition|torpedo|artillery|gun|howitzer|rocket|mortar|ammunition',
 'W07':r'air.defen[sc]e|missile|anti.aircraft',
 'W09':r'satellite|spacecraft'
}
def plausible_reference(sentence,name,cat,start,end):
 if cat.startswith('T'):return True
 text=norm(sentence);term=norm(name)
 context=re.search(r'\b(?:'+TYPE_CONTEXT.get(cat[:3],r'weapon')+r')s?\b',text[max(0,start-90):end+90])
 if term.isdigit() or len(term)==1:return False
 if re.search(r'[a-z]',term) and re.search(r'\d',term):return True
 if ' ' in term and CONTEXT.search(term):return True
 # Preserve all literal matches in evidence, but do not turn "attack" or "river" into weapons.
 if not context:return False
 if re.search(r'\b(?:commander in chief|lieutenant general|major general|prime minister|king charles|king abdullah)\b',text) and term in {'commander','general','king'}:return False
 original_case=re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',sentence)
 return bool(original_case)

class UsageClassifier:
 def __init__(self,matcher,sources):
  global find_terms
  find_terms=matcher.find_terms
  load_patterns(sources)
 def decide(self,row):
  sentence,name,category,start,end=row
  hits=find_patterns(sentence)
  code,reason=classify(sentence,name,category,hits) if hits else (None,'no_usage_pattern')
  if not plausible_reference(sentence,name,category,start,end):
   code=None;reason='literal_match_without_supported_weapon_reference'
  return code,reason,sorted({h['pattern_id'] for h in hits})
