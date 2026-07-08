# MIMS return-signature audit

Use the audit CLI to print the expected return signatures for third-party MIMS boundaries without calling external services:

```bash
python scripts/audit_mims_return_signatures.py
python scripts/audit_mims_return_signatures.py --format json
```

The CLI reports the return models for OptimusKG, ToolUniverse, and Medea service clients. This helps audit what the backend expects from `/context`, `/workflows`, and `/reason` before clinical artifacts are generated.
