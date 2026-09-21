# -*- coding: utf-8 -*-
"""
fetch_bodies.py
v1/v2 기사 URL에서 본문과 발행일을 수집한다. 중단해도 같은 명령으로 이어받는다.

  python fetch_bodies.py plan   --urls "..\\v1_russia_ukraine_unique_articles.csv" "..\\v2_middle_east_unique_articles.csv"
  python fetch_bodies.py pilot  --n 200            # 도메인별 성공률 먼저 측정 (필수)
  python fetch_bodies.py fetch  --workers 6        # 본문 수집 (밤새 실행, 중단·재개 가능)
  python fetch_bodies.py export                    # article_texts.csv 생성
  python fetch_bodies.py status                    # 진행 현황

원칙
  · robots.txt 를 지킨다. 차단된 URL 은 가져오지 않고 'robots 차단'으로 기록한다
  · 유료·로그인 장벽을 우회하지 않는다. 403/402 는 실패로 기록하고 넘어간다
  · 도메인당 요청 간격을 지킨다 (기본 3초). 도메인끼리는 병렬
  · 실패는 '무관 기사'가 아니라 실패로 남긴다 (기획서 5단계와 동일)

필요 패키지: 없음 (표준 라이브러리만으로 동작)
선택 패키지: trafilatura — 있으면 본문 추출 품질이 올라간다
             pip install trafilatura
"""
import argparse, csv, gzip, hashlib, io, json, os, random, re, sqlite3, stat, sys, threading, time
import urllib.error, urllib.parse, urllib.request, urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

DB           = "bodies.sqlite"
UA           = ("Mozilla/5.0 (compatible; F5-DefenseDashboard-Research/1.0; "
                "academic non-commercial research)")
TIMEOUT      = 20
DOMAIN_DELAY = 3.0       # 같은 도메인 연속 요청 최소 간격(초)
MIN_WORDS    = 60        # 이보다 짧으면 '본문 부족'
TRACK_PARAMS = re.compile(r"^(utm_|fbclid|gclid|mc_|ref|ref_src|CMP|cmp|icid|ito)")

_locks, _last = {}, {}
_lk = threading.Lock()
_stop = threading.Event()       # Ctrl+C 시 워커들이 즉시 빠져나오게 하는 신호


# ------------------------------------------------------------------ 공통
def norm_url(u: str) -> str:
    try:
        p = urllib.parse.urlsplit(u.strip())
    except ValueError:
        return u.strip()
    host = (p.hostname or "").lower()
    for pre in ("www.", "m.", "amp."):
        if host.startswith(pre):
            host = host[len(pre):]
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not TRACK_PARAMS.match(k)]
    path = re.sub(r"/(amp|amp\.html)$", "", p.path).rstrip("/") or "/"
    return urllib.parse.urlunsplit(("https", host, path,
                                    urllib.parse.urlencode(q), ""))


def doc_id(url_norm: str) -> str:
    return "A" + hashlib.md5(url_norm.encode("utf-8")).hexdigest()[:10]


def domain_of(url_norm: str) -> str:
    return urllib.parse.urlsplit(url_norm).hostname or "?"


def safe_write(path: Path, write_fn):
    try:
        if path.exists():
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        write_fn(path); return path
    except PermissionError:
        alt = path.with_name(path.stem + "_new" + path.suffix)
        write_fn(alt)
        print(f"[주의] '{path.name}' 잠김 -> '{alt.name}' 으로 저장했습니다.")
        return alt


# ------------------------------------------------------------------ DB
def open_db(out: Path):
    con = sqlite3.connect(out / DB, timeout=60, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS urls(
        url_norm TEXT PRIMARY KEY, url TEXT, doc_id TEXT, domain TEXT,
        datasets TEXT, sqldate TEXT, groups TEXT,
        status TEXT, http_code INTEGER, title TEXT, published_at TEXT,
        words INTEGER, body TEXT, error TEXT, fetched_at TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_status ON urls(status)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_domain ON urls(domain)")
    con.commit()
    return con


def load_urls(con, paths):
    """paths 는 경로 목록. 폴더 이름에 쉼표가 있을 수 있으므로 쉼표로 쪼개지 않는다."""
    n_new = 0
    for p in paths:
        if not Path(p).exists():
            raise SystemExit(f"\n[중단] '{p}' 파일이 없습니다.\n")
        with open(p, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                u = (row.get("article_url") or "").strip()
                if not u.startswith("http"):
                    continue
                un = norm_url(u)
                cur = con.execute("SELECT datasets,groups FROM urls WHERE url_norm=?", (un,))
                hit = cur.fetchone()
                ds, gp = row.get("dataset_version", ""), row.get("candidate_group", "")
                if hit:
                    d = "|".join(sorted(set(filter(None, (hit[0] or "").split("|") + [ds]))))
                    g = "|".join(sorted(set(filter(None, (hit[1] or "").split("|") + [gp]))))
                    con.execute("UPDATE urls SET datasets=?,groups=? WHERE url_norm=?",
                                (d, g, un))
                else:
                    con.execute(
                        "INSERT INTO urls(url_norm,url,doc_id,domain,datasets,sqldate,"
                        "groups,status) VALUES(?,?,?,?,?,?,?,'대기')",
                        (un, u, doc_id(un), domain_of(un), ds,
                         str(row.get("SQLDATE", "")), gp))
                    n_new += 1
        con.commit()
    return n_new


# ------------------------------------------------------------------ 추출
class _Extract(HTMLParser):
    """trafilatura 가 없을 때 쓰는 최소 추출기: 본문 영역의 <p> 를 모은다."""
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "figcaption"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.in_p, self.buf, self.paras = 0, 0, [], []
        self.jsonld, self.meta, self._ld = [], {}, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
            if tag == "script" and a.get("type") == "application/ld+json":
                self._ld = True
        elif tag == "p":
            self.in_p += 1; self.buf = []
        elif tag == "meta":
            k = a.get("property") or a.get("name") or a.get("itemprop")
            if k and a.get("content"):
                self.meta.setdefault(k.lower(), a["content"])
        elif tag == "time" and a.get("datetime"):
            self.meta.setdefault("time:datetime", a["datetime"])

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1); self._ld = False
        elif tag == "p" and self.in_p:
            self.in_p -= 1
            t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if len(t) > 40:
                self.paras.append(t)
            self.buf = []

    def handle_data(self, d):
        if self._ld:
            self.jsonld.append(d)
        elif self.in_p and not self.skip:
            self.buf.append(d)


def pick_published(meta, jsonld):
    for k in ("article:published_time", "datepublished", "og:published_time",
              "pubdate", "date", "dc.date.issued", "time:datetime"):
        if meta.get(k):
            return meta[k]
    for blob in jsonld:
        try:
            data = json.loads(blob)
        except Exception:
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if isinstance(obj, dict):
                for k in ("datePublished", "dateCreated", "uploadDate"):
                    if obj.get(k):
                        return str(obj[k])
    return ""


def extract(html: str, url: str):
    """-> (title, body, published_at, extractor)"""
    try:
        import trafilatura
        body = trafilatura.extract(html, url=url, include_comments=False,
                                   include_tables=False, favor_precision=True) or ""
        md = {}
        try:
            m = trafilatura.extract_metadata(html, default_url=url)
            md = {"title": getattr(m, "title", "") or "",
                  "date": getattr(m, "date", "") or ""}
        except Exception:
            pass
        if body.strip():
            return md.get("title", ""), body.strip(), md.get("date", ""), "trafilatura"
    except ImportError:
        pass
    except Exception:
        pass
    p = _Extract()
    try:
        p.feed(html)
    except Exception:
        pass
    title = p.meta.get("og:title") or p.meta.get("twitter:title") or ""
    return title, "\n\n".join(p.paras), pick_published(p.meta, p.jsonld), "내장 추출기"


# ------------------------------------------------------------------ 요청
_robots = {}


def robots_ok(url_norm, respect=True):
    if not respect:
        return True
    host = domain_of(url_norm)
    with _lk:
        rp = _robots.get(host)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"https://{host}/robots.txt")
        try:
            req = urllib.request.Request(f"https://{host}/robots.txt",
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                rp.parse(r.read().decode("utf-8", "ignore").splitlines())
        except Exception:
            rp.allow_all = True      # robots.txt 를 못 읽으면 막지 않는다 (표준 동작)
        with _lk:
            _robots[host] = rp
    try:
        return rp.can_fetch(UA, url_norm)
    except Exception:
        return True


def throttle(host, delay):
    with _lk:
        lk = _locks.setdefault(host, threading.Lock())
    with lk:
        with _lk:
            prev = _last.get(host, 0.0)
        wait = delay + random.uniform(0, 0.6) - (time.time() - prev)
        if wait > 0:
            if _stop.wait(wait):      # 중단 신호가 오면 기다리지 않고 즉시 반환
                return
        with _lk:
            _last[host] = time.time()


def fetch_one(url, url_norm, delay, respect_robots):
    """-> dict(status, http_code, title, published_at, words, body, error)"""
    if not robots_ok(url_norm, respect_robots):
        return dict(status="robots 차단", http_code=0, error="robots.txt 가 금지")
    throttle(domain_of(url_norm), delay)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            code, raw = r.getcode(), r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            ct = r.headers.get_content_charset() or "utf-8"
            html = raw.decode(ct, "ignore")
    except urllib.error.HTTPError as e:
        label = {401: "로그인 필요", 402: "유료 제한", 403: "접근 차단",
                 404: "페이지 없음", 410: "페이지 없음", 429: "요청 제한"}.get(e.code, "요청 실패")
        return dict(status=label, http_code=e.code, error=f"HTTP {e.code}")
    except Exception as e:
        return dict(status="요청 실패", http_code=0, error=f"{type(e).__name__}: {e}"[:200])

    title, body, pub, how = extract(html, url)
    w = len(body.split())
    if w < MIN_WORDS:
        return dict(status="본문 부족", http_code=code, title=title,
                    published_at=pub, words=w, body=body,
                    error=f"{w}단어 ({how})")
    return dict(status="본문 수집", http_code=code, title=title, published_at=pub,
                words=w, body=body, error="")


# ------------------------------------------------------------------ 명령
def cmd_plan(con, args):
    rows = con.execute("SELECT domain, COUNT(*) c FROM urls GROUP BY domain "
                       "ORDER BY c DESC").fetchall()
    total = sum(c for _, c in rows)
    worst = max((c for _, c in rows), default=0) * args.delay / 3600
    out = Path(args.out)
    safe_write(out / "fetch_plan.csv", lambda p: _csv(p, ["domain", "urls", "예상시간_시간"],
               [[d, c, round(c * args.delay / 3600, 2)] for d, c in rows]))
    print(f"URL {total}건 / 도메인 {len(rows)}개")
    print(f"도메인 병렬 기준 예상 소요: 약 {worst:.1f}시간 "
          f"(가장 큰 도메인 {rows[0][0] if rows else '-'} 기준, 간격 {args.delay}초)")
    print("상위 12개 도메인:")
    for d, c in rows[:12]:
        print(f"  {d:28s} {c:6d}건  ~{c*args.delay/3600:5.2f}h")
    print(f"\n저장: {out/'fetch_plan.csv'}")
    print("\n다음: python fetch_bodies.py pilot --n 200   (도메인별 성공률을 먼저 재십시오)")


def interleave(targets):
    """도메인별로 돌아가며 섞는다.

    원본 CSV 는 같은 도메인이 뭉쳐 있어(연속 행의 91.8%가 동일 도메인, 최대 4,358행 연속)
    워커 여러 개가 동시에 같은 도메인을 잡고 3초 간격 락에서 줄을 선다. 결과적으로
    워커를 몇 개를 띄우든 초당 처리량이 도메인 1개분으로 떨어진다.
    라운드로빈으로 섞으면 워커마다 다른 도메인을 잡아 병렬성이 실제로 살아난다.
    """
    from collections import defaultdict, deque
    buckets = defaultdict(deque)
    for un, u in targets:
        buckets[domain_of(un)].append((un, u))
    order, qs = [], list(buckets.values())
    while qs:
        qs = [q for q in qs if q]
        for q in qs:
            order.append(q.popleft())
    return order


def _csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def _run(con, args, targets, label):
    from collections import Counter
    targets = interleave(targets)
    remain = Counter(domain_of(un) for un, _ in targets)   # 도메인별 남은 건수
    ndom = len(remain)
    done = {"n": 0, "mark_t": time.time(), "mark_n": 0}
    lock = threading.Lock()
    t0 = time.time()

    def work(rec):
        if _stop.is_set():
            return
        un, u = rec
        r = fetch_one(u, un, args.delay, not args.ignore_robots)
        with lock:
            con.execute(
                "UPDATE urls SET status=?,http_code=?,title=?,published_at=?,words=?,"
                "body=?,error=?,fetched_at=? WHERE url_norm=?",
                (r.get("status"), r.get("http_code", 0), r.get("title", ""),
                 r.get("published_at", ""), r.get("words", 0), r.get("body", ""),
                 r.get("error", ""), datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 un))
            remain[domain_of(un)] -= 1
            done["n"] += 1
            if done["n"] % 20 == 0:
                con.commit()
                now = time.time()
                recent = (done["n"] - done["mark_n"]) / max(now - done["mark_t"], 1e-9) * 60
                avg = done["n"] / max(now - t0, 1e-9) * 60
                done["mark_t"], done["mark_n"] = now, done["n"]
                alive = sum(1 for v in remain.values() if v > 0)
                bigd, bign = max(remain.items(), key=lambda x: x[1]) if remain else ("", 0)
                eta = bign * (args.delay + 0.3) / 3600     # 마지막까지 남는 도메인이 병목
                print(f"  {done['n']}/{len(targets)}  최근 {recent:.0f}건/분 "
                      f"(누적 {avg:.0f})  활성 도메인 {alive}개  "
                      f"남은 예상 {eta:.1f}시간 [{bigd} {bign}건]")

    print(f"{label}: {len(targets)}건, 도메인 {ndom}개, 워커 {args.workers}개, "
          f"도메인 간격 {args.delay}초")
    print(f"  도메인 라운드로빈 정렬 적용 (워커가 서로 다른 도메인을 잡도록)")
    ideal = min(args.workers, ndom) * 60 / (args.delay + 0.3)
    bigd, bign = max(remain.items(), key=lambda x: x[1])
    print(f"  시작 처리량 약 {ideal:.0f}건/분 (도메인이 소진될수록 느려집니다)")
    print(f"  완료 예상 {bign*(args.delay+0.3)/3600:.1f}시간 "
          f"— 가장 큰 도메인 {bigd} {bign}건이 병목")
    if args.workers < ndom:
        print(f"  [권장] 도메인이 {ndom}개이므로 --workers {ndom} 까지 올려도 "
              f"도메인별 간격은 그대로 지켜집니다")
    ex = ThreadPoolExecutor(max_workers=args.workers)
    interrupted = False
    try:
        futs = [ex.submit(work, t) for t in targets]
        for f in futs:
            f.result()
    except KeyboardInterrupt:
        interrupted = True
        _stop.set()
        print("\n중단 요청을 받았습니다. 진행 중인 요청만 마치고 저장합니다 "
              "(최대 20초)...")
    finally:
        try:
            ex.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass
        with lock:
            con.commit()

    if interrupted:
        left = con.execute("SELECT COUNT(*) FROM urls WHERE status='대기'").fetchone()[0]
        print(f"저장 완료. 처리 {done['n']}건, 남은 대기 {left}건.")
        print("같은 명령을 다시 실행하면 이어받습니다. 중복 요청은 하지 않습니다.")

    st = con.execute("SELECT status, COUNT(*) FROM urls WHERE status!='대기' "
                     "GROUP BY status ORDER BY 2 DESC").fetchall()
    print("\n상태별 누적:")
    for s, c in st:
        print(f"  {s:10s} {c}")


def cmd_pilot(con, args):
    """도메인별로 고르게 표본을 뽑아 성공률을 먼저 잰다."""
    doms = [d for d, in con.execute("SELECT DISTINCT domain FROM urls "
                                    "WHERE status='대기'").fetchall()]
    per = max(1, args.n // max(len(doms), 1))
    tg = []
    for d in doms:
        tg += con.execute("SELECT url_norm,url FROM urls WHERE status='대기' AND domain=? "
                          "ORDER BY RANDOM() LIMIT ?", (d, per)).fetchall()
    tg = tg[:args.n]
    _run(con, args, tg, "시범 수집")
    rows = con.execute(
        "SELECT domain, COUNT(*) n, SUM(status='본문 수집') ok FROM urls "
        "WHERE fetched_at IS NOT NULL GROUP BY domain ORDER BY n DESC").fetchall()
    out = Path(args.out)
    safe_write(out / "pilot_by_domain.csv", lambda p: _csv(
        p, ["domain", "시도", "성공", "성공률"],
        [[d, n, o or 0, round((o or 0) / n * 100, 1)] for d, n, o in rows]))
    print(f"\n저장: {out/'pilot_by_domain.csv'}")
    print("성공률이 낮은 도메인은 --skip-domains 로 빼고 본 수집을 돌리십시오.")


def cmd_fetch(con, args):
    q = "SELECT url_norm,url FROM urls WHERE status='대기'"
    p = []
    if args.skip_domains:
        ds = [x.strip() for x in args.skip_domains.split(",") if x.strip()]
        q += " AND domain NOT IN (" + ",".join("?" * len(ds)) + ")"; p = ds
    if args.only_domains:
        ds = [x.strip() for x in args.only_domains.split(",") if x.strip()]
        q += " AND domain IN (" + ",".join("?" * len(ds)) + ")"; p += ds
    if args.limit:
        q += f" LIMIT {int(args.limit)}"
    tg = con.execute(q, p).fetchall()
    if not tg:
        print("대기 중인 URL 이 없습니다."); return
    _run(con, args, tg, "본 수집")
    print("\n다음: python fetch_bodies.py export")


def cmd_export(con, args):
    out = Path(args.out)
    rows = con.execute(
        "SELECT doc_id,url_norm,url,domain,datasets,groups,sqldate,published_at,"
        "title,words,body FROM urls WHERE status='본문 수집' ORDER BY doc_id").fetchall()
    hdr = ["article_id", "url_norm", "url", "domain", "datasets", "groups",
           "sqldate", "published_at", "title", "words", "body"]
    safe_write(out / "article_texts.csv", lambda p: _csv(p, hdr, [list(r) for r in rows]))
    log = con.execute(
        "SELECT doc_id,url,domain,status,http_code,words,published_at,error,fetched_at "
        "FROM urls ORDER BY domain,doc_id").fetchall()
    safe_write(out / "fetch_log.csv", lambda p: _csv(
        p, ["article_id", "url", "domain", "status", "http_code", "words",
            "published_at", "error", "fetched_at"], [list(r) for r in log]))
    nopub = sum(1 for r in rows if not r[7])
    print(f"본문 확보 {len(rows)}건 -> article_texts.csv")
    print(f"  발행일 미확인 {nopub}건 (집계 시 GDELT 기록일로 대체하고 표시 필요)")
    print(f"전체 로그 {len(log)}건 -> fetch_log.csv")
    print("\n다음: python match_weapons.py --terms weapon_terms.csv "
          "--texts article_texts.csv --id-col article_id --text-col body --out .")


def cmd_status(con, args):
    tot = con.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
    print(f"URL 총 {tot}건")
    for s, c in con.execute("SELECT status,COUNT(*) FROM urls GROUP BY status "
                            "ORDER BY 2 DESC"):
        print(f"  {s:10s} {c:6d}  ({c/max(tot,1)*100:4.1f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "pilot", "fetch", "export", "status"])
    ap.add_argument("--urls", nargs="+",
                    help='v1/v2 CSV 경로를 공백으로 구분해 나열 (최초 1회). '
                         '경로에 공백·쉼표가 있으면 각각 따옴표로 감싸십시오.')
    ap.add_argument("--out", default=".")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--delay", type=float, default=DOMAIN_DELAY)
    ap.add_argument("--n", type=int, default=200, help="pilot 표본 수")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-domains", default="")
    ap.add_argument("--only-domains", default="")
    ap.add_argument("--ignore-robots", action="store_true",
                    help="권장하지 않음. 연구 목적이라도 robots.txt 는 지키는 것이 기본")
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    con = open_db(out)
    if args.urls:
        print(f"URL 적재: 신규 {load_urls(con, args.urls)}건")
    if con.execute("SELECT COUNT(*) FROM urls").fetchone()[0] == 0:
        raise SystemExit("\n[중단] URL 이 없습니다. --urls 로 v1/v2 CSV 를 지정하십시오.\n"
                         '  예) python fetch_bodies.py plan --urls '
                         '"..\\v1_russia_ukraine_unique_articles.csv" '
                         '"..\\v2_middle_east_unique_articles.csv"\n')
    {"plan": cmd_plan, "pilot": cmd_pilot, "fetch": cmd_fetch,
     "export": cmd_export, "status": cmd_status}[args.cmd](con, args)
    con.close()


if __name__ == "__main__":
    main()
