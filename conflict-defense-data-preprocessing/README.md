# conflict-defense-data-preprocessing

F5팀 「글로벌 공개보도 기반 주요 분쟁의 무기·기술 사용 동향 대시보드」의 **데이터 전처리** 코드입니다.
수집 저장소(`conflict-defense-data-collection`)가 만든 작업 DB의 기사 본문에서 무기·기술 사전 이름이 나오는 문장을 찾고,
규칙으로 **사용(0) / 비사용(1) / 불확실(2)** 을 판정해 대시보드 DB에 올릴 `articles.csv`, `result.csv`를 만듭니다.

## 구성

```text
├── README.md
├── main.py                 실행 (1~4단계, validate, status)
└── preprocessing/
    ├── config.py           config.json 읽기
    ├── common.py           작업 DB 연결·사전 검사·전처리 테이블 생성·CSV 저장
    ├── codes.py            판정 코드 0 사용 / 1 비사용 / 2 불확실, 우선순위
    ├── term_matcher.py     정규화·문장 분리·사전 매칭·단어 경계
    ├── match.py            1단계: 사전 이름이 걸린 문장 저장
    ├── articles.py         2단계: articles 확정 (제목 보완·결측·중복 제외)
    ├── usage_rules.py      무기 언급 타당성·사용 표현 탐지·문장 판정 규칙
    ├── classify.py         3단계: 문장별 사용 판정
    ├── export.py           4단계: 기사×카테고리 우선순위 통합 → result.csv
    └── validate.py         원본·DB·CSV 대조 검증
```

## 실행

Python 3.11 이상. 필요한 패키지: `pyahocorasick==2.3.1`, `pysbd==0.3.4`

```powershell
pip install pyahocorasick==2.3.1 pysbd==0.3.4
```

`config.json` (`input_csv`, `work_dir`는 수집 저장소와 같게)

```json
{
  "input_csv": "data/articles_candidates.csv",
  "sources_dir": "data/sources",
  "work_dir": "work"
}
```

`sources_dir`에는 사전 3종을 UTF-8 CSV로 둡니다.

| 파일 | 필수 컬럼 | 판정에 쓴 규모 |
|---|---|---|
| sipri_dictionary.csv | wp_name, category_id | 4,570개 명칭 · 무기(W코드) |
| nato_dictionary.csv | tech_name, category_id | 115개 명칭 · 기술(T코드) |
| usage_patterns.csv | pattern_id, base_form, trans_form | 215행 · 기본형 77개 |

```powershell
python main.py 1 --config config.json      # 사전 매칭 (수집이 중간에 멈춰 pending이 남았으면 --allow-pending)
python main.py 2 --config config.json      # articles 확정
python main.py 3 --config config.json      # 사용 판정
python main.py 4 --config config.json      # result 생성·검증
python main.py validate --config config.json
```

결과: `work/deliverables/articles.csv`(article_id, conflict_id, published_date, article_url, title), `work/deliverables/result.csv`(article_id, category_id, usage_code, evidence_sentence). UTF-8 BOM CSV, ID는 문자열로 보존합니다.
1단계에서 사전 3종의 SHA-256을 기록하고, 이후 사전이 바뀌면 실행을 멈춥니다. 입력이나 사전을 바꾸면 새 `work_dir`에서 수집부터 다시 합니다.

## 처리 기준

| 단계 | 내용 | 보고서 |
|---|---|---|
| 1 사전 매칭 | NFKC·대시·따옴표·공백·대소문자 정규화, pysbd 문장 분리, Aho-Corasick 매칭, 단어 경계 검사 | 2.2, 3장 |
| 2 articles | 본문 추출에 성공하고 사전 이름이 한 번 이상 나온 기사. 제목은 수집 제목 우선. 5컬럼 중 빈 값이 있으면 제외. 같은 분쟁+정규화 URL+제목+매칭 내용이면 첫 행만 유지 | 1.1 |
| 3 무기 언급 타당성 | 일반 단어와 같은 무기명(Attack, River 등)은 주변 90자 안에 맞는 무기 단어가 있고 대소문자가 같을 때만 인정 | 4장 |
| 3 사용 표현 | 사용 패턴 사전의 기본형·변형, 괄호 주석 제거, 슬래시 대안, 추측어가 든 표현은 불확실 | 5장 |
| 3 문장 판정 | 짧은·숫자 이름, 무기 문맥 없음, 공격 대상인 무기 → 불확실. 절을 나눠 사용 표현 앞 85자의 부정어(비사용)·추측어(불확실)·미래·훈련(비사용), 실제 행동 동사 없음(불확실) 확인 | 6장 |
| 4 집계 | 기사×카테고리마다 사용 → 비사용 → 불확실 순으로 하나만 남기고 그 코드의 문장만 근거로 합침. 판정 코드가 없는 문장은 제외 | 7장 |
| 검증 | 원본 CSV·DB·출력 CSV 재대조, 코드 0/1/2, 우선순위, 사전에 없는 카테고리, 기사 연결, SHA-256 | 8.2 |

판정 규칙은 실제 판정에 쓴 `matching.py`(VERSION 20260923.4)와 같고 코드 숫자만 0/1/2로 바뀌었습니다. 규칙 버전은 3단계 결과(`work/prep3_manifest.json`)에 기록됩니다.

## 작업 DB

수집 저장소가 만든 `work/pipeline.sqlite`(`meta.db_format = "f5-collection-db-v2"`, 테이블 meta·input_rows·pages)를 읽고,
1단계에서 `matched_pages`, `matches`, `selected_articles`, `article_exclusions`, `decisions`, `result_rows`를 같은 DB에 추가합니다.
단계 완료 기록은 수집이 `collect1`·`collect2`, 전처리가 `prep1`~`prep4`라는 이름으로 같은 meta 테이블에 남기며, 수집 2단계가 끝나야 전처리 1단계를 시작할 수 있습니다.
