"""[전처리 1단계 · 보고서 2.2, 3장] 텍스트 정규화(norm), 문장 분리(pysbd), Aho-Corasick 사전 매칭과 단어 경계 검사(bounded).

Actual dictionary matching, separated from usage inference.
"""
import csv,re,unicodedata
import ahocorasick,pysbd
def norm(s):
 return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',s).translate(str.maketrans({'–':'-','—':'-','‑':'-','‐':'-','’':"'"}))).strip().casefold()
def token(c):return c.isalnum() or c in "_'-"
def bounded(text,start,end):return not(start and token(text[start-1])) and not(end<len(text) and token(text[end]))

class TermMatcher:
 def __init__(self,sources):
  self.terms={}
  for file,col in [('sipri_dictionary.csv','wp_name'),('nato_dictionary.csv','tech_name')]:
   with (sources/file).open(encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):self.terms.setdefault(norm(r[col]),[]).append((r[col],r['category_id']))
  self.automaton=ahocorasick.Automaton()
  for term,rows in self.terms.items():self.automaton.add_word(term,(term,rows))
  self.automaton.make_automaton()

 def find_terms(self,text):
  text=norm(text);out=[]
  for end,(term,rows) in self.automaton.iter(text):
   start=end-len(term)+1
   if bounded(text,start,end+1):out.extend((name,cat,start,end+1) for name,cat in rows)
  return sorted(set(out))

 def scan(self,title,body):
  segmenter=pysbd.Segmenter(language='en',clean=False)
  parts=[('title',title or '')]+[('body',s.strip()) for p in body.splitlines() if p.strip() for s in segmenter.segment(p) if s.strip()]
  seen=set()
  for index,(section,sentence) in enumerate(parts):
   if sentence in seen:continue
   seen.add(sentence)
   for name,category,start,end in self.find_terms(sentence):
    yield (index,section,category,name,sentence,start,end)
