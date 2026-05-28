-- ============================================================
-- Migration: 003_add_region_to_trigram_index.sql
--
-- Rebuilds airports_trigram_gin to include region_name so that
-- searches like "California" or "Ontario" match via region.
--
-- Apply:
--   psql $DATABASE_URL -f migrations/003_add_region_to_trigram_index.sql
--
-- NOTE: DROP/CREATE INDEX CONCURRENTLY cannot run inside a
-- transaction block. Run directly via psql.
-- ============================================================

DROP INDEX CONCURRENTLY IF EXISTS airports_trigram_gin;

CREATE INDEX CONCURRENTLY airports_trigram_gin
    ON airports USING GIN (
        immutable_unaccent(
            COALESCE(name,              '') || ' ' ||
            COALESCE(municipality_name, '') || ' ' ||
            COALESCE(metro_name,        '') || ' ' ||
            COALESCE(country_name,      '') || ' ' ||
            COALESCE(region_name,       '') || ' ' ||
            COALESCE(iata_code,         '') || ' ' ||
            COALESCE(icao_code,         '')
        ) gin_trgm_ops
    );


-- ================================================================
-- ROLLBACK (run manually if needed)
-- ================================================================
-- DROP INDEX CONCURRENTLY IF EXISTS airports_trigram_gin;
-- CREATE INDEX CONCURRENTLY airports_trigram_gin
--     ON airports USING GIN (
--         immutable_unaccent(
--             COALESCE(name,              '') || ' ' ||
--             COALESCE(municipality_name, '') || ' ' ||
--             COALESCE(metro_name,        '') || ' ' ||
--             COALESCE(country_name,      '') || ' ' ||
--             COALESCE(iata_code,         '') || ' ' ||
--             COALESCE(icao_code,         '')
--         ) gin_trgm_ops
--     );
