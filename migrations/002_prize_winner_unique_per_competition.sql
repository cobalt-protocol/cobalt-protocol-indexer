-- SQLModel create_all() does not alter existing tables, run this manually once.
-- winner_id is a per-contract counter, so it must only be unique per competition.
BEGIN;

-- 1. participant_winner FK depends on the old global unique on prize_winner.winner_id
ALTER TABLE participant_winner
    DROP CONSTRAINT IF EXISTS participant_winner_prize_winner_id_fkey;

-- 2. drop global uniqueness on prize_winner.winner_id
ALTER TABLE prize_winner DROP CONSTRAINT IF EXISTS prize_winner_winner_id_key;
ALTER TABLE prize_winner DROP CONSTRAINT IF EXISTS uq_prize_winner_winner_id;
DROP INDEX IF EXISTS ix_prize_winner_winner_id;
CREATE INDEX ix_prize_winner_winner_id ON prize_winner (winner_id);

-- 3. unique per competition
ALTER TABLE prize_winner
    ADD CONSTRAINT uq_prize_winner_competition_winner UNIQUE (competition_id, winner_id);

-- 4. composite FK (NULL prize_winner_id is not checked, MATCH SIMPLE)
ALTER TABLE participant_winner
    ADD CONSTRAINT fk_participant_winner_prize_winner
    FOREIGN KEY (competition_id, prize_winner_id)
    REFERENCES prize_winner (competition_id, winner_id);

COMMIT;
