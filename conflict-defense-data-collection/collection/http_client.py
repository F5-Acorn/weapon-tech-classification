"""[수집·저장 2단계] 공개 주소만 허용하고 응답을 8MB로 제한하는 HTTP 도우미.

Original public-URL and bounded-download helpers.
"""
import ipaddress,socket
from urllib.parse import urlsplit
def valid_url(url):
 u=urlsplit(url)
 if u.scheme not in ['http','https'] or not u.hostname or u.username:raise ValueError('Unsupported URL')
 for x in socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM):
  if not ipaddress.ip_address(x[4][0]).is_global:raise ValueError('Non-public destination')
 return u

def get(session,url):
 for _ in range(6):
  valid_url(url);r=session.get(url,timeout=(10,20),allow_redirects=False,stream=True)
  if r.is_redirect:
   from urllib.parse import urljoin
   target=urljoin(url,r.headers['location']);r.close();url=target;continue
  chunks=[];size=0
  for block in r.iter_content(65536):
   size+=len(block)
   if size>8_000_000:r.close();raise ValueError('Response exceeds 8 MB')
   chunks.append(block)
  r._content=b''.join(chunks);return r
 raise ValueError('Too many redirects')
