-- ============================================================
-- Migration: 001_setup_search.sql
--
-- Sets up:
--   • Extensions:      unaccent, pg_trgm
--   • Function:        immutable_unaccent(text)
--   • Column:          aliases_text text
--   • Indexes:
--       airports_trigram_gin            GIN trigram on scalar name columns
--       airports_aliases_trigram_gin    GIN trigram on aliases_text
--
-- Apply:
--   psql $DATABASE_URL -f migrations/001_setup_search.sql
--
-- NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction
-- block. Run this script directly via psql (not wrapped in BEGIN).
-- If your migration runner always wraps in a transaction, replace
-- CONCURRENTLY with nothing — the lock will be held longer but the
-- script will succeed.
--
-- Rollback: see bottom of file.
-- ============================================================


-- ----------------------------------------------------------------
-- 1. Extensions
-- ----------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- ----------------------------------------------------------------
-- 2. Immutable unaccent wrapper
--
-- The built-in unaccent() is declared STABLE, which PostgreSQL
-- forbids in expression indexes. This thin SQL wrapper re-declares
-- it as IMMUTABLE — safe because unaccent dictionary data never
-- changes at runtime (a well-known, standard pattern).
-- ----------------------------------------------------------------
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text AS $$
    SELECT public.unaccent($1)
$$ LANGUAGE SQL IMMUTABLE PARALLEL SAFE;


-- ----------------------------------------------------------------
-- 3. Add aliases_text column
-- ----------------------------------------------------------------
ALTER TABLE airports
    ADD COLUMN IF NOT EXISTS aliases_text text;


-- ================================================================
-- Index creation — must run OUTSIDE a transaction block.
-- ================================================================

-- ----------------------------------------------------------------
-- 4. GIN trigram index on accent-normalised scalar names
--
-- Used by similarity / ILIKE queries for typo tolerance:
--   WHERE immutable_unaccent(name || ' ' || ...) ILIKE '%dusseldorf%'
--   WHERE similarity(immutable_unaccent(name), 'heathrow') > 0.3
-- ----------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS airports_trigram_gin
    ON airports USING GIN (
        immutable_unaccent(
            COALESCE(name,              '') || ' ' ||
            COALESCE(municipality_name, '') || ' ' ||
            COALESCE(metro_name,        '') || ' ' ||
            COALESCE(country_name,      '') || ' ' ||
            COALESCE(iata_code,         '') || ' ' ||
            COALESCE(icao_code,         '')
        ) gin_trgm_ops
    );


-- ----------------------------------------------------------------
-- 5. GIN trigram index on aliases_text
--
-- Mirrors airports_trigram_gin but covers alias names.
-- Used by:
--   WHERE immutable_unaccent(COALESCE(aliases_text,'')) ILIKE '%q%'
--   WHERE word_similarity(:q, immutable_unaccent(COALESCE(aliases_text,''))) > 0.4
-- ----------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS airports_aliases_trigram_gin
    ON airports USING GIN (
        immutable_unaccent(COALESCE(aliases_text, '')) gin_trgm_ops
    );


-- ================================================================
-- ROLLBACK (run manually if needed)
-- ================================================================
-- DROP INDEX CONCURRENTLY IF EXISTS airports_aliases_trigram_gin;
-- DROP INDEX CONCURRENTLY IF EXISTS airports_trigram_gin;
-- DROP FUNCTION IF EXISTS immutable_unaccent(text);
-- ALTER TABLE airports DROP COLUMN IF EXISTS aliases_text;
-- -- Leave extensions in place (other objects may depend on them).
