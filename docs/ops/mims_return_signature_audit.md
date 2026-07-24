# Auditing MIMS Provider Return Signatures

Use the CLI below to print the expected return contracts for the three MIMS provider boundaries without calling external services:

```bash
python scripts/print_mims_return_signatures.py
python scripts/print_mims_return_signatures.py --json
```

The command prints the expected return schemas for OptimusKG (`GraphEvidenceArtifact`), ToolUniverse (`list[ToolRunArtifact]`), and Medea (`MedeaReasoningArtifact`). Compare live REST responses to these contracts before letting the outputs feed the clinician-facing decision brief.
