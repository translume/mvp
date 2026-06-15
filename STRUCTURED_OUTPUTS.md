# Structured Outputs

All model-generated clinical artifacts must be generated through local vLLM structured outputs and validated against Pydantic schemas before use.

The vLLM service must be started with:

```bash
--structured-outputs-config.backend=auto
```

Remote model APIs are blocked by default in private MVP mode.
