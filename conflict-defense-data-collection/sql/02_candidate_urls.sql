-- [02] 기사 URL 단위 요약 테이블 (분쟁 × 기사 URL 1행)
-- 입력: 01_candidates_raw.sql 결과 / 처리량: 약 1.6GB / 2026-09-23 결과: 2,832,396행
--
-- 대표 발생 위치: 한 기사에 연결된 사건들의 발생 위치 중 가장 많이 나온 곳.
--   좌표가 있는 위치를 우선하고, 동률이면 더 이른 사건의 위치를 쓴다.
-- geo_type: 1=국가 중심점(정밀 위치 아님), 2·5=1차 행정구역, 3·4=도시
-- translated: GDELT가 번역한 비영어 원문이면 TRUE
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.candidate_urls`
OPTIONS (description = "F5 URL-level summary of candidates_raw: one row per candidate_conflict_id x source_url, with representative event location (most frequent, coordinates first)")
AS
WITH base AS (
  SELECT
    candidate_conflict_id,
    source_url,
    ANY_VALUE(source_name) AS source_name,
    MIN(gdelt_mention_time) AS first_mention_time,
    MIN(SQLDATE) AS first_event_date,
    MAX(SQLDATE) AS last_event_date,
    COUNT(DISTINCT GLOBALEVENTID) AS event_count,
    STRING_AGG(DISTINCT EventRootCode ORDER BY EventRootCode) AS root_codes,
    MAX(extraction_confidence) AS max_confidence,
    LOGICAL_OR(IFNULL(translation_info, '') != '') AS translated
  FROM `__PROJECT__.__DATASET__.candidates_raw`
  GROUP BY candidate_conflict_id, source_url
), loc AS (
  SELECT
    candidate_conflict_id, source_url,
    ActionGeo_CountryCode, ActionGeo_FullName, ActionGeo_Type, ActionGeo_Lat, ActionGeo_Long,
    COUNT(DISTINCT GLOBALEVENTID) AS n,
    MIN(SQLDATE) AS d
  FROM `__PROJECT__.__DATASET__.candidates_raw`
  GROUP BY 1, 2, 3, 4, 5, 6, 7
), top_loc AS (
  SELECT
    candidate_conflict_id, source_url,
    ARRAY_AGG(STRUCT(
      ActionGeo_CountryCode AS geo_country_code,
      ActionGeo_FullName AS geo_fullname,
      ActionGeo_Type AS geo_type,
      ActionGeo_Lat AS geo_lat,
      ActionGeo_Long AS geo_long
    ) ORDER BY ActionGeo_Lat IS NULL, n DESC, d LIMIT 1)[OFFSET(0)] AS g,
    COUNT(*) AS location_count
  FROM loc
  GROUP BY candidate_conflict_id, source_url
)
SELECT
  b.*,
  t.g.geo_country_code, t.g.geo_fullname, t.g.geo_type, t.g.geo_lat, t.g.geo_long,
  t.location_count
FROM base AS b
JOIN top_loc AS t USING (candidate_conflict_id, source_url);
