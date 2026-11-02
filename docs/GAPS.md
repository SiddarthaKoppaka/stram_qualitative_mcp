# Known gaps

What is missing between the service today and the full vision in [PLANS.md](../PLANS.md). Snapshot of
2026-11-01. Each item is a candidate for later work, not a bug.

| # | Gap | Why it matters | Needs |
|---|---|---|---|
| 1 | Reworded copies | A rewritten headline counts as a new story | Phase 2 embeddings |
| 2 | Real login and private TLS (M6) | The demonstration is not safe to share | Keycloak and staging |
| 3 | Reliable GDELT collection | 70 of the last 30 days' 15-minute slots are empty, and new ones still appear | Pipeline fix |
| 4 | SEC announcement text | 3,936 announcements have only a 500-character summary | Writing the raw archive's text to `bodies/` |
| 5 | Spam that passes `content_farm` | Junk reaches results | Pipeline work |
| 6 | Semantic search | `text` is a plain substring | Phase 2 embeddings |
| 7 | Company-level sentiment | GDELT tone covers whole articles | Phase 2 |
| 8 | Monitoring and alerts | Failures in the demonstration are silent | M6 |
| 9 | Licensing review | Article text belongs to its publishers | Before anyone outside the team gets `qual:text` |

## Not yet proven

- **Connecting from a laptop.** Tests ran on the server itself, not through the SSH tunnel.
- **Surviving a reboot.** The service is set to start with its user session, but no reboot was tested.
- **The `sudo` commands in [Operations](OPERATIONS.md) and removal steps in
  [Deployment](../deploy/README.md#remove-it).** They were written from the setup script, not yet run.
- **The compaction timer.** Its first run is Sunday 2026-11-08. It stops the Parquet sink for a few
  minutes, and restarts it.
- **The M6 checklist** in [Operations](OPERATIONS.md#m6-staging-checklist).

## Limits to keep in mind

- **Some reads miss their budgets at worst.** On the deployed service, the slowest one-month ticker search
  took 4.3 s against 2 s. One-year ticker searches occasionally pass the 10 s deadline: 2 of 72 calls in a
  repeated run. The cause is not known. Re-measure once compaction has run. After three failures in a row,
  the worker stops restarting until the service is restarted.
- **Disk.** Compaction keeps the old Parquet files, about 2.5 GB last time, until someone removes them.
  The removal needs the data owner's approval.
- **One worker.** Queries run one at a time, so a few slow calls delay the rest.
- **Classic CI token.** `STRAM_DATA_READ_TOKEN` is currently a broad classic token. Replace it with a
  read-only token from the `stram_data` owner.
- **Security exception.** PyArrow carries an accepted risk that expires on 2027-01-31; see
  [Security exceptions](SECURITY_EXCEPTIONS.md).
