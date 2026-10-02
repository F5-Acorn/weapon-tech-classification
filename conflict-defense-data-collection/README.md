# conflict-defense-data-collection

F5팀 「글로벌 공개보도 기반 주요 분쟁의 무기·기술 사용 동향 대시보드」의 **데이터 수집·저장** 코드입니다.
GDELT에서 15개 국가 간 분쟁의 후보 기사를 뽑고(BigQuery), 기사 본문을 수집해 작업 DB(`work/pipeline.sqlite`)에 저장합니다.
이 DB는 전처리 저장소(`conflict-defense-data-preprocessing`)가 이어받아 사용 판정을 합니다.

## 구성

```text
├── README.md
├── main.py                 실행 (1단계, 2단계, status)
├── sql/
│   ├── 00_create_dataset.sql        데이터셋 생성
│   ├── 01_candidates_raw.sql        GDELT 사건×기사 후보 추출 (약 490GB, 7,126,395행)
│   ├── 02_candidate_urls.sql        분쟁×URL 요약 + 대표 발생 위치 (2,832,396행)
│   └── 03_erd_articles_export.sql   후보 기사 CSV 5컬럼 (2,832,396행)
└── collection/
    ├── config.py           config.json 읽기
    ├── common.py           작업 DB 연결·단계 기록·잠금
    ├── prepare.py          1단계: 후보 CSV 검사, 작업 DB 생성
    ├── collect.py          2단계: 본문 수집 / 기존 수집 DB 복사
    ├── fetcher.py          robots.txt·HTTP·본문 추출·제외 조건
    └── http_client.py      공개 주소 확인·8MB 제한 다운로드
```

## 1단계: 후보 기사 추출 (BigQuery)

`sql/`의 00 → 01 → 02 → 03을 BigQuery 콘솔에서 순서대로 실행하고 03 결과를 CSV로 내려받습니다.
2026-09-23 실행본과 같고, 목적지 `__PROJECT__.__DATASET__`만 본인 프로젝트·데이터셋으로 바꿔 씁니다.

후보 조건 (팀 결정 2026-09-23)
1. 행동 유형: `EventRootCode` 15·17·18·19·20 그리고 `QuadClass = 4`
2. 교전국 쌍: `Actor1CountryCode`·`Actor2CountryCode`가 분쟁 양측 교전국 (UCDP `gwno_a/gwno_b` → CAMEO 국가코드, 양방향)
3. 기사 언급 기간 2016-01-01 ~ 2026-09-23, `MentionType = 1`, http(s) URL

후보 CSV 컬럼: `article_id`(FARM_FINGERPRINT(conflict_id|url) 양수 63비트, 문자열로 보존), `conflict_id`, `published_date`(GDELT 최초 수집일), `article_url`, `title`(비어 있음)

## 2단계: 본문 수집

Python 3.11 이상. 필요한 패키지: `requests==2.34.2`, `trafilatura==2.2.0`, `lxml==6.1.3`

```powershell
pip install requests==2.34.2 trafilatura==2.2.0 lxml==6.1.3
```

`config.json` (상대 경로는 이 파일 위치 기준, 전처리 저장소와 같은 파일을 써도 됨)

```json
{
  "input_csv": "data/articles_candidates.csv",
  "work_dir": "work"
}
```

```powershell
python main.py 1 --config config.json                       # 후보 CSV 검사, 작업 DB 생성
python main.py 2 --config config.json --fetch-network        # 본문 수집 (기본 48개 동시 작업)
python main.py 2 --config config.json --cached-db "D:/기존작업/collection.sqlite"   # 이미 수집한 본문을 쓸 때
python main.py status --config config.json
```

- 고유 URL마다 한 번만 시도하고 실패한 URL은 다시 시도하지 않습니다. 같은 도메인에는 동시에 한 요청만 보내고 robots.txt와 최소 1.5초 간격을 지킵니다.
- 다시 실행하면 남은 `pending`만 처리합니다. `work/STOP` 파일을 만들면 진행 중인 요청만 마치고 멈춥니다. `--limit N`은 N건만 시도합니다.
- 본문 제외: HTTP 200 아님, HTML 아님, 홈으로 리다이렉트, 본문 추출 실패, 차단·오류 페이지, **본문 400자 미만**, **추출한 발행일이 GDELT 날짜와 30일 넘게 다름**. 제외된 URL도 상태값과 함께 DB에 남습니다.
- `--cached-db`는 기존 DB를 읽기 전용으로 열고, 후보 CSV와 행 순서·ID가 모두 같을 때만 제목·본문·수집 상태를 복사합니다.

## 작업 DB 형식 (전처리 저장소로 넘기는 파일)

`work/pipeline.sqlite`, `meta.db_format = "f5-collection-db-v2"`

| 테이블 | 컬럼 |
|---|---|
| meta | key, value(JSON) — db_format, collect1(input_sha256 등), collect2(수집 상태별 건수). 전처리는 prep1~prep4를 추가 |
| input_rows | row_no, article_id, conflict_id, published_date, url, title (후보 CSV 그대로) |
| pages | url, domain, status, title, body(zlib 압축 UTF-8), error, fetched_at, final_url, body_sha256 |

`pages.status`는 `extracted`, `pending`, `http_*`, `not_html`, `redirect_to_home`, `no_body`, `article_date_mismatch`, `access_challenge`, `short_or_partial`, `robots_denied`, `robots_unavailable`, `invalid_url`, `fetch_error` 중 하나이며, 전처리는 `extracted`만 씁니다.
전처리 1단계(사전 매칭)가 시작되면 수집 결과가 고정되어 2단계는 더 수집하지 않습니다.

후보 CSV·작업 DB 같은 데이터는 저장소에 올리지 않습니다.
