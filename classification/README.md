# 무기·기술 분류 파이프라인 (classification)

GDELT로 수집한 해외 기사에서 **무기·기술을 식별하고(1차), 실제 사용 보도인지 판정하고(2차),
국방 분류체계의 대·중·소 3층 분류를 붙여(3차)** 대시보드 입력 테이블을 만든다.

- 프로젝트: 글로벌 안보 이슈·무기체계 수요 변화 분석 기반 K-방산 기회 모니터링 대시보드 (F5조)
- 담당: 오휘준
- 기준일: 2026-09-21

---

## 1. 전체 흐름

```
0단계  fetch_bodies.py   기사 URL → 본문·발행일          → article_texts.csv
1단계  stage1.py         본문 → 무기/기술 단어 문장 추출   → 1차_무기기술_문장추출.csv
2단계  stage2.py         문장 → 사용여부 판정             → 2차_사용여부_판정.csv
3단계  stage3.py         판정 → 대·중·소 분류 + 집계      → 3차_분류매핑_문장.csv  ← 대시보드 입력
       stage3_split.py   분쟁별·층위별 파일로 분해
       make_final.py     분쟁별 (보도일 × 중분류) 최종 집계
```

0단계는 수 시간(네트워크 대기)이 걸리고, **1~3단계는 전체 2분 이내**다.
사전만 수정하고 다시 돌리는 작업은 코드 수정 없이 1~3단계 재실행으로 끝난다.

---

## 2. 설치

팀 저장소 `F5-Acorn/conflict-defense-news-dashboard` 의 `classification/` 폴더다.

```bash
git clone https://github.com/F5-Acorn/conflict-defense-news-dashboard.git
cd conflict-defense-news-dashboard/classification
pip install -r requirements.txt
```

Python 3.10 이상 (3.14에서 확인). 필요 패키지는 `pandas`, `openpyxl`, `wordfreq` 세 개다.
`fetch_bodies.py`는 표준 라이브러리만으로 동작하며, `trafilatura`를 추가로 설치하면 본문 추출 품질이 올라간다.

---

## 3. 실행

### 0단계 — 본문 수집 (처음 한 번)

```bash
python fetch_bodies.py plan  --urls "v1_russia_ukraine_unique_articles.csv" "v2_middle_east_unique_articles.csv"
python fetch_bodies.py pilot --n 200        # 도메인별 성공률 측정 — 건너뛰지 말 것
python fetch_bodies.py fetch --workers 6 --skip-domains nytimes.com,washingtonpost.com
python fetch_bodies.py export               # data/input/article_texts.csv 생성
python fetch_bodies.py status               # 진행 현황
```

- 수집 결과는 `bodies.sqlite`에 누적된다. **중단해도 같은 명령으로 이어받는다.**
- robots.txt를 지키고 유료·로그인 장벽은 우회하지 않는다. 도메인당 3초 간격, 도메인끼리는 병렬.
- 실패는 '무관 기사'가 아니라 사유별(`접근 차단`/`페이지 없음`/`본문 부족` 등)로 기록한다.
- `export`로 나온 `article_texts.csv`를 `data/input/`에 두면 1단계가 바로 읽는다.

### 1~3단계 — 분류

```bash
python run_all.py            # 1~3차를 순서대로 실행 (권장)
```

개별 실행도 가능하다. **네 스크립트 모두 같은 출력 폴더를 써야 한다.**

```bash
python stage1.py            # 출력 폴더 생략 시 ./out
python stage2.py
python stage3.py
python stage3_split.py
python make_final.py

python run_all.py D:\out3   # 출력 폴더를 직접 지정할 때
```

---

## 4. 폴더 구성

| 경로 | 내용 |
|---|---|
| `config.py` | **모든 경로를 여기서 관리한다.** 기본값은 리포 기준 상대경로 |
| `fetch_bodies.py` | 0단계 본문 수집 (재개 가능, robots 준수) |
| `dicts.py` | 공용 모듈 — 사전 로드 / 토큰화 / n-gram 색인 / 대소문자 규칙 |
| `stage1.py` | 1차 — 무기·기술 단어가 있는 문장 추출 |
| `stage2.py` | 2차 — 사용여부 판정 |
| `stage3.py` | 3차 — 대·중·소 분류 매핑 및 집계 |
| `stage3_split.py` | 3차 결과를 분쟁별·층위별 파일로 분해 |
| `make_final.py` | 분쟁별 (보도일 × 중분류) 최종 집계 |
| `run_all.py` | 1~3차 일괄 실행 |
| `data/dict/` | 사전 (리포에 포함, 팀이 직접 수정) |
| `data/input/` | `article_texts.csv` 등 입력 — **깃에 올리지 않음** |
| `out/` | 산출물 — **깃에 올리지 않음** |

### 경로를 바꾸고 싶을 때

`config.py`를 고치거나 환경변수로 덮어쓴다. 코드 수정은 필요 없다.

```powershell
$env:WT_ARTICLE_TEXTS = "D:\data\article_texts.csv"
$env:WT_OUT_DIR = "D:\out3"
python run_all.py
```

---

## 5. 사전 — 팀이 직접 수정하는 파일

`data/dict/` 아래에 있다. 코드를 고치지 않고 이 파일들만 바꾸면 결과가 바뀐다.

| 파일 | 원래 이름 | 내용 |
|---|---|---|
| `SIPRI_keywords_EN_simple.csv` | 동일 | 1차 무기 사전 210항목 |
| `NATO_keywords_EN_simple.csv` | 동일 | 1차 기술 사전 114항목 |
| `usage_weapon.xlsx` | 무기_사용여부.xlsx | 2차 무기 사용여부 54표현 → 활용형 253개로 전개 |
| `usage_tech.xlsx` | 기술_사용여부.xlsx | 2차 기술 사용여부 34표현 |
| `map_weapon.xlsx` | 무기 대분류 매핑 - 국방 무기체계 분류체계.xlsx | 3차 무기 중분류 |
| `map_tech.xlsx` | 기술 대분류 매핑 - 국방과학기술 분류체계.xlsx | 3차 기술 중분류 |
| `model_exclude.csv` | 동일 | 모델명 제외 목록 16개 (지명·인명·일반명사) |

`dicts.py` 안에서 조정하는 값:

- `PREV_BLOCK` — 선행어 차단 (`oil tanker`, `think tank`, `anti-tank` 등)
- `ZIPF_UPPER_ONLY` / `ZIPF_NOT_LOWER` — 모델명 대소문자 규칙 임계값
- `stage3.py`의 `DAE` — 대분류 명칭 (`W05 항공`, `T01 센서` 등)

---

## 6. 오탐 차단 방식

SIPRI 모델명에 지명·인명·일반명사가 섞여 있다(`Attack` 초계정, `Berlin` 보급함, 레이더 상표명 `HARD`·`PAGE`·`SMART`).
세 겹으로 막는다.

1. **대소문자 규칙** — 모델명·약어에만 적용. 영어 일상빈도(wordfreq zipf)로 임계값을 나눠
   흔한 단어(`hard`·`page`·`smart`)는 원문이 전부 대문자일 때만, 중간 빈도(`Taurus`·`Patriot`)는 소문자만 아니면 인정,
   드문 단어(`Himars`·`Javelin`)는 대소문자 무관. → `Himars` 표기도 정상 인정된다.
2. **단서 조건** — 숫자 없는 순알파벳 모델명은 같은 문장에 종류 단어나 군사 단서가 있어야 인정.
3. **제외 목록** — `model_exclude.csv`.

차단된 건은 전부 `1차_차단내역.csv`에 사유와 함께 남는다. **규칙을 바꿀 때는 이 파일부터 본다.**

> 문맥 단서에 기능어(`to`, `and`)나 국가명(`ukraine`, `russia`)을 넣으면 안 된다.
> 모든 기사에 나오므로 검증이 무력화된다.

---

## 7. 실행 결과 (2026-09-21 기준)

본문 18,083건 전량 실행.

| 차시 | 산출물 | 건수 |
|---|---|---|
| 1차 | 무기·기술 문장 추출 | 23,032건 (문장 19,641 / 기사 7,170) |
| 1차 | 차단 내역 | 122,227건 |
| 2차 | 사용여부 판정 | 6,718건 (사용 보도 4,653 / 사용 외 언급 1,301 / 확인 필요 764) |
| 3차 | 분류 매핑 | 6,718건 |

분쟁별 사용 보도: 러·우 4,009건 / 중동 640건.
상위 소분류: tank 711 / multiple rocket launcher 444 / bomber aircraft 415 / fighter aircraft 342.

---

## 8. 알려진 한계 — 사용 전 확인할 것

1. **`tanker` 297건** — SIPRI 번역이 '유조선'이라 W0401 수상함으로 매핑된다.
   직전 분석에서 tanker 문장의 79.7%가 민간 해운 문맥이었고 군용 급유 문맥은 5.2%였다. 사전 자체를 팀에서 정해야 한다.
2. **부정 표현이 거의 작동하지 않는다** — 사전의 `was not launched` 같은 완성형이 기사 문장과 일치하는 경우가 드물다.
   실제로 흔한 `denied`·`rejected`·`no evidence that` 추가가 필요하다.
3. **인용 단독(`said`) 4,303건은 미발견 처리**했다. 기준을 바꾸려면 `stage2.py`의 `ATTR_TYPES` 분기를 고친다.
4. **기술 매칭이 무기의 10.7%뿐**이다. NATO 용어가 일반 언론에 거의 나오지 않는다.
5. **제조국과 사용국을 구분하지 않는다** ("Iranian-made drones in Ukraine"). 미구현.
6. **매체 편향** — janes.com 본문 0건(유료), nytimes 0건. 확보된 본문은 일반 국제뉴스 매체 중심이다.
   대시보드 설명에 명시해야 한다.
7. **정밀도·재현율 미산출.** 검증셋 200건 라벨링(최소 2명 교차)이 남아 있다.
8. 한 기사에 무기가 여러 개 붙으므로 합계가 기사 수보다 크다. 대시보드 주석 필요.

---

## 9. 깃에 올리지 않는 파일

`.gitignore`에 등록돼 있다. 깃허브는 파일 1개가 50 MiB를 넘으면 경고하고 100 MiB를 넘으면 거부한다
(웹 브라우저 업로드는 25 MiB 제한).

- `bodies.sqlite` (130MB) — **수집 데이터 본체다. 삭제 금지**
- `article_texts.csv` (110MB) — `fetch_bodies.py export`로 2초면 재생성된다
- `out/` 산출물 — 재실행으로 재생성된다
- GDELT 원본 기사 목록 `v1_*`·`v2_*` — 별도 공유

---

## 10. 주의사항

- 출력 CSV를 Excel로 열어둔 채 스크립트를 돌리면 PermissionError가 난다.
- `article_texts.csv`는 `body`에 줄바꿈이 많아 Excel로 열면 깨져 보인다. pandas로 확인할 것.
- 모든 CSV는 `utf-8-sig`로 저장한다 (Excel 한글 깨짐 방지).
- 최종 파일은 전부 **보도일 오름차순**이다. 날짜는 `published_at`, 없으면 GDELT 기록일을 쓰고 `날짜출처` 컬럼에 표시한다.
