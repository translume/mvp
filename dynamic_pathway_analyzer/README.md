# Dynamic Pathway Analyzer

This utility reads an arbitrary precision-oncology JSON file and produces a unique,
case-specific pathway report.

## What it does

1. Recursively finds disease context, molecular findings, trials, sources,
   hypotheses, and assay limitations without depending on one exact JSON schema.
2. Normalizes the patient evidence with an OpenAI structured-output call.
3. Dynamically groups findings into pathways.
4. Creates focused research questions for each pathway.
5. Uses two moderately thorough OpenAI Responses API `web_search` calls across
   the highest-priority pathways: one authoritative medical/registry search and
   one unrestricted open-web search for distinctive translational evidence.
6. Returns:
   - simplified pathway descriptions;
   - therapeutic strategies to investigate;
   - potential synthetic-lethal and combination paths;
   - DNA repair/recombination interactions where relevant;
   - bypass and resistance pathways;
   - confirmation requirements;
   - evidence tiers and source URLs;
   - a clinician-facing Markdown report and structured JSON.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export OPENAI_API_KEY="sk-proj-..."
```

Do not put the real key in source code, Git, logs, or generated reports.

## Command-line usage

```text
usage: dynamic_pathway_analyzer.py [-h]
                                   [--output-dir OUTPUT_DIR]
                                   [--model MODEL]
                                   [--normalizer-model NORMALIZER_MODEL]
                                   --diagnosis DIAGNOSIS
                                   input_json
```

### Required arguments

- `input_json`: path to the oncology JSON file to analyze.
- `--diagnosis DIAGNOSIS`: user-defined diagnosis used as population context in
  every model prompt.

### Optional arguments

- `--output-dir OUTPUT_DIR`: output directory; defaults to `./pathway_output`.
- `--model MODEL`: model used for research and final synthesis; defaults to
  `OPENAI_MODEL`, then `gpt-5.6`.
- `--normalizer-model MODEL`: model used for case normalization and pathway
  construction; defaults to `OPENAI_NORMALIZER_MODEL`, then the main model.
- `-h`, `--help`: print the built-in command reference.

## Run

```bash
python dynamic_pathway_analyzer.py \
  state_after_trial_prescreens.json \
  --diagnosis "dedifferentiated chondrosarcoma" \
  --output-dir pathway_output
```

Complete example with explicit models:

```bash
python dynamic_pathway_analyzer.py \
  state_after_trial_prescreens.json \
  --diagnosis "dedifferentiated chondrosarcoma" \
  --output-dir pathway_output_hybrid \
  --model gpt-5.6 \
  --normalizer-model gpt-5.6
```

Optional model configuration:

```bash
export OPENAI_MODEL="gpt-5.6"
export OPENAI_NORMALIZER_MODEL="gpt-5.6"
```

Additional environment controls:

```bash
export MAX_JSON_CHARS=180000
export MAX_FINDINGS=80
export MAX_SOURCE_RECORDS=40
export MAX_RESEARCH_PATHWAYS=5
```

For a faster, narrower run:

```bash
export MAX_RESEARCH_PATHWAYS=3

python dynamic_pathway_analyzer.py \
  state_after_trial_prescreens.json \
  --diagnosis "dedifferentiated chondrosarcoma" \
  --output-dir pathway_output_fast
```

The required `--diagnosis` value is prepended to every model prompt as:

```text
Diagnosis: <user-defined value>
```

It is prompt context only; the script does not force-write it into the
normalized case object.

The analyzer prints progress for normalization, research, and final synthesis.
The default workflow makes four sequential model operations:

1. normalize the input case;
2. search authoritative medical and registry sources;
3. search the unrestricted web for distinctive translational evidence;
4. compile the final structured report.

Runtime depends on model load, web-search latency, and retries. Avoid starting
multiple copies against the same case unless concurrent paid API calls are
intentional.

## Files created

- `*.normalized_case_map.json`: patient findings and dynamically inferred pathway map.
- `*.research_memo.md`: web-grounded evidence memo.
- `*.research_sources.json`: complete audited URLs consulted by web search.
- `*.pathway_analysis.json`: final structured report.
- `*.pathway_analysis.md`: final clinician-facing narrative.

Use a new output directory for materially different diagnoses or settings so
older results are not confused with the latest run.

## Important behavior

The analyzer does not trust existing model-generated treatment rankings in the
input. It extracts source findings and supporting context, then rebuilds the
pathway analysis.

It distinguishes:

- RNA underexpression;
- DNA copy-number loss;
- heterozygous loss;
- homozygous/biallelic deletion;
- protein loss;
- functional pathway loss.

Potential combinations and recombination-pathway interactions are returned as
hypotheses, not treatment recommendations.

Web discovery is not restricted to government sites. The analyzer can inspect
primary journals, conference publications, academic sites, translational and
metabolomics commentary, medical news, and sponsor research. Non-primary
sources may explain mechanisms or surface research leads, but cannot establish
efficacy, approval, standard care, or patient-specific eligibility by themselves.

The default research pass is intentionally bounded: up to five pathways, up to
three prepared queries per pathway, 6–10 authoritative sources, and 3–6
distinctive open-web sources.
Set `MAX_RESEARCH_PATHWAYS` in the environment to lower the pathway count further.

## Search and evidence boundaries

The authoritative lane searches sources such as trial registries, PubMed/PMC,
NCBI, FDA, NCI, EMA, and WHO. The open-web lane can discover journal-publisher
pages, academic research, conference publications, biotechnology research,
metabolomics or translational commentary, medical news, and sponsor material.

Evidence from a cancer type unrelated to `--diagnosis` may be retained as
indirect mechanism, resistance, safety, or negative evidence. It must not be
presented as diagnosis-matched actionability unless separate disease-matched,
tumor-agnostic, guideline, regulatory, or trial evidence supports that role.

## Clinical boundary

This program produces educational precision-oncology research support. It does
not recommend treatment or determine clinical-trial eligibility. Findings,
sources, assay interpretations, and trial status require review by qualified
clinicians and molecular-pathology professionals.

## No-web tumor-board causal synthesis

`tumor_board_causal_synthesis.py` creates a second-stage Molecular Tumor Board
Causal Summary and Adaptive Action Plan from an existing pathway-analysis
Markdown file and research memo. It performs one model call and supplies no web
search tool; the two Markdown documents are its complete evidence boundary.

```bash
python tumor_board_causal_synthesis.py \
  --pathway-analysis pathway_output/state_after_trial_prescreens.pathway_analysis.md \
  --research-memo pathway_output/state_after_trial_prescreens.research_memo.md \
  --diagnosis "dedifferentiated chondrosarcoma" \
  --output-dir tumor_board_output
```

The script looks for `tumor_board_causal_synthesis_prompt.md` beside the Python
file. Until that file is placed there, it can use the originally supplied prompt
attachment. A prompt can always be selected explicitly:

```bash
python tumor_board_causal_synthesis.py \
  --pathway-analysis pathway_output/state_after_trial_prescreens.pathway_analysis.md \
  --research-memo pathway_output/state_after_trial_prescreens.research_memo.md \
  --diagnosis "dedifferentiated chondrosarcoma" \
  --system-prompt /path/to/tumor_board_prompt.md \
  --output-dir tumor_board_output
```

Outputs:

- `onco_board_summar.md`: clinician-facing report.
- `onco_board_summar.manifest.json`: model, prompt, input
  hashes, usage, and evidence-boundary audit metadata.

---

For this specific case, use:

```
MAX_JSON_CHARS = int(os.getenv("MAX_JSON_CHARS", "180000"))
MAX_FINDINGS = int(os.getenv("MAX_FINDINGS", "40"))
MAX_SOURCE_RECORDS = int(os.getenv("MAX_SOURCE_RECORDS", "40"))
MAX_RESEARCH_PATHWAYS = int(os.getenv("MAX_RESEARCH_PATHWAYS", "5"))
```

Why:

 - The extracted research payload is only about 57,000 characters, so increasing MAX_JSON_CHARS above 180,000 provides no benefit.

 - The analyzer finds 24 findings, so MAX_FINDINGS=40 retains all of them.

 - It finds 19 source records, so MAX_SOURCE_RECORDS=40 retains all sources.

 - MAX_RESEARCH_PATHWAYS is the only setting currently limiting comprehensiveness. Raising it from 3 to 5 captures more biology without increasing the number of API calls—the pathways remain batched into the same two searches.

Recommended environment configuration:

```
export MAX_JSON_CHARS=180000
export MAX_FINDINGS=40
export MAX_SOURCE_RECORDS=40
export MAX_RESEARCH_PATHWAYS=5
```

Then:

```
dynamic_pathway_analyzer.py \
  ../state_after_trial_prescreens.json \
  --diagnosis "dedifferentiated chondrosarcoma" \
  --output-dir pathway_output_comprehensive
```

Profiles:

| Goal | Pathways |
|---|---:|
| Faster, focused | 3 |
| Comprehensive under ~20 minutes | 5 |
| Very broad, potentially slower | 7 |
| Exhaustive and likely too slow/noisy | 10 |


Five is the best balance. The workflow still makes four sequential API operations, so no setting can guarantee completion under 20 minutes during API congestion or retries, but these values should normally stay within that target while retaining all currently discovered findings and sources.
