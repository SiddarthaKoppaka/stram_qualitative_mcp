# Deployment

What the scripts in [`deploy/`](../../deploy/) create on the host, and where. The steps are in
[Deploy the service](../how-to/deploy-the-service.md).

## Scripts

| Script | Runs as | Does |
|---|---|---|
| `build_image.sh` | The lake's owner | Builds the image, checks worker isolation, saves it to a tar file |
| `setup_host.sh` | root | Creates or updates the service user, mounts, audit volume, key and units, then starts the service |
| `m6_evidence.sh` | root | Gathers host evidence and backs up the audit journal; see [Check staging](../how-to/check-staging.md) |
| `install_compaction_timer.sh` | The lake's owner | Installs the Parquet compaction timer |
| `issue_demo_token.py` | Anyone | Makes a demo signing key and a one-hour token |
| `staging.env.example` | | The shape of the staging settings file |

## What gets created

| Item | Why |
|---|---|
| Non-login user `stram-qual` | Separates the service from the account that writes the lake |
| Read-only mounts under `/srv/stram-qual/news/` | Gives it `parquet` and `bodies` only, never the raw archive |
| Podman volume `stram-qual-audit` | Holds the audit journal |
| Podman secret `stram-qual-audit-key` | Signs the audit journal |
| Pod `stram-qual`, publishing `127.0.0.1:8801` | The service. Demo mode adds a small server for its public signing key |
| `~stram-qual/.config/stram-qual/service.env` | The service's settings, mode 0600 |
| `~stram-qual/.config/containers/systemd/` | The Quadlet units |
| `/etc/stram-qual/staging.env` | Staging settings, written by an administrator |
| `/var/backups/stram-qual/` | Audit backups, keys and checkpoints from `m6_evidence.sh`, root only |
| Tailscale Serve entry on port 8443 | Private HTTPS on the tailnet, added by an administrator |

## Units

| Unit | Mode | Notes |
|---|---|---|
| `stram-qual-pod.service` | Both | Start it first; stopping the service stops it |
| `stram-qual-mcp.service` | Both | The service; memory capped at 5 GB |
| `stram-qual-jwks.service` | Demo only | Serves the demo public key on the pod's loopback |
| `srv-stram\x2dqual-news-parquet.mount`, `...-bodies.mount` | Both | Read-only bind mounts |
