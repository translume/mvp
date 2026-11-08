# Tumor-board causal synthesis

The complete Docker workflow runs this stage automatically after pathway
analysis. See `README.md` in this directory for runtime settings and output
locations, and the repository-root `README.md` for laptop setup.

The command reads the completed pathway-analysis Markdown and research memo,
loads the bundled synthesis prompt, and sends one bounded Astra Pro Responses
request. It performs no web search and does not manufacture missing clinical
facts. Every request explicitly uses `store=False`; failed or incomplete output
cannot be written as a finished report.

To inspect the command interface from the repository root:

```bash
docker compose exec --user analyzer dynamic-pathway-analyzer \
  python /app/tumor_board_causal_synthesis.py --help
```

The service writes `onco_board_summary.md`,
`onco_board_summary.manifest.json`, and request receipts in `openai_calls/`.
The manifest records source-document hashes, the actual response/model, Pro
mode, effective effort, returned usage, and the completed report's hash.
