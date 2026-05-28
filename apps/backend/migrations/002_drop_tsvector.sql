-- ============================================================
-- Migration: 002_drop_tsvector.sql
--
-- Removes all tsvector / FTS infrastructure that is no longer
-- used by the search layer (trigram-only since 001).
--
-- Drops:
--   • Index:    airports_search_vector_gin
--   • Trigger:  airports_search_vector_trigger
--   • Function: airports_search_vector_update()
--   • Column:   airports.search_vector
--   • FTS config: airports_simple
--
-- Keeps everything else: unaccent, pg_trgm, immutable_unaccent,
-- aliases_text, airports_trigram_gin, airports_aliases_trigram_gin.
--
-- Apply:
--   psql $DATABASE_URL -f migrations/002_drop_tsvector.sql
--
-- NOTE: DROP INDEX CONCURRENTLY cannot run inside a transaction.
-- Run this script directly via psql (not wrapped in BEGIN).
-- ============================================================

DROP INDEX CONCURRENTLY IF EXISTS airports_search_vector_gin;

DROP TRIGGER IF EXISTS airports_search_vector_trigger ON airports;

DROP FUNCTION IF EXISTS airports_search_vector_update();

ALTER TABLE airports DROP COLUMN IF EXISTS search_vector;

DROP TEXT SEARCH CONFIGURATION IF EXISTS airports_simple;
