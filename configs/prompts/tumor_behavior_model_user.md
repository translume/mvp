Generate TumorBehaviorModelOutput for the Translume MVP.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Use only these state labels when supported by evidence or explicit missing-evidence reasoning:
- proliferative
- stress_adapted_survival
- plastic_dedifferentiated
- dormant_quiescent
- apoptotic_eliminated

Rules:
- State evidence must cite supporting finding IDs, graph node/edge IDs, ToolUniverse artifact IDs, Medea evidence, or explicit missing/speculative evidence.
- Transition hypotheses must cite supporting artifacts from the payload.
- Transition rationales must mention case-derived evidence terms from the payload.
- Do not generate transition probabilities.
- Do not generate treatment recommendations.
- Do not generate outcome predictions.
- If evidence does not support a transition, omit that transition or mark the missing evidence in limitations.
