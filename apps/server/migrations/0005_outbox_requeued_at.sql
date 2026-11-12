-- Personal Zalo channel: when staff requeue a failed / unknown outbox row (POST /staff/outbox/:id/decide), the
-- bridge must send it again even though its local send journal already holds an outcome for that id. The claim
-- item carries requeued_at so the bridge can tell a staff requeue from a redelivery of the same claim.
ALTER TABLE outbox ADD COLUMN requeued_at INTEGER;
