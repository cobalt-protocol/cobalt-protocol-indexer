-- SQLModel create_all() does not alter existing tables, run this manually once.
BEGIN;

ALTER TABLE price_competition
    DROP CONSTRAINT IF EXISTS price_competition_price_competition_fee_id_key;

ALTER TABLE price_competition
    ADD CONSTRAINT uq_price_competition_fee_id_indexer_state
    UNIQUE (price_competition_fee_id, indexer_state_id);

COMMIT;
