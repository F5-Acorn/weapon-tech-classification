-- [01] GDELT 기사 후보 원본 테이블 생성 — 자동 생성 파일, 직접 고치지 말 것 (build_combined_sql.py 재실행)
-- 조회 계획: gdelt_search_plan.json 배치 15개, 공통 기간 2016-01-01 ~ 2026-09-23
-- 후보 조건: 두 행위자 국가코드가 분쟁 양측 교전국(CAMEO) AND 행동 유형(EventRootCode 15·17·18·19·20, QuadClass 4)
-- 처리량: 약 490GB (2026-09-23 실행 기준). 실행 전 편집기의 예상 처리량을 반드시 확인한다.
-- 결과: 사건×기사 후보 1행씩, 2026-09-23 실행 결과 7,126,395행
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.candidates_raw`
OPTIONS (description = "F5 GDELT candidate event-mention rows, dyad(Actor1/2CountryCode) + EventRootCode 15,17-20 + QuadClass 4, 2016-01-01~2026-09-23")
AS
WITH batches AS (
  SELECT * FROM UNNEST([
    STRUCT('ucdp_164_20160101_20260923' AS batch_id, 'ucdp_164' AS candidate_conflict_id, ['USA'] AS side_a, ['VEN'] AS side_b),
    STRUCT('ucdp_218_20160101_20260923' AS batch_id, 'ucdp_218' AS candidate_conflict_id, ['IND'] AS side_a, ['PAK'] AS side_b),
    STRUCT('ucdp_274_20160101_20260923' AS batch_id, 'ucdp_274' AS candidate_conflict_id, ['CHN'] AS side_a, ['IND'] AS side_b),
    STRUCT('ucdp_294_20160101_20260923' AS batch_id, 'ucdp_294' AS candidate_conflict_id, ['KHM'] AS side_a, ['THA'] AS side_b),
    STRUCT('ucdp_302_20160101_20260923' AS batch_id, 'ucdp_302' AS candidate_conflict_id, ['ISR'] AS side_a, ['SYR'] AS side_b),
    STRUCT('ucdp_324_20160101_20260923' AS batch_id, 'ucdp_324' AS candidate_conflict_id, ['IRN'] AS side_a, ['IRQ'] AS side_b),
    STRUCT('ucdp_409_20160101_20260923' AS batch_id, 'ucdp_409' AS candidate_conflict_id, ['ERI'] AS side_a, ['ETH'] AS side_b),
    STRUCT('ucdp_10383_20160101_20260923' AS batch_id, 'ucdp_10383' AS candidate_conflict_id, ['BGD'] AS side_a, ['MMR'] AS side_b),
    STRUCT('ucdp_10771_20160101_20260923' AS batch_id, 'ucdp_10771' AS candidate_conflict_id, ['COD'] AS side_a, ['RWA'] AS side_b),
    STRUCT('ucdp_11639_20160101_20260923' AS batch_id, 'ucdp_11639' AS candidate_conflict_id, ['AFG'] AS side_a, ['PAK'] AS side_b),
    STRUCT('ucdp_13243_20160101_20260923' AS batch_id, 'ucdp_13243' AS candidate_conflict_id, ['RUS'] AS side_a, ['UKR'] AS side_b),
    STRUCT('ucdp_13324_20160101_20260923' AS batch_id, 'ucdp_13324' AS candidate_conflict_id, ['KGZ'] AS side_a, ['TJK'] AS side_b),
    STRUCT('ucdp_14609_20160101_20260923' AS batch_id, 'ucdp_14609' AS candidate_conflict_id, ['IRN'] AS side_a, ['ISR'] AS side_b),
    STRUCT('ucdp_16099_20160101_20260923' AS batch_id, 'ucdp_16099' AS candidate_conflict_id, ['GBR', 'USA'] AS side_a, ['YEM'] AS side_b),
    STRUCT('ucdp_16470_20160101_20260923' AS batch_id, 'ucdp_16470' AS candidate_conflict_id, ['ISR'] AS side_a, ['YEM'] AS side_b)
  ])
), mentions AS (
  SELECT
    GLOBALEVENTID, MentionIdentifier, MentionSourceName, MentionTimeDate,
    Confidence, InRawText, SentenceID, MentionDocTranslationInfo
  FROM `gdelt-bq.gdeltv2.eventmentions_partitioned`
  WHERE _PARTITIONTIME >= TIMESTAMP('2016-01-01')
    AND _PARTITIONTIME < TIMESTAMP('2026-09-24')
    AND MentionTimeDate >= 20160101000000
    AND MentionTimeDate < 20260924000000
    AND MentionType = 1
    AND REGEXP_CONTAINS(MentionIdentifier, r'^https?://')
), events AS (
  SELECT
    GLOBALEVENTID, SQLDATE, DATEADDED, Actor1Name, Actor2Name,
    Actor1CountryCode, Actor2CountryCode, EventCode, EventRootCode, QuadClass,
    ActionGeo_CountryCode, ActionGeo_FullName, ActionGeo_Type,
    ActionGeo_Lat, ActionGeo_Long
  FROM `gdelt-bq.gdeltv2.events_partitioned`
  WHERE _PARTITIONTIME >= TIMESTAMP('2015-02-19')
    AND _PARTITIONTIME < TIMESTAMP('2026-09-24')
    AND EventRootCode IN ('15', '17', '18', '19', '20')
    AND QuadClass = 4
    AND Actor1CountryCode IN UNNEST(['AFG', 'BGD', 'CHN', 'COD', 'ERI', 'ETH', 'GBR', 'IND', 'IRN', 'IRQ', 'ISR', 'KGZ', 'KHM', 'MMR', 'PAK', 'RUS', 'RWA', 'SYR', 'THA', 'TJK', 'UKR', 'USA', 'VEN', 'YEM'])
    AND Actor2CountryCode IN UNNEST(['AFG', 'BGD', 'CHN', 'COD', 'ERI', 'ETH', 'GBR', 'IND', 'IRN', 'IRQ', 'ISR', 'KGZ', 'KHM', 'MMR', 'PAK', 'RUS', 'RWA', 'SYR', 'THA', 'TJK', 'UKR', 'USA', 'VEN', 'YEM'])
), tagged AS (
  SELECT b.batch_id, b.candidate_conflict_id, e.*
  FROM events AS e
  JOIN batches AS b
    ON (e.Actor1CountryCode IN UNNEST(b.side_a) AND e.Actor2CountryCode IN UNNEST(b.side_b))
    OR (e.Actor1CountryCode IN UNNEST(b.side_b) AND e.Actor2CountryCode IN UNNEST(b.side_a))
)
SELECT DISTINCT
  t.*,
  m.MentionIdentifier AS source_url,
  m.MentionSourceName AS source_name,
  m.MentionTimeDate AS gdelt_mention_time,
  m.Confidence AS extraction_confidence,
  m.InRawText, m.SentenceID,
  m.MentionDocTranslationInfo AS translation_info
FROM tagged AS t
JOIN mentions AS m USING (GLOBALEVENTID);
