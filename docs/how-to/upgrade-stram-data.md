# How to move to a new `stram_data` release

The service pins one exact `stram_data` commit and checks its version at startup, so an upgrade
touches several files. Do it in one change.

1. Update the commit in `pyproject.toml`, `.github/workflows/ci.yml` and
   `tools/prepare_container_dependency.sh`.
2. Update the expected version in `worker.py` (`EXPECTED_STRAM_DATA_VERSION`), the `Dockerfile` and
   `tools/prepare_container_dependency.sh`.
3. Add the new Data Interface snapshot to `contracts/`, and point
   `tests/contract/test_data_interface_release.py` at it.
4. Refresh the lock:

   ```bash
   uv lock --upgrade-package stram-data
   ```

5. Run the [quality gates](run-the-quality-gates.md), then rebuild and redeploy the image; see
   [Deploy the service](deploy-the-service.md).
