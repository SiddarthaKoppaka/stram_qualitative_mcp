# Staging checklist

The conditions for M6. Staging serves the team on the tailnet; it must not serve anyone outside the
team until every item has an owner and evidence in [PLANS.md](../../PLANS.md).
[Check staging](../how-to/check-staging.md) gathers most of the evidence.

| Item | Status | Evidence or what remains |
|---|---|---|
| Image pinned by digest, with SBOM, provenance, vulnerability report and a rollback digest | Open | Image IDs are recorded (`m7` `704e592d0d06`, `m5` `65667b7857c9`) and CI builds an SBOM and scans; the deployed image is built on the host, without provenance |
| Keycloak client with exact issuer, audience, tenant claim and least scopes; missing, forged, expired, wrong-audience, wrong-tenant and wrong-scope tokens all fail | Done | Missing, forged and wrong-scope tokens fail through the tailnet; the others in tests; the realm check confirmed audience isolation |
| Private TLS, with exact Host and Origin rules | Done | Tailscale Serve on 8443; wrong Host 421, foreign Origin 403 |
| Host firewall allowing outbound traffic only to the issuer, JWKS and approved telemetry | Open | To plan with the Quant owner, because the host is shared |
| Unprivileged host and in-container writes to the lake both fail | Done | `m6_evidence.sh` |
| `/proc` shows the seccomp filter on the query worker during a real call | Done | `m6_evidence.sh` |
| Audit backup, independent verification, external checkpoint and a restore drill | Done | `m6_evidence.sh`; the backup is still on the same disk |
| Agreed retention | Open | Proposal: 90 days online, one year archived. The Quant MCP keeps 30 days of backups |
| Overload, deadline, worker crash, restart limit and graceful shutdown exercised | Done | `m6_evidence.sh`, an overload test, and the 2026-11-03 article timeouts |
| Dashboards, alerts and owners, with telemetry redaction checked | Open | No monitoring system yet |
| Rollback to the previous release restores readiness without touching the lake or journal | Done | 2026-11-04: `m7` to `m5` and back, checked each way; the images are local tags, not reviewed digests |
| Licensing checked before anyone outside the team gets `qual:text` | Open | Needs an owner |
