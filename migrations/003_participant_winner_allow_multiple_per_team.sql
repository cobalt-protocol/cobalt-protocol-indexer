-- SQLModel create_all() does not alter existing tables, run this manually once if needed.
BEGIN;

ALTER TABLE participant_winner DROP CONSTRAINT IF EXISTS ix_participant_winner_team_id;
ALTER TABLE participant_winner DROP CONSTRAINT IF EXISTS participant_winner_team_id_key;
DROP INDEX IF EXISTS ix_participant_winner_team_id;
CREATE INDEX IF NOT EXISTS ix_participant_winner_team_id ON participant_winner (team_id);

COMMIT;

