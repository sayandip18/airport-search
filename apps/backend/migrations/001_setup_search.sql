-- ============================================================
-- Migration: 001_setup_search.sql
--
-- Merged from 001_add_search_indexes.sql + 002_add_aliases_text.sql
--
-- Sets up:
--   • Extensions:      unaccent, pg_trgm
--   • FTS config:      airports_simple  (accent-insensitive, no stemming)
--   • Function:        immutable_unaccent(text)
--   • Columns:         search_vector tsvector, aliases_text text
--   • Trigger:         airports_search_vector_trigger
--                      (maintains both columns on INSERT/UPDATE)
--   • Indexes:
--       airports_search_vector_gin      GIN on search_vector
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
-- 2. Custom FTS configuration: airports_simple
--
-- Clones the built-in "simple" config and prepends the unaccent
-- dictionary so every token is accent-stripped before indexing.
--
--   to_tsvector('airports_simple', 'Düsseldorf') → 'dusseldorf'
--   to_tsvector('airports_simple', 'São Paulo')  → 'sao' 'paulo'
--
-- No stemming or stop-word removal — correct for proper nouns.
-- ----------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'airports_simple'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION airports_simple (COPY = simple);
        ALTER TEXT SEARCH CONFIGURATION airports_simple
            ALTER MAPPING FOR hword, hword_part, word
            WITH unaccent, simple;
    END IF;
END;
$$;


-- ----------------------------------------------------------------
-- 3. Immutable unaccent wrapper
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
-- 4. Add columns
-- ----------------------------------------------------------------
ALTER TABLE airports
    ADD COLUMN IF NOT EXISTS search_vector tsvector;

ALTER TABLE airports
    ADD COLUMN IF NOT EXISTS aliases_text text;


-- ----------------------------------------------------------------
-- 5. Trigger function: airports_search_vector_update
--
-- Rebuilds search_vector and aliases_text before every INSERT or
-- UPDATE using weighted fields:
--
--   A  →  iata_code, icao_code
--          (exact identifiers — highest relevance rank)
--   B  →  name, municipality_name, metro_name, metro_code
--          (primary human-readable names)
--   C  →  country_name, country_code, region_name, region_code
--          (broader geography)
--   D  →  alias names extracted via elem->>'name' from the four
--          JSONB alias arrays
--
-- aliases_text is a flat concatenation of all alias names,
-- used for trigram search so aliases participate in the same
-- ILIKE / word_similarity queries as scalar columns.
-- ----------------------------------------------------------------
CREATE OR REPLACE FUNCTION airports_search_vector_update()
RETURNS trigger AS $$
BEGIN

    -- ---- search_vector ------------------------------------------
    NEW.search_vector :=

        -- A: codes
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.iata_code, '')), 'A') ||
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.icao_code, '')), 'A') ||

        -- B: primary names
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.name, '')), 'B') ||
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.municipality_name, '')), 'B') ||
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.metro_name, '')), 'B') ||
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.metro_code, '')), 'B') ||

        -- C: country / region
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.country_name, '')), 'C') ||
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.country_code, '')), 'C') ||
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.region_name, '')), 'C') ||
        setweight(to_tsvector('airports_simple',
            COALESCE(NEW.region_code, '')), 'C') ||

        -- D: alias names via elem->>'name' (not jsonb_array_elements_text,
        --    which would stringify the whole JSON object)
        setweight(to_tsvector('airports_simple',
            COALESCE((
                SELECT string_agg(elem->>'name', ' ')
                FROM jsonb_array_elements(NEW.municipality_aliases) elem
            ), '')
        ), 'D') ||
        setweight(to_tsvector('airports_simple',
            COALESCE((
                SELECT string_agg(elem->>'name', ' ')
                FROM jsonb_array_elements(NEW.metro_aliases) elem
            ), '')
        ), 'D') ||
        setweight(to_tsvector('airports_simple',
            COALESCE((
                SELECT string_agg(elem->>'name', ' ')
                FROM jsonb_array_elements(NEW.country_alias) elem
            ), '')
        ), 'D') ||
        setweight(to_tsvector('airports_simple',
            COALESCE((
                SELECT string_agg(elem->>'name', ' ')
                FROM jsonb_array_elements(NEW.region_alias) elem
            ), '')
        ), 'D');

    -- ---- aliases_text -------------------------------------------
    -- Flat concatenation of every alias name across all four arrays.
    -- NULL when all alias arrays are empty / have no names.
    NEW.aliases_text := (
        SELECT string_agg(alias_name, ' ')
        FROM (
            SELECT elem->>'name' AS alias_name
            FROM jsonb_array_elements(NEW.municipality_aliases) elem
            UNION ALL
            SELECT elem->>'name'
            FROM jsonb_array_elements(NEW.metro_aliases) elem
            UNION ALL
            SELECT elem->>'name'
            FROM jsonb_array_elements(NEW.country_alias) elem
            UNION ALL
            SELECT elem->>'name'
            FROM jsonb_array_elements(NEW.region_alias) elem
        ) alias_names
        WHERE alias_name IS NOT NULL AND alias_name <> ''
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ----------------------------------------------------------------
-- 6. Attach trigger
-- ----------------------------------------------------------------
DROP TRIGGER IF EXISTS airports_search_vector_trigger ON airports;

CREATE TRIGGER airports_search_vector_trigger
    BEFORE INSERT OR UPDATE ON airports
    FOR EACH ROW EXECUTE FUNCTION airports_search_vector_update();


-- ----------------------------------------------------------------
-- 7. Back-fill existing rows
--
-- Fires the trigger for every row already in the table.
-- No-op if the table is empty (fresh install).
-- ----------------------------------------------------------------
UPDATE airports SET iata_code = iata_code;


-- ================================================================
-- Index creation — must run OUTSIDE a transaction block.
-- ================================================================

-- ----------------------------------------------------------------
-- 8. GIN index on tsvector
--
-- Used by @@ full-text queries:
--   WHERE search_vector @@ plainto_tsquery('airports_simple', 'fra')
-- ----------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS airports_search_vector_gin
    ON airports USING GIN (search_vector);


-- ----------------------------------------------------------------
-- 9. GIN trigram index on accent-normalised scalar names
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
-- 10. GIN trigram index on aliases_text
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
-- DROP INDEX CONCURRENTLY IF EXISTS airports_search_vector_gin;
-- DROP TRIGGER IF EXISTS airports_search_vector_trigger ON airports;
-- DROP FUNCTION IF EXISTS airports_search_vector_update();
-- DROP FUNCTION IF EXISTS immutable_unaccent(text);
-- ALTER TABLE airports DROP COLUMN IF EXISTS aliases_text;
-- ALTER TABLE airports DROP COLUMN IF EXISTS search_vector;
-- DROP TEXT SEARCH CONFIGURATION IF EXISTS airports_simple;
-- -- Leave extensions in place (other objects may depend on them).
