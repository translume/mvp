# Verified Harvard MIMS source snapshots

The application uses the original bundled Medea, OptimusKG, and ToolUniverse source archives. Their SHA-256 identities are pinned in `vendor_archives.lock.json`. Docker installs them through `scripts/install_packaged_vendors.py` into `third_party/upstream/` and validates all installed source bytes against the locked archives. Unsafe paths, escaping links, modified files, missing files, and unexpected source files fail verification.

These are immutable source snapshots, not fabricated Git checkouts. The archive contents remain unchanged. Application-owned OpenAI wrappers live under `packages/` and `services/`; no upstream model dependency tree is installed.

To check installed sources in the running application:

```sh
docker compose exec translume-api python -c "from pathlib import Path; from translume_core.vendor.packaged import require_packaged_vendor_sources; require_packaged_vendor_sources(Path('/app')); print('Verified bundled sources')"
```

To intentionally update a vendor, obtain and review the actual new upstream archive, update its lock identity and wrapper compatibility, then rerun the application tests and real integration check. Do not edit a locked extracted source tree or manufacture Git metadata to pass validation.
