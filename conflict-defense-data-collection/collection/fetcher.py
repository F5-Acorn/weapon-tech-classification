"""[수집·저장 2단계] robots.txt 확인 → HTML 다운로드 → trafilatura 본문 추출 → 발행일 30일 불일치·400자 미만·차단 페이지 제외.

Original HTTP/body extraction logic; sentence matching removed for stage separation.
"""
import threading,time,datetime,re
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import requests,trafilatura
from lxml import html as lhtml
from .http_client import valid_url,get
UA='ArticleEvidenceResearch/1.0'
local=threading.local();robot_cache={};host_delay={}
def fetch(url,domain,expected_date=None):
 result={'url':url,'domain':domain,'status':'fetch_error','title':'','body':'','error':'','final_url':url}
 try:
  if not hasattr(local,'session'):
   local.session=requests.Session();local.session.headers['User-Agent']=UA
  s=local.session;u=valid_url(url);base=f'{u.scheme}://{u.netloc}'
  cached=robot_cache.get(base)
  if not cached or time.time()-cached[0]>86400:
   rr=get(s,base+'/robots.txt');rp=RobotFileParser()
   if rr.status_code in [401,403]:rp.disallow_all=True
   elif rr.status_code==404:rp.allow_all=True
   elif rr.status_code==200:rp.parse(rr.text.splitlines())
   else:result['status']='robots_unavailable';result['error']='robots HTTP '+str(rr.status_code);return result
   cached=(time.time(),rp);robot_cache[base]=cached
  rp=cached[1]
  if not rp.can_fetch(UA,url):result['status']='robots_denied';return result
  delay=max(1.5,rp.crawl_delay(UA) or 0);wait=host_delay.get(domain,0)+delay-time.monotonic()
  if wait>0:time.sleep(wait)
  response=get(s,url);host_delay[domain]=time.monotonic();result['final_url']=response.url
  if response.status_code!=200:result['status']='http_'+str(response.status_code);return result
  if 'html' not in response.headers.get('Content-Type',''):result['status']='not_html';return result
  original_path=urlsplit(url).path.strip('/');final_path=urlsplit(response.url).path.strip('/')
  if len(original_path.split('/'))>1 and not final_path:result['status']='redirect_to_home';return result
  document=lhtml.fromstring(response.content,parser=lhtml.HTMLParser(remove_comments=True))
  for element in document.xpath('//*[@class or @id]'):
   label=' '+element.get('class','')+' '+element.get('id','')+' '
   if re.search(r'(?:^|[\s_-])(?:related|recommended|recommendations|most-popular|read-more|latest-news|newsletter|social-share)(?:$|[\s_-])',label,re.I) and element.getparent() is not None:element.drop_tree()
  data=trafilatura.bare_extraction(document,url=response.url,with_metadata=True,include_comments=False,include_tables=False,favor_precision=True)
  if not data:result['status']='no_body';return result
  data=data.as_dict() if hasattr(data,'as_dict') else data
  title=data.get('title') or '';body=data.get('text') or ''
  result.update(title=title,body=body)
  extracted_date=data.get('date')
  if expected_date and extracted_date:
   try:
    delta=abs((datetime.date.fromisoformat(str(extracted_date)[:10])-datetime.date.fromisoformat(expected_date[:10])).days)
    if delta>30:result['status']='article_date_mismatch';result['error']=f'input_date={expected_date};extracted_date={extracted_date}';return result
   except ValueError:pass
  if re.search(r'client challenge|just a moment|access denied|verify you are human|page not found|404 not found|attention required',title,re.I):result['status']='access_challenge';return result
  if len(body)<400:result['status']='short_or_partial';return result
  result['status']='extracted'
 except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)[:300]
 return result
