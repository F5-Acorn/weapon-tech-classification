-- [03] ERD articles 형식으로 조회 → 결과를 구글드라이브 CSV로 내보낸다 (결과 저장 > CSV(Google Drive))
-- 입력: 02_candidate_urls.sql 결과 / 처리량: 약 0.2GB / 2026-09-23 결과: 2,832,396행 (드라이브 F5_ERD_적재용_20260923/articles.csv)
--
-- article_id: FARM_FINGERPRINT(conflict_id|url)의 양수 63비트 → 재실행해도 같은 값. 충돌 0 확인.
--             같은 URL이 여러 분쟁 후보에 걸리면 분쟁마다 다른 ID (ERD: 기사 1행 = 분쟁 1개)
-- published_date: 임시값. GDELT가 이 URL을 처음 수집한 날짜. 본문 수집 후 실제 발행일로 교체한다.
-- title: 본문 수집(또는 04_gkg_titles.sql) 후 채운다.
SELECT
  FARM_FINGERPRINT(CONCAT(candidate_conflict_id, '|', source_url)) & 0x7FFFFFFFFFFFFFFF AS article_id,
  candidate_conflict_id AS conflict_id,
  PARSE_DATE('%Y%m%d', SUBSTR(CAST(first_mention_time AS STRING), 1, 8)) AS published_date,
  source_url AS article_url,
  CAST(NULL AS STRING) AS title
FROM `__PROJECT__.__DATASET__.candidate_urls`
ORDER BY conflict_id, published_date, article_url;
