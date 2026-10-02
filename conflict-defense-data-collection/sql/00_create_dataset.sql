-- [00] 결과를 저장할 데이터셋 생성 (처리량 0)
-- GDELT 공개 데이터(gdelt-bq)가 US 리전에 있어서 같은 US 위치로 만든다.
-- 샌드박스 프로젝트에서는 테이블이 생성 후 60일 뒤 자동 삭제된다.
CREATE SCHEMA IF NOT EXISTS `__PROJECT__.__DATASET__`
OPTIONS (
  location = 'US',
  description = 'F5 GDELT candidate articles for UCDP interstate conflicts 2016-01-01~2026-09-23'
);
