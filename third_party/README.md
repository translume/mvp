# Third-Party Harvard MIMS Repositories

`third_party/upstream/` is reserved for clean, updateable Git clones of the
Harvard MIMS repositories used by Translume:

```text
third_party/upstream/Medea
third_party/upstream/OptimusKG
third_party/upstream/ToolUniverse
```

These folders must contain real `.git` directories for production or demo
validation. Zip-extracted folders are not updateable and do not satisfy the
Translume PRIME_DIRECTIVES.

## Production update workflow

Clone or fast-forward pull every upstream repository:

```bash
make vendor-repos
```

Validate that every repository is an updateable Git checkout:

```bash
make vendor-status
```

The status command fails if a repository is missing, zip-extracted, has the
wrong remote, or has a dirty working tree.

## Manual Git commands

The real update path is ordinary Git:

```bash
git -C third_party/upstream/Medea pull --ff-only
git -C third_party/upstream/OptimusKG pull --ff-only
git -C third_party/upstream/ToolUniverse pull --ff-only
```

After pulling updates, run:

```bash
make vendor-status
make audit-vendor-model-calls
make catalog-vendor-repos
make test
```

## Offline zip bootstrap

Offline zip bootstrap exists only for source inspection when a networked clone is
not possible:

```bash
make vendor-bootstrap-from-zips
```

This command intentionally does **not** satisfy `make vendor-status` because
zip-extracted repositories cannot be updated with `git pull --ff-only`.

## Extension strategy

Do not put Translume production logic inside the Harvard repos. Translume
extends these repositories through ports and adapters:

```text
packages/translume-ports      # stable Translume contracts
packages/translume-adapters   # Translume-owned wrappers/extensions
services/*-service            # isolated runtime service boundaries
```

Patch files under `third_party/patches/` are reserved only for unavoidable
upstream patches.
