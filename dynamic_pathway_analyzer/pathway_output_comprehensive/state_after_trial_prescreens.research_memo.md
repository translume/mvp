# Moderately thorough hybrid pathway research

## Authoritative medical and trial research

# Precision-oncology research memo  
**Diagnosis:** Dedifferentiated chondrosarcoma, chest-wall specimen  
**Report date:** June 5, 2024  
**Interpretive constraint:** Stage, resectability, recurrence/metastatic status, prior therapy, performance status, measurable disease, and biopsy feasibility are unavailable. Accordingly, trial eligibility and treatment applicability cannot be established.

## Executive interpretation

1. **MTAP is the most clinically developed pathway in this case**, but the present DNA copy-loss plus RNA-underexpression result is insufficient to establish the biomarker used by most trials. Confirm homozygous/biallelic deletion or complete tumor-cell protein loss before treating the finding as actionable.
2. **The 9p21 findings are biologically plausible in dedifferentiated chondrosarcoma**, but MTAP, CDKN2A, and CDKN2B must be resolved independently. Regional proximity does not prove co-deletion.
3. **CHEK2 c.846+4_846+7del has strong evidence for abnormal splicing and loss of function in the germline setting.** Tumor-only detection does not determine germline origin, clonality, zygosity, or a second hit. CHEK2 alone should not be equated with homologous-recombination deficiency or PARP-inhibitor sensitivity.
4. **AKT2 RNA overexpression and low-confidence LYN gain remain exploratory.** Neither establishes kinase activation, and no disease-matched clinical role was identified for targeting either alteration.

---

## 1. MTAP-associated methionine-salvage/PRMT5 vulnerability

### Disease fit and mechanism

A recent disease-specific genomic series found MTAP alterations in **6 of 31 dedifferentiated chondrosarcomas (19%)**, alongside frequent CDKN2A and CDKN2B alterations. This establishes that MTAP loss occurs in this histology, but not that every copy-loss call is homozygous or functionally null. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/?utm_source=openai))

Mechanistically, complete MTAP loss prevents normal metabolism of methylthioadenosine, or MTA. MTA accumulation partially suppresses PRMT5 activity, creating a hypomorphic PRMT5 state and increased dependency on residual PRMT5/WDR77 function. Experimental correlates include increased intracellular MTA and reduced symmetric dimethylarginine, or SDMA, methylation. The dependency was enriched—but not universal—among MTAP-null models. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC4997612/?utm_source=openai))

MTA-cooperative PRMT5 inhibitors such as anvumetostat/AMG 193 and TNG908 are designed to preferentially inhibit the PRMT5–MTA complex. Early anvumetostat work reported pharmacologic activity in MTAP-deleted models and initial patients across several cancer lineages, but this is pan-cancer evidence rather than dedifferentiated-chondrosarcoma efficacy. ([pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov/39282709/?utm_source=openai))

### Patient-specific interpretation

**Mechanism value: moderate-to-high if functional MTAP-null status is confirmed.**

Current evidence is supportive but incomplete:

- DNA copy-number loss does not distinguish heterozygous from homozygous deletion without allele-specific or purity-adjusted data.
- RNA underexpression can be caused by deletion, transcriptional regulation, specimen composition, or subclonality.
- Neither result proves absent MTAP protein in the dedifferentiated tumor cells.
- Tumor MTA or MTA:SAM measurement is mechanistically informative, but is not a routine validated companion diagnostic. Moreover, metabolite behavior in intact tumors may differ from cultured MTAP-null cells. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC8270912/?utm_source=openai))

### Trial findings

#### NCT05094336 — anvumetostat/AMG 193, MTAPESTRY 101

The current registry record lists this study as **active, not recruiting**, with the status last verified in March 2026. It accepts advanced solid tumors with evidence of homozygous CDKN2A loss and/or MTAP-null status or lost MTAP expression, depending on study part. General requirements include metastatic or locally advanced disease not amenable to curative surgery/radiation, measurable disease for most parts, ECOG 0–1, adequate organ function, and available archival tissue; some parts require biopsies. Dedifferentiated chondrosarcoma is not a dedicated efficacy cohort. ([clinicaltrials.gov](https://clinicaltrials.gov/study/NCT05094336?cond=NCT05094336&utm_source=openai))

**Implication:** The reported DNA loss plus RNA underexpression might not satisfy screening without documentation of homozygous loss or accepted evidence of absent MTAP expression. This study is not presently open to new enrollment according to the current record.

#### NCT05275478 — TNG908

The registry specifies:

- Locally advanced, metastatic, or unresectable solid tumor.
- Prior standard therapy as available.
- **Documented biallelic/homozygous MTAP deletion by NGS or absence of MTAP protein by IHC.**
- ECOG 0–1 or Karnofsky score ≥70.
- A sarcoma expansion arm covering soft-tissue and bone sarcomas.
- Tumor SDMA as a pharmacodynamic endpoint. ([clinicaltrials.gov](https://clinicaltrials.gov/study/NCT05275478?utm_source=openai))

**Implication:** This is the more directly disease-relevant of the two specified trials because it includes a sarcoma expansion arm. The present report still does not establish its required biomarker. The retrieved current registry excerpt did not clearly expose the overall recruitment-status field; direct site/sponsor confirmation is therefore necessary before referral.

### Confirmation priorities

1. Re-review purity-adjusted copy-number plots and log-ratio/allele-frequency data to determine whether MTAP loss is homozygous, heterozygous, or subclonal.
2. Perform MTAP IHC with an internal positive control, documenting whether loss is complete and restricted to tumor cells.
3. If tissue permits, assess the dedifferentiated and cartilaginous components separately.
4. Confirm whether CDKN2A/CDKN2B are independently deleted rather than inferred from MTAP.
5. If pursuing NCT05275478 or a similar trial, obtain written confirmation that the local assay, specimen age, and IHC clone/scoring meet central-screening requirements.

### Clinical actionability

**Investigational only.** No MTAP-directed therapy is established standard care for dedifferentiated chondrosarcoma. The available evidence supports molecular confirmation and trial consideration, not off-label treatment.

---

## 2. Unresolved 9p21 cell-cycle suppressor dysregulation

### Disease-specific evidence

The 9p21/RB pathway is recurrently altered in dedifferentiated chondrosarcoma. In a FISH-based study, CDKN2A loss occurred in **13 of 21 dedifferentiated tumors (62%)**. In informative paired areas, the well-differentiated component could retain diploid CDKN2A while the dedifferentiated component showed loss or homozygous deletion, supporting acquisition during progression in at least some tumors. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC4325180/?utm_source=openai))

A newer clinical-genomic series found CDKN2A and CDKN2B alterations in **35% each** of dedifferentiated chondrosarcomas and MTAP alterations in 19%. These population frequencies support a possible regional 9p21 event, but do not establish co-deletion in this individual tumor. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/?utm_source=openai))

Integrated DDCS profiling also found enrichment of CDKN2A/B copy-number loss, TP53 alterations, and G2–M/E2F transcriptional programs. This supports cell-cycle dysregulation as part of DDCS biology, but not a validated treatment-selection biomarker. ([pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov/36926116/?utm_source=openai))

### Patient-specific interpretation

**Mechanism value: moderate; current clinical actionability: low.**

The reported CDKN2A RNA underexpression is consistent with, but does not prove:

- Homozygous CDKN2A deletion.
- Promoter methylation or another silencing mechanism.
- Complete p16 protein loss.
- Functional dependency on CDK4/6.

The contradictory CDKN2B RNA annotation and undocumented, low-confidence DNA loss should not be interpreted until the original source pages and directionality are reconciled.

Most importantly, a CDK4/6-directed hypothesis requires **retained functional RB1**. RB1 loss or absent pRB generally removes the downstream machinery required for a conventional CDK4/6-inhibitor effect. Disease-specific clinical efficacy of CDK4/6 inhibition in DDCS was not identified.

### Confirmation priorities

1. Recover the original CDKN2B RNA result and verify whether it is overexpressed or underexpressed.
2. Obtain locus-level copy-number assessment for **MTAP, CDKN2A, and CDKN2B separately**, ideally with allele-specific data or orthogonal FISH/ddPCR.
3. Perform p16 IHC, with attention to tumor-cell staining and the two histologic components.
4. Assess RB1 by:
   - DNA sequencing/copy number,
   - RB/pRB IHC,
   - and, where feasible, an E2F or RB-functional expression signature.
5. Review CCND1, CDK4, CDK6, and CDKN2C, but do not infer activation solely from expression.

### Combination/bypass interpretation

- MTAP metabolism and p16/RB dysregulation may be parallel consequences of a regional 9p21 deletion; neither validates the other.
- Confirmed p16 loss with retained RB could support an investigational CDK4/6 hypothesis, but not standard use.
- RB loss, cyclin E/CDK2 activation, or broader E2F deregulation could bypass CDK4/6 blockade.
- No evidence presently supports combining an MTAP-directed agent with a CDK4/6 inhibitor in this patient outside a trial designed to establish safety and pharmacology.

---

## 3. CHEK2/checkpoint and genome-surveillance pathway

### Variant interpretation

ClinVar classifies **CHEK2 NM_007194.4:c.846+4_846+7del** as pathogenic/likely pathogenic for germline CHEK2-related cancer predisposition, with multiple submitters and no classification conflict. RNA studies show abnormal transcripts involving exon 7 or exons 7–8; predicted consequences include a frameshift/premature stop or an in-frame deletion disrupting the kinase domain. Functional work indicates substantially reduced kinase activity. ([ncbi.nlm.nih.gov](https://www.ncbi.nlm.nih.gov/clinvar/variation/216652/?utm_source=openai))

This establishes that the variant can impair CHEK2 function. It does **not** establish in this case:

- Whether it is germline or somatic.
- Whether the tumor contains a second hit or loss of the wild-type allele.
- Whether the variant is clonal in the dedifferentiated component.
- Whether the tumor has functional homologous-recombination deficiency.

The absence of matched normal makes germline origin particularly important to resolve.

### Disease fit

CHEK2 is not a recurrent defining alteration in the retrieved DDCS series. By contrast, TP53 alteration is common—approximately 59%–68% in disease-specific studies—and may arise preferentially in the dedifferentiated component. Therefore, verification of the separate low-confidence TP53 splice-region call is at least as important as the CHEK2 finding for interpreting checkpoint biology. ([pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov/33147331/?utm_source=openai))

### PARP/HRD caution

**CHEK2 loss alone should not be treated as equivalent to BRCA1/2 loss.**

In an FDA pooled analysis of metastatic prostate-cancer trials—**off-disease evidence**—PARP-inhibitor benefit was greatest in BRCA1, BRCA2, PALB2, and CDK12 groups, while no clear benefit was observed in the CHEK2-mutated subgroup. This does not determine activity in DDCS, but it is important negative evidence against assuming PARP sensitivity from CHEK2 alone. ([pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov/38484203/?utm_source=openai))

### Confirmation priorities

1. Confirm the variant by orthogonal sequencing.
2. Refer for germline testing and genetic counseling using blood or another non-tumor specimen.
3. Determine variant allele fraction relative to tumor purity and local copy number.
4. Test for loss of heterozygosity or a second CHEK2 hit.
5. If fresh/viable tissue is available, consider functional HR assessment such as irradiation-induced RAD51 foci.
6. Review:
   - BRCA1/2, PALB2, RAD51C/D and BARD1;
   - ATM and other checkpoint genes;
   - genomic scars/signature 3 or validated HRD measures;
   - the exact TP53 variant and its supporting reads.
7. Interpret TP53 IHC cautiously: null or diffuse-aberrant staining may support dysfunction, but normal-pattern staining does not exclude a pathogenic splice variant.

### Clinical actionability

**Currently low.** The variant is important for germline assessment and tumor biology, but does not independently justify a PARP inhibitor or checkpoint-directed combination in DDCS. ATR, WEE1, CHK1, DNA-damaging, or PARP combinations remain trial-level hypotheses requiring confirmed functional context and safety data.

---

## 4. Exploratory AKT2 and LYN signaling observations

### Disease-specific evidence

The PI3K–AKT–mTOR pathway can be active in chondrosarcoma. Phosphorylated S6, a downstream surrogate, was reported in **11 of 25 dedifferentiated chondrosarcomas (44%)**. Activating genomic alterations in this pathway are nevertheless uncommon, and pathway activation can arise through multiple upstream inputs. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC6248264/?utm_source=openai))

Chondrosarcoma kinase-screening studies also found strong AKT, Src, and MAPK activity in model systems and heterogeneous receptor activation. These findings establish pathway plausibility, not AKT2-specific dependence or clinical efficacy of AKT/Src inhibitors. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC6889735/?utm_source=openai))

### AKT2 interpretation

AKT2 RNA overexpression does not establish:

- Increased AKT2 protein.
- Membrane recruitment or activating phosphorylation.
- Dominance over AKT1/AKT3.
- Downstream pathway activation.
- Sensitivity to an AKT inhibitor.

**Recommended confirmation:** AKT2 protein, phospho-AKT Ser473/Thr308, phospho-PRAS40, phospho-S6, PTEN expression, and review of PIK3CA/PIK3R1/PTEN/TSC1/TSC2/MTOR alterations. Phosphoproteomic testing would be more informative than RNA alone if available and analytically validated.

If AKT signaling and a functional RB axis are both confirmed, they may represent parallel survival and cell-cycle pathways. That is a mechanistic rationale for research, not evidence that a combination is tolerable or effective.

### LYN interpretation

No convincing disease-specific evidence was identified that LYN copy-number gain defines a therapeutic subgroup in DDCS. A low-confidence gain without source-page documentation should be considered non-actionable.

Before further consideration, establish:

- Reproducibility on raw copy-number data.
- Focal versus arm-level gain.
- Absolute copy number after purity/ploidy adjustment.
- LYN RNA and protein expression.
- Activating phosphorylation or a coherent Src-family signaling signature.

Broad Src-family activity in chondrosarcoma models does not prove that LYN is the responsible kinase in this specimen.

---

## Molecular tumor-board priorities

1. **Resolve MTAP first:** allele-specific copy number plus MTAP IHC with internal controls.
2. **Map the full 9p21 event:** independently assess MTAP, CDKN2A and CDKN2B; do not infer one from another.
3. **Establish RB competence:** RB1 sequencing/copy number and RB/pRB IHC before any CDK4/6 discussion.
4. **Confirm CHEK2 origin and second-hit status:** matched-normal/germline testing is particularly important.
5. **Verify the TP53 call:** obtain exact HGVS variant, read evidence, transcript consequence and orthogonal confirmation.
6. **Do not act on AKT2 RNA or LYN gain alone:** seek phosphoprotein/pathway evidence.
7. **Clarify clinical context:** localized versus unresectable/recurrent/metastatic disease, prior treatment, ECOG status, measurable disease, and biopsy feasibility determine whether any investigational pathway has practical relevance.

## Overall actionability ranking

| Pathway | Mechanistic confidence now | Clinical relevance now |
|---|---:|---:|
| MTAP–MTA–PRMT5 | Moderate; potentially high after confirmation | Highest, but investigational |
| CDKN2A/B–RB cell cycle | Moderate biologic plausibility | Low without deletion/p16/RB confirmation |
| CHEK2/checkpoint | Variant-level LoF evidence strong; tumor-state evidence incomplete | Low; germline implications important |
| AKT2 signaling | Low from RNA alone | Exploratory |
| LYN signaling | Very low | Non-actionable pending confirmation |

---

## Sources used

1. **Peer-reviewed primary disease-genomic study — disease prevalence and co-alterations.**  
   Supports MTAP, CDKN2A/B and TP53 alteration frequencies in DDCS. Does not establish therapeutic response.  
   https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/

2. **Peer-reviewed primary mechanistic study — MTAP/MTA/PRMT5 dependency.**  
   Supports MTA accumulation, partial PRMT5 suppression, SDMA effects and enriched PRMT5 dependency. Does not establish clinical efficacy or universal sensitivity.  
   https://pmc.ncbi.nlm.nih.gov/articles/PMC4997612/

3. **Peer-reviewed translational/early clinical study — anvumetostat/AMG 193.**  
   Supports MTA-cooperative mechanism and early pan-cancer clinical development. Does not establish DDCS-specific efficacy.  
   https://pubmed.ncbi.nlm.nih.gov/39282709/

4. **Official trial registry — NCT05094336, anvumetostat/AMG 193.**  
   Supports current trial status, aliases, biomarker language and general eligibility. Does not establish this patient’s eligibility or efficacy in DDCS.  
   https://clinicaltrials.gov/study/NCT05094336

5. **Official trial registry — NCT05275478, TNG908.**  
   Supports acceptance of homozygous MTAP deletion by NGS or absent MTAP protein by IHC, the sarcoma cohort and SDMA pharmacodynamics. Does not establish eligibility without clinical and assay review.  
   https://clinicaltrials.gov/study/NCT05275478

6. **Peer-reviewed primary pathology study — CDKN2A copy-number evolution.**  
   Supports frequent CDKN2A loss and component-specific deletion in DDCS. Does not establish CDK4/6-inhibitor efficacy.  
   https://pmc.ncbi.nlm.nih.gov/articles/PMC4325180/

7. **NCBI ClinVar evidence record — CHEK2 c.846+4_846+7del.**  
   Supports germline pathogenic/likely-pathogenic classification and abnormal splicing evidence. Does not establish somatic oncogenicity, biallelic loss, or HRD in this tumor.  
   https://www.ncbi.nlm.nih.gov/clinvar/variation/216652/

8. **FDA pooled clinical analysis, peer-reviewed — off-disease negative evidence.**  
   Supports caution about PARP-inhibitor benefit in CHEK2-mutated prostate cancer. Does not directly determine response in DDCS.  
   https://pubmed.ncbi.nlm.nih.gov/38484203/

9. **Peer-reviewed disease review synthesizing primary tissue studies — PI3K/AKT/mTOR.**  
   Supports the occurrence of phospho-S6 pathway activity in DDCS. Does not establish AKT2-specific activation or clinical benefit from AKT inhibition.  
   https://pmc.ncbi.nlm.nih.gov/articles/PMC6248264/

10. **Peer-reviewed primary/translational study — chondrosarcoma kinase dependencies.**  
    Supports heterogeneous AKT/Src pathway activity in chondrosarcoma models and tissue-level phospho-S6 findings. Does not validate LYN gain or a clinically usable kinase target.  
    https://pmc.ncbi.nlm.nih.gov/articles/PMC6889735/

## Open-web translational discovery

# Molecular tumor board research memo  
**Diagnosis:** Dedifferentiated chondrosarcoma  
**Specimen:** Chest-wall soft-tissue tumor, 80% tumor  
**Report date:** June 5, 2024  
**Key limitation:** Stage, disease setting, prior treatment, ECOG status, measurable disease, and biopsy feasibility are unknown; therefore, trial eligibility cannot be inferred.

## Executive interpretation

1. **MTAP is the most credible investigational pathway**, because MTAP deletion occurs in a disease-matched DDCS cohort and has a well-defined MTA–PRMT5 dependency. However, the reported DNA copy loss plus RNA underexpression does **not** yet prove homozygous, clonal, functionally MTAP-null disease. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/?utm_source=openai))
2. The two specifically queried trials are **not current enrollment options**: NCT05275478 is terminated, while NCT05094336 is active but not recruiting and Amgen has announced discontinuation of further AMG 193 development. ([clinicaltrials.gov](https://clinicaltrials.gov/study/NCT05275478?utm_source=openai))
3. **CDKN2A/B and MTAP should be interpreted as potentially separate consequences of a 9p21 regional event.** MTAP loss does not validate CDKN2A/B loss, and RNA underexpression alone is insufficient for CDK4/6-directed reasoning.
4. **CHEK2 c.846+4_846+7del has credible splice-disrupting evidence**, but tumor-only detection does not establish whether it is germline or somatic, monoallelic or biallelic, or whether this DDCS is HR-deficient. It is not, by itself, a treatment biomarker. ([ncbi.nlm.nih.gov](https://www.ncbi.nlm.nih.gov/clinvar/RCV000222175/))
5. **AKT2 RNA overexpression and the undocumented LYN gain remain exploratory.** Neither establishes activated signaling or currently supports a kinase-directed candidate.

---

## 1. MTAP-associated methionine-salvage vulnerability

### Disease fit and mechanism

A clinical-grade genomic study reported MTAP deletion in **6 of 31 DDCS tumors (19%)**, alongside frequent CDKN2A and CDKN2B alterations. This establishes that MTAP deletion is a genuine, although minority, molecular subset of DDCS; it does not establish sensitivity to a specific agent in this histology. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/?utm_source=openai))

Mechanistically, MTAP loss prevents normal metabolism of methylthioadenosine, producing intracellular MTA accumulation in experimental models. MTA partially suppresses PRMT5 activity and creates increased dependence on residual PRMT5/WDR77 function. Reduced symmetric dimethylarginine and H4R3 symmetric methylation are potential pathway/pharmacodynamic readouts, not validated routine eligibility tests. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC4997612/?utm_source=openai))

### Patient-specific interpretation

The current combination of **DNA copy-number loss plus RNA underexpression is supportive, but insufficient**. Priority confirmation should be:

- Review allele-specific copy number and purity-adjusted depth to distinguish **homozygous deletion, single-copy loss, and subclonal loss**.
- Orthogonally confirm the locus with validated copy-number NGS, FISH, MLPA, or another laboratory-supported method.
- Perform **MTAP IHC**, requiring absent staining in tumor cells with retained internal staining in non-neoplastic stromal/endothelial cells.
- Where morphology permits, test the **dedifferentiated component separately**, because component-specific or subclonal 9p21 loss is possible.
- Resolve whether the reported deletion encompasses the complete MTAP coding region rather than a partial/exon-only call.
- Tumor MTA or PRMT5-methylation assays may be useful translationally but are not established substitutes for trial-specified genomic or IHC definitions.

### Specifically queried trials

**NCT05094336 — AMG 193/anvumetostat, MTAPESTRY 101**

The registry accepted evidence of **homozygous CDKN2A loss and/or MTAP-null status in tumor tissue or blood, or lost MTAP expression in tumor tissue**, depending on study part. Thus, an adequately validated homozygous deletion or complete MTAP IHC loss could have met the biomarker definition; copy loss plus RNA underexpression alone would require sponsor confirmation and likely further validation. Other requirements included advanced disease not amenable to curative local treatment, generally RECIST-measurable disease and ECOG 0–1. ([clinicaltrials.gov](https://clinicaltrials.gov/study/NCT05094336?utm_source=openai))

This is no longer a practical enrollment route: ClinicalTrials.gov lists the study as **active, not recruiting**, and Amgen’s first-quarter 2026 update states that further AMG 193 development and the study’s dose-expansion program will be discontinued. The registry’s FDA-regulated-drug designation does not mean that AMG 193 was approved. ([clinicaltrials.gov](https://clinicaltrials.gov/study/NCT05094336?a=53&tab=history&utm_source=openai))

**NCT05275478 — TNG908/ralometostat**

This study required **confirmed homozygous MTAP deletion** and included a bone/soft-tissue sarcoma expansion cohort, making it historically relevant to DDCS. It is now **terminated**, with the registry citing a sponsor business decision, and is not accepting participants. The available DNA/RNA findings would not independently establish its homozygous-deletion requirement. ([clinicaltrials.gov](https://clinicaltrials.gov/study/NCT05275478?utm_source=openai))

### Clinical actionability

**Current level: investigational, pending confirmation.** There is disease-matched prevalence and strong pan-cancer mechanistic support, but no DDCS efficacy evidence establishing an MTAP-directed standard. A different currently recruiting MTAP trial would need fresh matching against its exact histology, assay, disease-setting, biopsy and prior-treatment requirements.

No MTAP combination should be proposed clinically solely from genomic proximity to CDKN2A/B. Combination concepts involving cell-cycle, DNA-damage, or survival-pathway inhibition remain preclinical hypotheses unless supported by an appropriate protocol.

---

## 2. Unresolved 9p21 cell-cycle suppressor dysregulation

### Disease fit

In the same exact-histology cohort, CDKN2A and CDKN2B alterations were each reported in approximately **35% of DDCS**, while MTAP deletion occurred in 19%. This supports recurrent 9p21-region disruption in DDCS but also demonstrates that the genes cannot be assumed to be co-deleted in every tumor. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/?utm_source=openai))

### Patient-specific interpretation

CDKN2A RNA underexpression is not equivalent to homozygous deletion or p16 protein absence. The contradictory CDKN2B RNA annotation and undocumented low-confidence copy-loss call should be resolved before pathway assignment.

Recommended confirmation:

- Obtain the original CDKN2B source-page result and direction of expression.
- Reassess allele-specific copy number across **CDKN2A, CDKN2B and MTAP**, including deletion boundaries and clonality.
- Perform p16 IHC, interpreted in the dedifferentiated tumor cells with internal controls.
- Test **RB1 copy number/sequence and RB protein expression**.
- Consider cyclin D1, CDK4/6 and Ki-67 as contextual markers, not standalone predictive assays.

### Mechanism versus actionability

Confirmed p16 loss with intact RB would provide a coherent model of increased CDK4/6–RB–E2F activity. Nevertheless, this does **not** establish that a CDK4/6 inhibitor is effective in DDCS. RB loss would be a strong biological reason not to expect canonical CDK4/6 dependence.

The proposed AKT–cell-cycle combination remains only a hypothesis: it would require independent evidence of active AKT signaling and an intact, CDK4/6-dependent RB axis. MTAP-directed and cell-cycle-directed strategies should be evaluated as separate dependencies rather than assuming that one biomarker confirms the other.

---

## 3. CHEK2-associated checkpoint observation

### Variant interpretation

ClinVar classifies **CHEK2 NM_007194.4:c.846+4_846+7del** as pathogenic/likely pathogenic in the **germline cancer-predisposition context**. RNA studies cited by submitters show abnormal transcripts, including an out-of-frame exon-skipping transcript expected to produce absent/nonfunctional protein and an in-frame transcript removing part of the kinase domain; the corresponding exon-deleted protein had substantially reduced kinase activity. ClinVar has no somatic clinical-impact or somatic-oncogenicity assertion for this variant. ([ncbi.nlm.nih.gov](https://www.ncbi.nlm.nih.gov/clinvar/RCV000222175/))

### Patient-specific interpretation

Because no matched normal was tested, this result could represent:

- A germline CHEK2 pathogenic variant,
- A somatic variant,
- Or a mixture complicated by tumor purity and copy-number state.

The splice effect is credible, but functional tumor inactivation remains unresolved.

Priority work-up:

1. Confirm the exact transcript/HGVS nomenclature and assay read support.
2. Test peripheral blood or another non-neoplastic specimen through an appropriate germline laboratory, with genetic counseling if indicated.
3. Determine variant allele fraction, locus copy number and loss of heterozygosity.
4. If tissue permits, use RNA sequencing or targeted RT-PCR to confirm aberrant splicing in this tumor.
5. Evaluate the reported TP53 splice-region call with exact nomenclature, read evidence and orthogonal confirmation.
6. Assess BRCA1/2, PALB2, RAD51-pathway alterations, genomic LOH/HRD signatures and—where feasible—functional RAD51 foci before invoking homologous-recombination deficiency.

### Clinical actionability

**CHEK2 alone should not be used to infer PARP-inhibitor, platinum, ATR/CHK1 or other checkpoint sensitivity in DDCS.** Neither monoallelic status nor a pathogenic germline classification proves HRD in the tumor. Any DNA-damaging/checkpoint combination would be investigational and would require a suitable study with explicit biomarker eligibility and safety monitoring.

No recurrent, disease-specific CHEK2 therapeutic signal meeting the source threshold was identified in this focused DDCS search.

---

## 4. AKT2 and LYN signaling observations

### AKT2

AKT2 RNA overexpression can reflect transcriptional state, tumor composition or pathway feedback and does not establish kinase activation. Before considering the PI3K–AKT–mTOR pathway biologically active, assess:

- AKT2 protein abundance,
- Phospho-AKT at validated activation sites,
- Downstream phospho-PRAS40, phospho-S6 and phospho-4EBP1,
- Upstream PIK3CA, PIK3R1, PTEN, receptor-tyrosine-kinase and RAS alterations,
- Whether activation is present specifically in the dedifferentiated component.

Absent these findings, AKT2 is a **monitoring/confirmation observation**, not a drug-selection biomarker.

### LYN

The LYN copy-number gain lacks adequate source documentation. Confirm the original call, genomic coordinates, assay quality, absolute copy number, focality and tumor-purity adjustment. If confirmed, LYN protein and activating phosphorylation would still be required to argue functional signaling.

No DDCS-specific evidence found in the prioritized search supports treating a low-confidence LYN gain. Accordingly, no LYN combination hypothesis is currently supportable.

---

## Immediate molecular priorities

1. **Orthogonally establish MTAP status:** complete homozygous deletion and/or MTAP IHC loss.
2. Map the full **9p21 deletion boundaries** and determine whether MTAP, CDKN2A and CDKN2B are independently affected.
3. Confirm **p16 and RB protein status** in the dedifferentiated component.
4. Conduct matched-normal testing for **CHEK2**, plus tumor LOH/splice analysis.
5. Resolve the undocumented TP53 and LYN calls from original report pages.
6. Confirm AKT signaling with phosphoprotein/downstream readouts rather than RNA alone.
7. Reassess trial options only after stage, recurrence/metastatic status, prior therapies, ECOG, measurable disease and biopsy feasibility are known.

## Sources used

1. **Peer-reviewed primary research — exact-histology genomic landscape**  
   Wagner et al., *Genomic Characterization of Chondrosarcoma Reveals Potential Therapeutic Targets*.  
   Supports DDCS frequencies of MTAP, CDKN2A and CDKN2B alterations. Does not establish drug efficacy or individual-patient eligibility.  
   https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/

2. **Peer-reviewed primary translational research — MTAP/PRMT5 mechanism**  
   Kryukov et al., *MTAP deletion confers enhanced dependency on the arginine methyltransferase PRMT5 in human cancer cells*.  
   Supports MTA accumulation, partial PRMT5 suppression, PRMT5 dependency and methylation readouts. Pan-cancer/preclinical; does not establish DDCS efficacy.  
   https://pmc.ncbi.nlm.nih.gov/articles/PMC4997612/

3. **Official trial registry — AMG 193/anvumetostat eligibility and status**  
   ClinicalTrials.gov, NCT05094336.  
   Supports biomarker definitions and general eligibility requirements; does not establish this patient’s eligibility or efficacy in DDCS.  
   https://clinicaltrials.gov/study/NCT05094336

4. **Sponsor development update — current AMG 193 program disposition**  
   Amgen first-quarter 2026 financial results.  
   Supports discontinuation of further AMG 193 development; sponsor material does not independently establish efficacy or safety.  
   https://investors.amgen.com/static-files/4e8e58ab-1e91-441e-94ea-4c8285338ec9

5. **Official trial registry — TNG908/ralometostat**  
   ClinicalTrials.gov, NCT05275478.  
   Supports the historical homozygous-MTAP-deletion requirement, sarcoma cohort and terminated status. Does not establish efficacy or current access.  
   https://clinicaltrials.gov/study/NCT05275478

6. **Clinical variant database — CHEK2 splice variant**  
   ClinVar RCV000222175.  
   Supports germline pathogenic/likely pathogenic classification and reported splice/kinase effects. Does not establish somatic oncogenicity, tumor biallelic loss, HRD or therapeutic sensitivity.  
   https://www.ncbi.nlm.nih.gov/clinvar/RCV000222175/

## All consulted web sources

- [https://pmc.ncbi.nlm.nih.gov/articles/PMC10417069/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10417069/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/28420036/](https://pubmed.ncbi.nlm.nih.gov/28420036/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/34734747/](https://pubmed.ncbi.nlm.nih.gov/34734747/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/41895355/](https://pubmed.ncbi.nlm.nih.gov/41895355/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/37383872/](https://pubmed.ncbi.nlm.nih.gov/37383872/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/38311185/](https://pubmed.ncbi.nlm.nih.gov/38311185/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC10013202/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10013202/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/20140939/](https://pubmed.ncbi.nlm.nih.gov/20140939/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/33147331/](https://pubmed.ncbi.nlm.nih.gov/33147331/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/35485870/](https://pubmed.ncbi.nlm.nih.gov/35485870/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/16631464/](https://pubmed.ncbi.nlm.nih.gov/16631464/) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/88/NCT03666988/SAP_001.pdf](https://cdn.clinicaltrials.gov/large-docs/88/NCT03666988/SAP_001.pdf) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC431183/pdf/pnas00040-0366.pdf](https://pmc.ncbi.nlm.nih.gov/articles/PMC431183/pdf/pnas00040-0366.pdf) — authoritative
- [https://www.clinicaltrials.gov/ProvidedDocs/68/NCT02903368/Prot_SAP_000.pdf](https://www.clinicaltrials.gov/ProvidedDocs/68/NCT02903368/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/17/NCT02693717/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/17/NCT02693717/Prot_SAP_000.pdf) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336](https://clinicaltrials.gov/study/NCT05094336) — authoritative
- [https://clinicaltrials.gov/api/v2/studies/NCT05094336](https://clinicaltrials.gov/api/v2/studies/NCT05094336) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?a=53&tab=history](https://clinicaltrials.gov/study/NCT05094336?a=53&tab=history) — authoritative
- [https://clinicaltrials.gov/data-about-studies/api-migration](https://clinicaltrials.gov/data-about-studies/api-migration) — authoritative
- [https://clinicaltrials.gov/data-api/about-api/study-data-structure](https://clinicaltrials.gov/data-api/about-api/study-data-structure) — authoritative
- [https://clinicaltrials.gov/data-about-studies/learn-about-api](https://clinicaltrials.gov/data-about-studies/learn-about-api) — authoritative
- [https://clinicaltrials.gov/find-studies](https://clinicaltrials.gov/find-studies) — authoritative
- [https://clinicaltrials.gov/?rel=0](https://clinicaltrials.gov/?rel=0) — authoritative
- [https://clinicaltrials.gov/study/NCT07594626](https://clinicaltrials.gov/study/NCT07594626) — authoritative
- [https://clinicaltrials.gov/study/NCT06883747](https://clinicaltrials.gov/study/NCT06883747) — authoritative
- [https://clinicaltrials.gov/study/NCT06188702?checkSpell=&rank=5&term=AREA%5BConditionSearch%5D%28%28METHIONINE+ADENOSYLTRANSFERASE+I%2FIII+DEFICIENCY%29+OR+%28mat2a%29%29](https://clinicaltrials.gov/study/NCT06188702?checkSpell=&rank=5&term=AREA%5BConditionSearch%5D%28%28METHIONINE+ADENOSYLTRANSFERASE+I%2FIII+DEFICIENCY%29+OR+%28mat2a%29%29) — authoritative
- [https://clinicaltrials.gov/study/NCT06855771](https://clinicaltrials.gov/study/NCT06855771) — authoritative
- [https://clinicaltrials.gov/study/NCT06922591](https://clinicaltrials.gov/study/NCT06922591) — authoritative
- [https://clinicaltrials.gov/study/NCT05732831](https://clinicaltrials.gov/study/NCT05732831) — authoritative
- [https://cdn.clinicaltrials.gov/documents/modernization/CTGModernizationPublicMeetingTranscript.pdf](https://cdn.clinicaltrials.gov/documents/modernization/CTGModernizationPublicMeetingTranscript.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/documents/modernization/WebsiteFunctionalityPanel.pdf](https://cdn.clinicaltrials.gov/documents/modernization/WebsiteFunctionalityPanel.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/documents/modernization/IntroductionandOverviewSession.pdf](https://cdn.clinicaltrials.gov/documents/modernization/IntroductionandOverviewSession.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/35/NCT03314935/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/35/NCT03314935/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/53/NCT05138653/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/53/NCT05138653/Prot_000.pdf) — authoritative
- [https://clinicaltrials.gov/study/NCT05275478](https://clinicaltrials.gov/study/NCT05275478) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?a=22&tab=history](https://clinicaltrials.gov/study/NCT05094336?a=22&tab=history) — authoritative
- [https://clinicaltrials.gov/study/NCT07492680](https://clinicaltrials.gov/study/NCT07492680) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?a=58&tab=history](https://clinicaltrials.gov/study/NCT05094336?a=58&tab=history) — authoritative
- [https://clinicaltrials.gov/study/NCT07549022](https://clinicaltrials.gov/study/NCT07549022) — authoritative
- [https://clinicaltrials.gov/study/NCT06810544](https://clinicaltrials.gov/study/NCT06810544) — authoritative
- [https://clinicaltrials.gov/study/NCT03435250?a=41&tab=history](https://clinicaltrials.gov/study/NCT03435250?a=41&tab=history) — authoritative
- [https://clinicaltrials.gov/study/NCT06188702](https://clinicaltrials.gov/study/NCT06188702) — authoritative
- [https://clinicaltrials.gov/study/NCT06360354?tab=table](https://clinicaltrials.gov/study/NCT06360354?tab=table) — authoritative
- [https://clinicaltrials.gov/study/NCT07579221](https://clinicaltrials.gov/study/NCT07579221) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/79/NCT04770779/SAP_001.pdf](https://cdn.clinicaltrials.gov/large-docs/79/NCT04770779/SAP_001.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/51/NCT04415151/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/51/NCT04415151/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/52/NCT05259852/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/52/NCT05259852/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/04/NCT04281004/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/04/NCT04281004/Prot_000.pdf) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?cond=NCT05094336](https://clinicaltrials.gov/study/NCT05094336?cond=NCT05094336) — authoritative
- [https://clinicaltrials.gov/study/NCT05245500](https://clinicaltrials.gov/study/NCT05245500) — authoritative
- [https://clinicaltrials.gov/study/NCT04794699](https://clinicaltrials.gov/study/NCT04794699) — authoritative
- [https://clinicaltrials.gov/study/NCT06914128?tab=table](https://clinicaltrials.gov/study/NCT06914128?tab=table) — authoritative
- [https://clinicaltrials.gov/study/NCT06968572](https://clinicaltrials.gov/study/NCT06968572) — authoritative
- [https://clinicaltrials.gov/study/NCT06589596](https://clinicaltrials.gov/study/NCT06589596) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/59/NCT02462759/Prot_001.pdf](https://cdn.clinicaltrials.gov/large-docs/59/NCT02462759/Prot_001.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/62/NCT04599062/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/62/NCT04599062/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/14/NCT04863014/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/14/NCT04863014/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/18/NCT04233918/Prot_002.pdf](https://cdn.clinicaltrials.gov/large-docs/18/NCT04233918/Prot_002.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/69/NCT00819169/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/69/NCT00819169/Prot_SAP_000.pdf) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/26912360/](https://pubmed.ncbi.nlm.nih.gov/26912360/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC4997612/](https://pmc.ncbi.nlm.nih.gov/articles/PMC4997612/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/26912361/](https://pubmed.ncbi.nlm.nih.gov/26912361/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/39282709/](https://pubmed.ncbi.nlm.nih.gov/39282709/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/41512197/](https://pubmed.ncbi.nlm.nih.gov/41512197/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC13044523/](https://pmc.ncbi.nlm.nih.gov/articles/PMC13044523/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/37774699/](https://pubmed.ncbi.nlm.nih.gov/37774699/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/38595098/](https://pubmed.ncbi.nlm.nih.gov/38595098/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC8270912/](https://pmc.ncbi.nlm.nih.gov/articles/PMC8270912/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/40146197/](https://pubmed.ncbi.nlm.nih.gov/40146197/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/37552839/](https://pubmed.ncbi.nlm.nih.gov/37552839/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/39919252/](https://pubmed.ncbi.nlm.nih.gov/39919252/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC5644504/pdf/nihms886790.pdf](https://pmc.ncbi.nlm.nih.gov/articles/PMC5644504/pdf/nihms886790.pdf) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC1839956/pdf/nihms15677.pdf](https://pmc.ncbi.nlm.nih.gov/articles/PMC1839956/pdf/nihms15677.pdf) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC7817689/pdf/41467_2020_Article_20790.pdf](https://pmc.ncbi.nlm.nih.gov/articles/PMC7817689/pdf/41467_2020_Article_20790.pdf) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC4883595/pdf/nihms770340.pdf](https://pmc.ncbi.nlm.nih.gov/articles/PMC4883595/pdf/nihms770340.pdf) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC4052024/](https://pmc.ncbi.nlm.nih.gov/articles/PMC4052024/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC4498940/](https://pmc.ncbi.nlm.nih.gov/articles/PMC4498940/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC13004474/](https://pmc.ncbi.nlm.nih.gov/articles/PMC13004474/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC4325180/](https://pmc.ncbi.nlm.nih.gov/articles/PMC4325180/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC6248264/](https://pmc.ncbi.nlm.nih.gov/articles/PMC6248264/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC1852953/](https://pmc.ncbi.nlm.nih.gov/articles/PMC1852953/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC8001927/](https://pmc.ncbi.nlm.nih.gov/articles/PMC8001927/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/19336518/](https://pubmed.ncbi.nlm.nih.gov/19336518/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/40627883/](https://pubmed.ncbi.nlm.nih.gov/40627883/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC3018623/](https://pmc.ncbi.nlm.nih.gov/articles/PMC3018623/) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/44/NCT03110744/Prot_001.pdf](https://cdn.clinicaltrials.gov/large-docs/44/NCT03110744/Prot_001.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/20/NCT04436120/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/20/NCT04436120/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/83/NCT02187783/Prot_001.pdf](https://cdn.clinicaltrials.gov/large-docs/83/NCT02187783/Prot_001.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/20/NCT02530320/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/20/NCT02530320/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/78/NCT03519178/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/78/NCT03519178/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/01/NCT03070301/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/01/NCT03070301/Prot_SAP_000.pdf) — authoritative
- [https://www.ncbi.nlm.nih.gov/clinvar/variation/216652/](https://www.ncbi.nlm.nih.gov/clinvar/variation/216652/) — authoritative
- [https://www.ncbi.nlm.nih.gov/clinvar/variation/216652](https://www.ncbi.nlm.nih.gov/clinvar/variation/216652) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/38484203/](https://pubmed.ncbi.nlm.nih.gov/38484203/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/42133897/](https://pubmed.ncbi.nlm.nih.gov/42133897/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/37211773/](https://pubmed.ncbi.nlm.nih.gov/37211773/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/28082821/](https://pubmed.ncbi.nlm.nih.gov/28082821/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/33516088/](https://pubmed.ncbi.nlm.nih.gov/33516088/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/35550005/](https://pubmed.ncbi.nlm.nih.gov/35550005/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/38993246/](https://pubmed.ncbi.nlm.nih.gov/38993246/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/35768576/](https://pubmed.ncbi.nlm.nih.gov/35768576/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/41352287/](https://pubmed.ncbi.nlm.nih.gov/41352287/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/38848470/](https://pubmed.ncbi.nlm.nih.gov/38848470/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/22674453/](https://pubmed.ncbi.nlm.nih.gov/22674453/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/36926116/](https://pubmed.ncbi.nlm.nih.gov/36926116/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/30281149/](https://pubmed.ncbi.nlm.nih.gov/30281149/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/27248819/](https://pubmed.ncbi.nlm.nih.gov/27248819/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/10881744/](https://pubmed.ncbi.nlm.nih.gov/10881744/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/40117529/](https://pubmed.ncbi.nlm.nih.gov/40117529/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/31615936/](https://pubmed.ncbi.nlm.nih.gov/31615936/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/28301537/](https://pubmed.ncbi.nlm.nih.gov/28301537/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/41420192/](https://pubmed.ncbi.nlm.nih.gov/41420192/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/41752158/](https://pubmed.ncbi.nlm.nih.gov/41752158/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/32427623/](https://pubmed.ncbi.nlm.nih.gov/32427623/) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/33/NCT04187833/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/33/NCT04187833/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/47/NCT03207347/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/47/NCT03207347/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/27/NCT04439227/Prot_001.pdf](https://cdn.clinicaltrials.gov/large-docs/27/NCT04439227/Prot_001.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/12/NCT04266912/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/12/NCT04266912/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/32/NCT02095132/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/32/NCT02095132/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/20/NCT02838420/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/20/NCT02838420/Prot_000.pdf) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC3182699/](https://pmc.ncbi.nlm.nih.gov/articles/PMC3182699/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC5796255/](https://pmc.ncbi.nlm.nih.gov/articles/PMC5796255/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC8685273/](https://pmc.ncbi.nlm.nih.gov/articles/PMC8685273/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC9862566/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9862566/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC12531285/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12531285/) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/27047227/](https://pubmed.ncbi.nlm.nih.gov/27047227/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC6889735/](https://pmc.ncbi.nlm.nih.gov/articles/PMC6889735/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC4229252/](https://pmc.ncbi.nlm.nih.gov/articles/PMC4229252/) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC5656027/](https://pmc.ncbi.nlm.nih.gov/articles/PMC5656027/) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/92/NCT04632992/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/92/NCT04632992/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/74/NCT04464174/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/74/NCT04464174/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/16/NCT02677116/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/16/NCT02677116/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/02/NCT04762602/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/02/NCT04762602/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/22/NCT04458922/ICF_001.pdf](https://cdn.clinicaltrials.gov/large-docs/22/NCT04458922/ICF_001.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/53/NCT03046953/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/53/NCT03046953/Prot_SAP_000.pdf) — authoritative
- [https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm) — authoritative
- [https://precision.fda.gov/ginas/app/ui/substances/5139b555-a1ec-41f1-960c-99fa8863dba3](https://precision.fda.gov/ginas/app/ui/substances/5139b555-a1ec-41f1-960c-99fa8863dba3) — authoritative
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-amivantamab-and-hyaluronidase-lpuj-subcutaneous-injection](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-amivantamab-and-hyaluronidase-lpuj-subcutaneous-injection) — authoritative
- [https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?ID=P230011S002](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?ID=P230011S002) — authoritative
- [https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P230042](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P230042) — authoritative
- [https://www.fda.gov/news-events/press-announcements/fda-approves-gene-therapy-treatment-spinal-muscular-atrophy](https://www.fda.gov/news-events/press-announcements/fda-approves-gene-therapy-treatment-spinal-muscular-atrophy) — authoritative
- [https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm?deviceclass=&devicename=&implant_flag=&life_sustain_support_flag=&pagenum=10&panel=OR&productcode=&regulationnumber=&sortcolumn=productcode&start_search=191&submission_type_id=1&summary_malfunction_reporting=&thirdparty=](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm?deviceclass=&devicename=&implant_flag=&life_sustain_support_flag=&pagenum=10&panel=OR&productcode=&regulationnumber=&sortcolumn=productcode&start_search=191&submission_type_id=1&summary_malfunction_reporting=&thirdparty=) — authoritative
- [https://www.accessdata.fda.gov/scripts/cdrh/Cfdocs/cfrl/rl.cfm?lid=509743&lpcd=EYQ](https://www.accessdata.fda.gov/scripts/cdrh/Cfdocs/cfrl/rl.cfm?lid=509743&lpcd=EYQ) — authoritative
- [https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?ID=P010019](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?ID=P010019) — authoritative
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-amivantamab-vmjw-egfr-exon-20-insertion-mutated-non-small-cell-lung-cancer-indications](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-amivantamab-vmjw-egfr-exon-20-insertion-mutated-non-small-cell-lung-cancer-indications) — authoritative
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-amivantamab-vmjw-metastatic-non-small-cell-lung-cancer](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-amivantamab-vmjw-metastatic-non-small-cell-lung-cancer) — authoritative
- [https://www.accessdata.fda.gov/drugsatfda_docs/appletter/2020/761077Orig1s004ltr.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/appletter/2020/761077Orig1s004ltr.pdf) — authoritative
- [https://www.fda.gov/news-events/press-announcements/fda-approves-first-gene-therapy-severe-leukocyte-adhesion-deficiency-type-i](https://www.fda.gov/news-events/press-announcements/fda-approves-first-gene-therapy-severe-leukocyte-adhesion-deficiency-type-i) — authoritative
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2018/761077Orig1s000ChemR.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2018/761077Orig1s000ChemR.pdf) — authoritative
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2015/125522Orig1s000OtherR.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2015/125522Orig1s000OtherR.pdf) — authoritative
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2008/125268s000_ChemR.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2008/125268s000_ChemR.pdf) — authoritative
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2024/761344Orig1s000OtherR.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2024/761344Orig1s000OtherR.pdf) — authoritative
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2015/125522Orig1s000SumR.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2015/125522Orig1s000SumR.pdf) — authoritative
- [https://clinicaltrials.gov/policy/faq](https://clinicaltrials.gov/policy/faq) — authoritative
- [https://clinicaltrials.gov/study/NCT04754191?intr=Enfortumab&page=1&rank=10&viewType=Table](https://clinicaltrials.gov/study/NCT04754191?intr=Enfortumab&page=1&rank=10&viewType=Table) — authoritative
- [https://clinicaltrials.gov/study/NCT02453282](https://clinicaltrials.gov/study/NCT02453282) — authoritative
- [https://clinicaltrials.gov/study/NCT02923778](https://clinicaltrials.gov/study/NCT02923778) — authoritative
- [https://clinicaltrials.gov/study/NCT05747534](https://clinicaltrials.gov/study/NCT05747534) — authoritative
- [https://clinicaltrials.gov/study/NCT07505303](https://clinicaltrials.gov/study/NCT07505303) — authoritative
- [https://clinicaltrials.gov/study/nct05609578?tab=history](https://clinicaltrials.gov/study/nct05609578?tab=history) — authoritative
- [https://clinicaltrials.gov/study/NCT04644770](https://clinicaltrials.gov/study/NCT04644770) — authoritative
- [https://clinicaltrials.gov/study/NCT02152631?id=%22NCT01655225%22OR%22NCT02079636%22OR%22NCT02152631%22OR%22NCT02308020%22OR%22NCT02411591%22OR%22NCT02450539%22&rank=4](https://clinicaltrials.gov/study/NCT02152631?id=%22NCT01655225%22OR%22NCT02079636%22OR%22NCT02152631%22OR%22NCT02308020%22OR%22NCT02411591%22OR%22NCT02450539%22&rank=4) — authoritative
- [https://clinicaltrials.gov/study/NCT04956640?id=NCT04956640&rank=1](https://clinicaltrials.gov/study/NCT04956640?id=NCT04956640&rank=1) — authoritative
- [https://clinicaltrials.gov/study/NCT05463224](https://clinicaltrials.gov/study/NCT05463224) — authoritative
- [https://cdn.clinicaltrials.gov/documents/Observational_Study_Protocol_Registration_Template.pdf](https://cdn.clinicaltrials.gov/documents/Observational_Study_Protocol_Registration_Template.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/documents/RFIConsolidatedComments.pdf](https://cdn.clinicaltrials.gov/documents/RFIConsolidatedComments.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/documents/Interventional_Study_Protocol_Registration_Template_Jan_2018.pdf](https://cdn.clinicaltrials.gov/documents/Interventional_Study_Protocol_Registration_Template_Jan_2018.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/67/NCT04279067/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/67/NCT04279067/Prot_SAP_000.pdf) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?a=26&tab=history](https://clinicaltrials.gov/study/NCT05094336?a=26&tab=history) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?a=25&tab=history](https://clinicaltrials.gov/study/NCT05094336?a=25&tab=history) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?a=39&tab=history](https://clinicaltrials.gov/study/NCT05094336?a=39&tab=history) — authoritative
- [https://clinicaltrials.gov/study/NCT06593522](https://clinicaltrials.gov/study/NCT06593522) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?a=41&tab=history](https://clinicaltrials.gov/study/NCT05094336?a=41&tab=history) — authoritative
- [https://clinicaltrials.gov/study/NCT06360354?rank=1&term=AREA%5BBasicSearch%5D%28AREA%5BConditionSearch%5D%28Pancreatic+Cancer%29+AND+AREA%5BBasicSearch%5D%28Metastatic%29+AND+SEARCH%5BLocation%5D%28AREA%5BLocationCountry%5DUnited+States+AND+AREA%5BLocationState%5DNew+York+AND+AREA%5BLocationCity%5DNew+York%29+AND+AREA%5BOverallStatus%5D%28NOT_YET_RECRUITING+OR+RECRUITING%29%29](https://clinicaltrials.gov/study/NCT06360354?rank=1&term=AREA%5BBasicSearch%5D%28AREA%5BConditionSearch%5D%28Pancreatic+Cancer%29+AND+AREA%5BBasicSearch%5D%28Metastatic%29+AND+SEARCH%5BLocation%5D%28AREA%5BLocationCountry%5DUnited+States+AND+AREA%5BLocationState%5DNew+York+AND+AREA%5BLocationCity%5DNew+York%29+AND+AREA%5BOverallStatus%5D%28NOT_YET_RECRUITING+OR+RECRUITING%29%29) — authoritative
- [https://clinicaltrials.gov/study/NCT06333951?intr=AMG193&rank=3](https://clinicaltrials.gov/study/NCT06333951?intr=AMG193&rank=3) — authoritative
- [https://clinicaltrials.gov/study/NCT06333951](https://clinicaltrials.gov/study/NCT06333951) — authoritative
- [https://clinicaltrials.gov/study/NCT07553572](https://clinicaltrials.gov/study/NCT07553572) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/89/NCT04342689/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/89/NCT04342689/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/50/NCT03103750/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/50/NCT03103750/Prot_SAP_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/23/NCT03258723/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/23/NCT03258723/Prot_000.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/large-docs/25/NCT03700125/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/25/NCT03700125/Prot_000.pdf) — authoritative
- [https://clinicaltrials.gov/?locale=us](https://clinicaltrials.gov/?locale=us) — authoritative
- [https://cdn.clinicaltrials.gov/documents/trainTrainer/SMART-Study-Design-Example-Record.pdf](https://cdn.clinicaltrials.gov/documents/trainTrainer/SMART-Study-Design-Example-Record.pdf) — authoritative
- [https://cdn.clinicaltrials.gov/documents/trainTrainer/Parallel-Design-Answer-Key.pdf](https://cdn.clinicaltrials.gov/documents/trainTrainer/Parallel-Design-Answer-Key.pdf) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/?utm_source=openai](https://pmc.ncbi.nlm.nih.gov/articles/PMC11949235/?utm_source=openai) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC4997612/?utm_source=openai](https://pmc.ncbi.nlm.nih.gov/articles/PMC4997612/?utm_source=openai) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/39282709/?utm_source=openai](https://pubmed.ncbi.nlm.nih.gov/39282709/?utm_source=openai) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC8270912/?utm_source=openai](https://pmc.ncbi.nlm.nih.gov/articles/PMC8270912/?utm_source=openai) — authoritative
- [https://clinicaltrials.gov/study/NCT05094336?cond=NCT05094336&utm_source=openai](https://clinicaltrials.gov/study/NCT05094336?cond=NCT05094336&utm_source=openai) — authoritative
- [https://clinicaltrials.gov/study/NCT05275478?utm_source=openai](https://clinicaltrials.gov/study/NCT05275478?utm_source=openai) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC4325180/?utm_source=openai](https://pmc.ncbi.nlm.nih.gov/articles/PMC4325180/?utm_source=openai) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/36926116/?utm_source=openai](https://pubmed.ncbi.nlm.nih.gov/36926116/?utm_source=openai) — authoritative
- [https://www.ncbi.nlm.nih.gov/clinvar/variation/216652/?utm_source=openai](https://www.ncbi.nlm.nih.gov/clinvar/variation/216652/?utm_source=openai) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/33147331/?utm_source=openai](https://pubmed.ncbi.nlm.nih.gov/33147331/?utm_source=openai) — authoritative
- [https://pubmed.ncbi.nlm.nih.gov/38484203/?utm_source=openai](https://pubmed.ncbi.nlm.nih.gov/38484203/?utm_source=openai) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC6248264/?utm_source=openai](https://pmc.ncbi.nlm.nih.gov/articles/PMC6248264/?utm_source=openai) — authoritative
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC6889735/?utm_source=openai](https://pmc.ncbi.nlm.nih.gov/articles/PMC6889735/?utm_source=openai) — authoritative
- [https://www.ncbi.nlm.nih.gov/clinvar/RCV000222175/](https://www.ncbi.nlm.nih.gov/clinvar/RCV000222175/) — open_web
- [https://www.ncbi.nlm.nih.gov/clinvar/RCV002229123/](https://www.ncbi.nlm.nih.gov/clinvar/RCV002229123/) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC6980683/](https://pmc.ncbi.nlm.nih.gov/articles/PMC6980683/) — open_web
- [https://ascopubs.org/doi/10.1200/JCO.2026.44.16_suppl.11528](https://ascopubs.org/doi/10.1200/JCO.2026.44.16_suppl.11528) — open_web
- [https://www.mdpi.com/2072-6694/15/15/3924](https://www.mdpi.com/2072-6694/15/15/3924) — open_web
- [https://aacrjournals.org/clincancerres/article/15/8/2685/74768/Genomic-Profiling-of-Chondrosarcoma-Chromosomal](https://aacrjournals.org/clincancerres/article/15/8/2685/74768/Genomic-Profiling-of-Chondrosarcoma-Chromosomal) — open_web
- [https://www.sciencedirect.com/science/article/abs/pii/S1040842826001848](https://www.sciencedirect.com/science/article/abs/pii/S1040842826001848) — open_web
- [https://www.ambrygen.com/file/view/729/Espenschied_C_ECCO_2017_Classifying_variants_in_the_CHEK2_gene_the_importance_of_collaboration_Abstract_and_poster.pdf](https://www.ambrygen.com/file/view/729/Espenschied_C_ECCO_2017_Classifying_variants_in_the_CHEK2_gene_the_importance_of_collaboration_Abstract_and_poster.pdf) — open_web
- [https://www.abacusdx.com/media/AMP%202022_Abstracts.pdf](https://www.abacusdx.com/media/AMP%202022_Abstracts.pdf) — open_web
- [https://www.spandidos-publications.com/5324/downloadSupplementary](https://www.spandidos-publications.com/5324/downloadSupplementary) — open_web
- [https://www.nature.com/articles/s41374-021-00549-x.pdf](https://www.nature.com/articles/s41374-021-00549-x.pdf) — open_web
- [https://repository.icr.ac.uk/server/api/core/bitstreams/74dbf531-9187-4ca2-9640-02c03db5c39c/content](https://repository.icr.ac.uk/server/api/core/bitstreams/74dbf531-9187-4ca2-9640-02c03db5c39c/content) — open_web
- [https://pdfs.semanticscholar.org/b5fa/d62c7870927106411135716ad550e8a7215e.pdf](https://pdfs.semanticscholar.org/b5fa/d62c7870927106411135716ad550e8a7215e.pdf) — open_web
- [https://www.reddit.com/r/BRCA/comments/1q8ij19/chek2_variant_c8464delagta_and_hormone_positive_bc/](https://www.reddit.com/r/BRCA/comments/1q8ij19/chek2_variant_c8464delagta_and_hormone_positive_bc/) — open_web
- [https://www.reddit.com/r/ClinicalGenetics/comments/14xuusn](https://www.reddit.com/r/ClinicalGenetics/comments/14xuusn) — open_web
- [https://www.reddit.com/r/breastcancer/comments/18htlni](https://www.reddit.com/r/breastcancer/comments/18htlni) — open_web
- [https://www.reddit.com/r/BRCA/comments/1implnw/got_my_genetic_testing_resultschek2/](https://www.reddit.com/r/BRCA/comments/1implnw/got_my_genetic_testing_resultschek2/) — open_web
- [https://arxiv.org/abs/2505.08508](https://arxiv.org/abs/2505.08508) — open_web
- [https://arxiv.org/abs/2006.07296](https://arxiv.org/abs/2006.07296) — open_web
- [https://arxiv.org/abs/2407.13463](https://arxiv.org/abs/2407.13463) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/1udwy45/tango_462_trial_update/](https://www.reddit.com/r/pancreaticcancer/comments/1udwy45/tango_462_trial_update/) — open_web
- [https://www.reddit.com/r/breastcancer/comments/1sinfgx/my_chek2_mutation_sisters/](https://www.reddit.com/r/breastcancer/comments/1sinfgx/my_chek2_mutation_sisters/) — open_web
- [https://arxiv.org/abs/1809.08289](https://arxiv.org/abs/1809.08289) — open_web
- [https://www.reddit.com/r/AskDocs/comments/zt68n6](https://www.reddit.com/r/AskDocs/comments/zt68n6) — open_web
- [https://www.reddit.com/r/genetics/comments/1ue3dym/chek2_ile157thr/](https://www.reddit.com/r/genetics/comments/1ue3dym/chek2_ile157thr/) — open_web
- [https://www.reddit.com/r/DNA/comments/1goeoia](https://www.reddit.com/r/DNA/comments/1goeoia) — open_web
- [https://www.reddit.com/r/ProstateCancer/comments/1rl01jq/anyone_ever_had_a_variant_of_unknown_significance/](https://www.reddit.com/r/ProstateCancer/comments/1rl01jq/anyone_ever_had_a_variant_of_unknown_significance/) — open_web
- [https://www.reddit.com/r/ClinicalGenetics/comments/1r57roq/can_someone_help_explain_vus_results/](https://www.reddit.com/r/ClinicalGenetics/comments/1r57roq/can_someone_help_explain_vus_results/) — open_web
- [https://www.reddit.com/r/genetics/comments/134qclw](https://www.reddit.com/r/genetics/comments/134qclw) — open_web
- [https://www.cancer.gov/publications/dictionaries/cancer-drug/def/prmt5-mta-inhibitor-mrtx1719](https://www.cancer.gov/publications/dictionaries/cancer-drug/def/prmt5-mta-inhibitor-mrtx1719) — open_web
- [https://www.sciencedirect.com/science/article/pii/S2211124716302996](https://www.sciencedirect.com/science/article/pii/S2211124716302996) — open_web
- [https://www.sciencedirect.com/science/article/pii/S0923753426000992](https://www.sciencedirect.com/science/article/pii/S0923753426000992) — open_web
- [https://pubmed.ncbi.nlm.nih.gov/42321016/](https://pubmed.ncbi.nlm.nih.gov/42321016/) — open_web
- [https://ascopubs.org/doi/10.1200/JCO.2026.44.16_suppl.3115](https://ascopubs.org/doi/10.1200/JCO.2026.44.16_suppl.3115) — open_web
- [https://www.sciencedirect.com/science/article/pii/S0006295226003631](https://www.sciencedirect.com/science/article/pii/S0006295226003631) — open_web
- [https://digitalcommons.library.tmc.edu/utgsbs_dissertations/1290/](https://digitalcommons.library.tmc.edu/utgsbs_dissertations/1290/) — open_web
- [https://www.frontiersin.org/journals/cell-and-developmental-biology/articles/10.3389/fcell.2023.1173356/full](https://www.frontiersin.org/journals/cell-and-developmental-biology/articles/10.3389/fcell.2023.1173356/full) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC9346486/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9346486/) — open_web
- [https://www.tangotx.com/wp-content/uploads/Briggs_et_al_AACR2025_MTAP.pdf](https://www.tangotx.com/wp-content/uploads/Briggs_et_al_AACR2025_MTAP.pdf) — open_web
- [https://translational-medicine.biomedcentral.com/counter/pdf/10.1186/s12967-022-03823-8.pdf](https://translational-medicine.biomedcentral.com/counter/pdf/10.1186/s12967-022-03823-8.pdf) — open_web
- [https://sellerslab.org/wp-content/uploads/2020/07/Mavrakis2016.pdf](https://sellerslab.org/wp-content/uploads/2020/07/Mavrakis2016.pdf) — open_web
- [https://www.annualreviews.org/docserver/fulltext/pharmtox/66/1/annurev-pharmtox-062124-035809.pdf?accname=guest&checksum=B6B39C44FA02A2605E178BEB3901A5B9&expires=1778072472&id=id](https://www.annualreviews.org/docserver/fulltext/pharmtox/66/1/annurev-pharmtox-062124-035809.pdf?accname=guest&checksum=B6B39C44FA02A2605E178BEB3901A5B9&expires=1778072472&id=id) — open_web
- [https://watermark02.silverchair.com/neuro-oncology_25_s1_issue.pdf?token=AQECAHi208BE49Ooan9kkhW_Ercy7Dm3ZL_9Cf3qfKAc485ysgAAA2wwggNoBgkqhkiG9w0BBwagggNZMIIDVQIBADCCA04GCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQMVs8Ajv6uOkuUSxqKAgEQgIIDH4NI5EYr5dG9EjSrlbabvo1EIoUYSp_zQZM-ZbAmBLiyJYI6oztH1LdHFh8norHqq4wbNa5bWwIYAsmkoIg2o3ghGpnXIE6PFMad8sjkIVCj-uXQtm4ZXkndIvgl02ZtUXNd_MVm9ivvW-V3-X7LBIZnmDsPIrLg3LMLjX_koIxCKTHeQZrSc2d6KRKKafLFJwJQEaZdQysCbkB5Oh1E0PL7Q90zQG0p_TkZyIkUbuEU9Bg48KpveAkdDBQo6MNlPxOXn8mDCDGNUgf7mQvvmdcY5SWY5h1xUjKCKMk5U9-ngd40gK9L1q4qvw0HzPvyFRZjDGSDGE4wgnkWdb1eq6RqhtNq-r7p9oz04krTBRvg-XRA9LSaUy3hkRakgaSixpgn94fwhf1_kmWpYVXWnSAF-7OaaJo-pRW_9punPVVZ3dguN31z7LSe73CudlK6ikMe6e2KO6MKPJTeQHFtFXrlhmHJQ-fdWSJao5hCZ3RkI2iGUAxf6XbuyGFwcogL9z_ER7l_GsPG86lUty5XyxzwtYgtsUbYGQA6zGdrZ9Wef7Jpj1zxmSr09_UCyKJE-dK7I4wM-r5Lw8-rn70Qi8OARakJkcrvEzjq0NDFCxBxR7FVtikBP-xECFBIZhhQGmRiDY6FIKPzQh-7npP2L8Z3tMumXMkXg2LYs278mKeeN_XZ1LtQzNiAz5zhtprj6kNdugK3p80toZAFdSvNl6b-ReI0R2htA0kgFCVIBP06jEQnyOBW2kWKVDFXmlkRYh_hCeSu-RtDwT4zePwHRkN4X_3cXqIHdsbJXZNN08IGKPAo_biBYViC50za60tBWtiPeQf9_pvzgSVxj65r3nmGfnjasbQeS8CMtO9zKIWxIKPR0dnpZpiVEavXSgqK2jVbFIzJj5PCRp0RMaZJJxldhjasAoEklWbZ06JeKGZ_fR1ndoWrKoGNJ5TL4qfR-4ZYgr7T--tQr3I2legOcajHDDjrmz1SObjV6113rmfEc809-E-RwGzrL01IQAa6CtcCwNgRtBBZmCx5uL0gV02ZV3Jxx5rC59e07lW_3QI](https://watermark02.silverchair.com/neuro-oncology_25_s1_issue.pdf?token=AQECAHi208BE49Ooan9kkhW_Ercy7Dm3ZL_9Cf3qfKAc485ysgAAA2wwggNoBgkqhkiG9w0BBwagggNZMIIDVQIBADCCA04GCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQMVs8Ajv6uOkuUSxqKAgEQgIIDH4NI5EYr5dG9EjSrlbabvo1EIoUYSp_zQZM-ZbAmBLiyJYI6oztH1LdHFh8norHqq4wbNa5bWwIYAsmkoIg2o3ghGpnXIE6PFMad8sjkIVCj-uXQtm4ZXkndIvgl02ZtUXNd_MVm9ivvW-V3-X7LBIZnmDsPIrLg3LMLjX_koIxCKTHeQZrSc2d6KRKKafLFJwJQEaZdQysCbkB5Oh1E0PL7Q90zQG0p_TkZyIkUbuEU9Bg48KpveAkdDBQo6MNlPxOXn8mDCDGNUgf7mQvvmdcY5SWY5h1xUjKCKMk5U9-ngd40gK9L1q4qvw0HzPvyFRZjDGSDGE4wgnkWdb1eq6RqhtNq-r7p9oz04krTBRvg-XRA9LSaUy3hkRakgaSixpgn94fwhf1_kmWpYVXWnSAF-7OaaJo-pRW_9punPVVZ3dguN31z7LSe73CudlK6ikMe6e2KO6MKPJTeQHFtFXrlhmHJQ-fdWSJao5hCZ3RkI2iGUAxf6XbuyGFwcogL9z_ER7l_GsPG86lUty5XyxzwtYgtsUbYGQA6zGdrZ9Wef7Jpj1zxmSr09_UCyKJE-dK7I4wM-r5Lw8-rn70Qi8OARakJkcrvEzjq0NDFCxBxR7FVtikBP-xECFBIZhhQGmRiDY6FIKPzQh-7npP2L8Z3tMumXMkXg2LYs278mKeeN_XZ1LtQzNiAz5zhtprj6kNdugK3p80toZAFdSvNl6b-ReI0R2htA0kgFCVIBP06jEQnyOBW2kWKVDFXmlkRYh_hCeSu-RtDwT4zePwHRkN4X_3cXqIHdsbJXZNN08IGKPAo_biBYViC50za60tBWtiPeQf9_pvzgSVxj65r3nmGfnjasbQeS8CMtO9zKIWxIKPR0dnpZpiVEavXSgqK2jVbFIzJj5PCRp0RMaZJJxldhjasAoEklWbZ06JeKGZ_fR1ndoWrKoGNJ5TL4qfR-4ZYgr7T--tQr3I2legOcajHDDjrmz1SObjV6113rmfEc809-E-RwGzrL01IQAa6CtcCwNgRtBBZmCx5uL0gV02ZV3Jxx5rC59e07lW_3QI) — open_web
- [https://arxiv.org/abs/2205.12202](https://arxiv.org/abs/2205.12202) — open_web
- [https://arxiv.org/abs/1504.02816](https://arxiv.org/abs/1504.02816) — open_web
- [https://en.wikipedia.org/wiki/MTAP](https://en.wikipedia.org/wiki/MTAP) — open_web
- [https://arxiv.org/abs/1710.03268](https://arxiv.org/abs/1710.03268) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/1efi9zw/does_anyone_have_the_mutation_mtap_deletion/](https://www.reddit.com/r/pancreaticcancer/comments/1efi9zw/does_anyone_have_the_mutation_mtap_deletion/) — open_web
- [https://arxiv.org/abs/1703.07724](https://arxiv.org/abs/1703.07724) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/1u8831a/amgen_terminating_amg193_and_leaving_responding/](https://www.reddit.com/r/pancreaticcancer/comments/1u8831a/amgen_terminating_amg193_and_leaving_responding/) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/1ud0j1w/mtap_drug_trial/](https://www.reddit.com/r/pancreaticcancer/comments/1ud0j1w/mtap_drug_trial/) — open_web
- [https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html](https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html) — open_web
- [https://www.nlm.nih.gov/pubs/techbull/ja25/ja25_clinical_trials_screen-scraping.html](https://www.nlm.nih.gov/pubs/techbull/ja25/ja25_clinical_trials_screen-scraping.html) — open_web
- [https://catalog.data.gov/dataset/clinicaltrials-gov](https://catalog.data.gov/dataset/clinicaltrials-gov) — open_web
- [https://biotechhunter.com/trials/NCT05094336](https://biotechhunter.com/trials/NCT05094336) — open_web
- [https://cancer.ucsf.edu/_docs/trials/current_trials.pdf](https://cancer.ucsf.edu/_docs/trials/current_trials.pdf) — open_web
- [https://druglandscape.com/trial/NCT06810544](https://druglandscape.com/trial/NCT06810544) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC10741595/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10741595/) — open_web
- [https://www.volcengine.com/article/1250834](https://www.volcengine.com/article/1250834) — open_web
- [https://zingu.ai/apis/clinicaltrials.gov%3Aclinicaltrials.gov-api](https://zingu.ai/apis/clinicaltrials.gov%3Aclinicaltrials.gov-api) — open_web
- [https://public-pages-files-2025.frontiersin.org/journals/oncology/articles/10.3389/fonc.2023.1264785/pdf](https://public-pages-files-2025.frontiersin.org/journals/oncology/articles/10.3389/fonc.2023.1264785/pdf) — open_web
- [https://bioascend.com/wp-content/uploads/2025/11/19_Ardrshir_Atlanta-Lung_Final-2025v5.pdf](https://bioascend.com/wp-content/uploads/2025/11/19_Ardrshir_Atlanta-Lung_Final-2025v5.pdf) — open_web
- [https://www.ecommunity.com/sites/default/files/uploads/2024-09/Clinical-Trials-Open-Protocols-Oncology-091224.pdf](https://www.ecommunity.com/sites/default/files/uploads/2024-09/Clinical-Trials-Open-Protocols-Oncology-091224.pdf) — open_web
- [https://www.jpma.or.jp/information/evaluation/results/allotment/tcjmdm0000001m62-att/DS_202406_OSS.pdf](https://www.jpma.or.jp/information/evaluation/results/allotment/tcjmdm0000001m62-att/DS_202406_OSS.pdf) — open_web
- [https://www.reddit.com/r/mcp/comments/1ruy1te/clinical_trials_mcp_server_provides_programmatic/](https://www.reddit.com/r/mcp/comments/1ruy1te/clinical_trials_mcp_server_provides_programmatic/) — open_web
- [https://arxiv.org/abs/2603.15936](https://arxiv.org/abs/2603.15936) — open_web
- [https://www.reddit.com/r/mcp/comments/1rt44mj/plainyogurt21clintrialsmcp_provide_structured/](https://www.reddit.com/r/mcp/comments/1rt44mj/plainyogurt21clintrialsmcp_provide_structured/) — open_web
- [https://www.reddit.com/r/PowerBI/comments/1lag5ik](https://www.reddit.com/r/PowerBI/comments/1lag5ik) — open_web
- [https://arxiv.org/abs/2307.14522](https://arxiv.org/abs/2307.14522) — open_web
- [https://www.reddit.com/r/learnpython/comments/fy2b1q](https://www.reddit.com/r/learnpython/comments/fy2b1q) — open_web
- [https://www.reddit.com/r/ApoE4/comments/1unc6s1/i_got_tired_of_decoding_clinicaltrialsgov_so_i/](https://www.reddit.com/r/ApoE4/comments/1unc6s1/i_got_tired_of_decoding_clinicaltrialsgov_so_i/) — open_web
- [https://www.reddit.com/r/mcp/comments/1r1ho9k/medical_research_mcp_suite_enables_comprehensive/](https://www.reddit.com/r/mcp/comments/1r1ho9k/medical_research_mcp_suite_enables_comprehensive/) — open_web
- [https://www.reddit.com/r/RegulatoryClinWriting/comments/1u2ft8p/fda_sbia_presents_virtual_training_with_upcoming/](https://www.reddit.com/r/RegulatoryClinWriting/comments/1u2ft8p/fda_sbia_presents_virtual_training_with_upcoming/) — open_web
- [https://www.reddit.com/r/clinicalresearch/comments/1mcm9gj](https://www.reddit.com/r/clinicalresearch/comments/1mcm9gj) — open_web
- [https://www.reddit.com/r/RetatrutideTrial/comments/1suyu7l/arizona_research_center/](https://www.reddit.com/r/RetatrutideTrial/comments/1suyu7l/arizona_research_center/) — open_web
- [https://arxiv.org/abs/2512.08193](https://arxiv.org/abs/2512.08193) — open_web
- [https://www.reddit.com/r/clinicalresearch/comments/1iadac9/easier_search_for_clinicaltrialsgov/](https://www.reddit.com/r/clinicalresearch/comments/1iadac9/easier_search_for_clinicaltrialsgov/) — open_web
- [https://www.reddit.com/r/LeronLimab_Times/comments/12lgq2q](https://www.reddit.com/r/LeronLimab_Times/comments/12lgq2q) — open_web
- [https://www.reddit.com/r/clinicalresearch/comments/1kingas/clinicaltrialsgov_is_the_most_mindnumbingly_awful/](https://www.reddit.com/r/clinicalresearch/comments/1kingas/clinicaltrialsgov_is_the_most_mindnumbingly_awful/) — open_web
- [https://arxiv.org/abs/2405.07998](https://arxiv.org/abs/2405.07998) — open_web
- [https://clinicaltrials.gov/find-studies/how-to-search-for-studies-with-results](https://clinicaltrials.gov/find-studies/how-to-search-for-studies-with-results) — open_web
- [https://clinicaltrials.gov/study/NCT07277413](https://clinicaltrials.gov/study/NCT07277413) — open_web
- [https://clinicaltrials.gov/study/NCT02693717?a=6&tab=history](https://clinicaltrials.gov/study/NCT02693717?a=6&tab=history) — open_web
- [https://clinicaltrials.gov/study/NCT03744793](https://clinicaltrials.gov/study/NCT03744793) — open_web
- [https://cdn.clinicaltrials.gov/large-docs/81/NCT07536581/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/81/NCT07536581/Prot_000.pdf) — open_web
- [https://cdn.clinicaltrials.gov/large-docs/04/NCT04531904/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/04/NCT04531904/Prot_000.pdf) — open_web
- [https://cdn.clinicaltrials.gov/large-docs/19/NCT05303519/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/19/NCT05303519/Prot_000.pdf) — open_web
- [https://cdn.clinicaltrials.gov/large-docs/37/NCT04442737/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/37/NCT04442737/Prot_000.pdf) — open_web
- [https://clinicaltrials.med.nyu.edu/clinicaltrial/2430/phase-12-multi-center-open-label/](https://clinicaltrials.med.nyu.edu/clinicaltrial/2430/phase-12-multi-center-open-label/) — open_web
- [https://braintumorcenter.ucsf.edu/clinical-trial/phase-iii-multicenter-open-label-study-evaluate-safety-tolerability-and-preliminary](https://braintumorcenter.ucsf.edu/clinical-trial/phase-iii-multicenter-open-label-study-evaluate-safety-tolerability-and-preliminary) — open_web
- [https://www.clinicaltrialsregister.eu/ctr-search/trial/2021-005605-27/FR](https://www.clinicaltrialsregister.eu/ctr-search/trial/2021-005605-27/FR) — open_web
- [https://ckb.genomenon.com/clinicalTrial/show?nctId=NCT05275478](https://ckb.genomenon.com/clinicalTrial/show?nctId=NCT05275478) — open_web
- [https://www.invivochem.cn/TNG-908.html](https://www.invivochem.cn/TNG-908.html) — open_web
- [https://www.sec.gov/Archives/edgar/data/1819133/000095017025028353/tngx-20241231.htm](https://www.sec.gov/Archives/edgar/data/1819133/000095017025028353/tngx-20241231.htm) — open_web
- [https://fdaaa.trialstracker.net/trial/NCT05275478/](https://fdaaa.trialstracker.net/trial/NCT05275478/) — open_web
- [https://www.sec.gov/Archives/edgar/data/1819133/000119312526160323/d145279dars.pdf](https://www.sec.gov/Archives/edgar/data/1819133/000119312526160323/d145279dars.pdf) — open_web
- [https://www.reginfo.gov/public/do/DownloadDocument?objectID=128670501](https://www.reginfo.gov/public/do/DownloadDocument?objectID=128670501) — open_web
- [https://pryzm.ozmosi.com/product/25339](https://pryzm.ozmosi.com/product/25339) — open_web
- [https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2023.1152087/pdf](https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2023.1152087/pdf) — open_web
- [https://go.drugbank.com/drugs/DB17411/clinical_trials?conditions=DBCOND0012992%2CDBCOND0043840%2CDBCOND0091517%2CDBCOND0017375%2CDBCOND0026806%2CDBCOND0041813%2CDBCOND0029860&phase=1&purpose=treatment&status=active_not_recruiting](https://go.drugbank.com/drugs/DB17411/clinical_trials?conditions=DBCOND0012992%2CDBCOND0043840%2CDBCOND0091517%2CDBCOND0017375%2CDBCOND0026806%2CDBCOND0041813%2CDBCOND0029860&phase=1&purpose=treatment&status=active_not_recruiting) — open_web
- [https://scholarworks.indianapolis.iu.edu//bitstreams/bdf1e0b8-e595-4d21-8d45-fafd51e72333/download](https://scholarworks.indianapolis.iu.edu//bitstreams/bdf1e0b8-e595-4d21-8d45-fafd51e72333/download) — open_web
- [https://www.reddit.com/r/biotech_stocks/comments/1slffjp/genmab_gmab_stops_development_of_gen1047_after/](https://www.reddit.com/r/biotech_stocks/comments/1slffjp/genmab_gmab_stops_development_of_gen1047_after/) — open_web
- [https://www.reddit.com/r/biotech_stocks/comments/1q8iaue/vor_phase_3_marked_terminated_on_ctgov_business/](https://www.reddit.com/r/biotech_stocks/comments/1q8iaue/vor_phase_3_marked_terminated_on_ctgov_business/) — open_web
- [https://www.reddit.com/r/LeronLimab_Times/comments/zv860e](https://www.reddit.com/r/LeronLimab_Times/comments/zv860e) — open_web
- [https://www.reddit.com/r/biotech_stocks/comments/1qj43e3/bntx_bnt142_trial_in_cldn6_solid_tumors_now/](https://www.reddit.com/r/biotech_stocks/comments/1qj43e3/bntx_bnt142_trial_in_cldn6_solid_tumors_now/) — open_web
- [https://www.reddit.com/r/biotech_stocks/comments/1rqygza/eli_lilly_lly_terminates_phase_3_pediatric/](https://www.reddit.com/r/biotech_stocks/comments/1rqygza/eli_lilly_lly_terminates_phase_3_pediatric/) — open_web
- [https://www.reddit.com/r/Livimmune/comments/1ncp4c7](https://www.reddit.com/r/Livimmune/comments/1ncp4c7) — open_web
- [https://www.reddit.com/r/sellaslifesciences/comments/1ud12cx/ptcl_leukemia_data_due_june_30_from_genfleet/](https://www.reddit.com/r/sellaslifesciences/comments/1ud12cx/ptcl_leukemia_data_due_june_30_from_genfleet/) — open_web
- [https://www.reddit.com/r/clinicalresearch/comments/18o85w8](https://www.reddit.com/r/clinicalresearch/comments/18o85w8) — open_web
- [https://www.reddit.com/r/Zepbound/comments/1pwc9y3/clinical_trials_with_zepbound_and_similar/](https://www.reddit.com/r/Zepbound/comments/1pwc9y3/clinical_trials_with_zepbound_and_similar/) — open_web
- [https://www.reddit.com/r/clinicalresearch/comments/1jrkreu](https://www.reddit.com/r/clinicalresearch/comments/1jrkreu) — open_web
- [https://www.reddit.com/r/biotech/comments/1h7eyh1](https://www.reddit.com/r/biotech/comments/1h7eyh1) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC10172009/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10172009/) — open_web
- [https://ascopubs.org/doi/10.1200/JCO.2022.40.16_suppl.11548](https://ascopubs.org/doi/10.1200/JCO.2022.40.16_suppl.11548) — open_web
- [https://www.frontiersin.org/journals/medicine/articles/10.3389/fmed.2021.746909/full](https://www.frontiersin.org/journals/medicine/articles/10.3389/fmed.2021.746909/full) — open_web
- [https://www.sciencedirect.com/topics/medicine-and-dentistry/retinoblastoma-protein](https://www.sciencedirect.com/topics/medicine-and-dentistry/retinoblastoma-protein) — open_web
- [https://discovery.ucl.ac.uk/1457593/1/art_10.1007_s00428-014-1685-4.pdf](https://discovery.ucl.ac.uk/1457593/1/art_10.1007_s00428-014-1685-4.pdf) — open_web
- [https://www.pathologica.it/article/download/1368/1050/20087](https://www.pathologica.it/article/download/1368/1050/20087) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC10890624/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10890624/) — open_web
- [https://www.mdpi.com/2072-6694/17/16/2689](https://www.mdpi.com/2072-6694/17/16/2689) — open_web
- [https://www.researchgate.net/publication/333436807_Radiotherapy_resistance_in_chondrosarcoma_cells_a_possible_correlation_with_alterations_in_cell_cycle_related_genes](https://www.researchgate.net/publication/333436807_Radiotherapy_resistance_in_chondrosarcoma_cells_a_possible_correlation_with_alterations_in_cell_cycle_related_genes) — open_web
- [https://citeseerx.ist.psu.edu/document?doi=68b1333af93d6dce74de18107c5d3c0bfbab2df3&repid=rep1&type=pdf](https://citeseerx.ist.psu.edu/document?doi=68b1333af93d6dce74de18107c5d3c0bfbab2df3&repid=rep1&type=pdf) — open_web
- [https://aacrjournals.org/clincancerres/article/26/2/419/82764/Genomic-Profiling-Identifies-Association-of-IDH1](https://aacrjournals.org/clincancerres/article/26/2/419/82764/Genomic-Profiling-Identifies-Association-of-IDH1) — open_web
- [https://www.reddit.com/r/cancer/comments/1p2jgvx/it_came_back/](https://www.reddit.com/r/cancer/comments/1p2jgvx/it_came_back/) — open_web
- [https://en.wikipedia.org/wiki/Chordoma](https://en.wikipedia.org/wiki/Chordoma) — open_web
- [https://aacrjournals.org/clincancerres/article/19/14/3796/77820/Functional-Profiling-of-Receptor-Tyrosine-Kinases](https://aacrjournals.org/clincancerres/article/19/14/3796/77820/Functional-Profiling-of-Receptor-Tyrosine-Kinases) — open_web
- [https://www.mdpi.com/1422-0067/19/1/311/html](https://www.mdpi.com/1422-0067/19/1/311/html) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC10598203/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10598203/) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC13022607/](https://pmc.ncbi.nlm.nih.gov/articles/PMC13022607/) — open_web
- [https://f1000research.com/articles/7-1826/v1](https://f1000research.com/articles/7-1826/v1) — open_web
- [https://pubmed.ncbi.nlm.nih.gov/23922104/](https://pubmed.ncbi.nlm.nih.gov/23922104/) — open_web
- [https://jitc.bmj.com/content/14/5/e014346](https://jitc.bmj.com/content/14/5/e014346) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC12272896/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12272896/) — open_web
- [https://pubmed.ncbi.nlm.nih.gov/27429845/](https://pubmed.ncbi.nlm.nih.gov/27429845/) — open_web
- [https://aacrjournals.org/cancerres/article-abstract/69/15/6216/549925](https://aacrjournals.org/cancerres/article-abstract/69/15/6216/549925) — open_web
- [https://aacrjournals.org/cancerrescommun/article/doi/10.1158/2767-9764.CRC-25-0334/770330](https://aacrjournals.org/cancerrescommun/article/doi/10.1158/2767-9764.CRC-25-0334/770330) — open_web
- [https://pubmed.ncbi.nlm.nih.gov/18722108/](https://pubmed.ncbi.nlm.nih.gov/18722108/) — open_web
- [https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2021.772263/pdf](https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2021.772263/pdf) — open_web
- [https://mdpi-res.com/d_attachment/ijms/ijms-19-00311/article_deploy/ijms-19-00311.pdf?version=1516514419](https://mdpi-res.com/d_attachment/ijms/ijms-19-00311/article_deploy/ijms-19-00311.pdf?version=1516514419) — open_web
- [https://www.tandfonline.com/doi/pdf/10.1080/14737140.2019.1686979](https://www.tandfonline.com/doi/pdf/10.1080/14737140.2019.1686979) — open_web
- [https://d-nb.info/1170572707/34](https://d-nb.info/1170572707/34) — open_web
- [https://e-century.us/files/ajcr/13/7/ajcr0147677.pdf](https://e-century.us/files/ajcr/13/7/ajcr0147677.pdf) — open_web
- [https://www.tandfonline.com/doi/pdf/10.2217/fon-2016-0226](https://www.tandfonline.com/doi/pdf/10.2217/fon-2016-0226) — open_web
- [https://arxiv.org/abs/2307.07427](https://arxiv.org/abs/2307.07427) — open_web
- [https://arxiv.org/abs/1509.03642](https://arxiv.org/abs/1509.03642) — open_web
- [https://en.wikipedia.org/wiki/Palbociclib](https://en.wikipedia.org/wiki/Palbociclib) — open_web
- [https://en.wikipedia.org/wiki/CDK_inhibitor](https://en.wikipedia.org/wiki/CDK_inhibitor) — open_web
- [https://arxiv.org/abs/2012.00566](https://arxiv.org/abs/2012.00566) — open_web
- [https://en.wikipedia.org/wiki/Abemaciclib](https://en.wikipedia.org/wiki/Abemaciclib) — open_web
- [https://en.wikipedia.org/wiki/Tegtociclib](https://en.wikipedia.org/wiki/Tegtociclib) — open_web
- [https://en.wikipedia.org/wiki/G1_Therapeutics](https://en.wikipedia.org/wiki/G1_Therapeutics) — open_web
- [https://arxiv.org/abs/1308.6808](https://arxiv.org/abs/1308.6808) — open_web
- [https://www.reddit.com/r/breastcancer/comments/1p036pf](https://www.reddit.com/r/breastcancer/comments/1p036pf) — open_web
- [https://www.reddit.com/r/biotech/comments/1rwa3xy/pfizer_delivers_phase_2_win_in_2nd_line_er/](https://www.reddit.com/r/biotech/comments/1rwa3xy/pfizer_delivers_phase_2_win_in_2nd_line_er/) — open_web
- [https://www.reddit.com/r/LivingWithMBC/comments/1ru7gdd/cdk46s/](https://www.reddit.com/r/LivingWithMBC/comments/1ru7gdd/cdk46s/) — open_web
- [https://www.reddit.com/r/BANDOFBROTHERSOFSRNE/comments/1bc72nf](https://www.reddit.com/r/BANDOFBROTHERSOFSRNE/comments/1bc72nf) — open_web
- [https://en.wikipedia.org/wiki/Atirmociclib](https://en.wikipedia.org/wiki/Atirmociclib) — open_web
- [https://www.reddit.com/r/LivingWithMBC/comments/1m0mzpr/cdk_46s_side_effects/](https://www.reddit.com/r/LivingWithMBC/comments/1m0mzpr/cdk_46s_side_effects/) — open_web
- [https://www.reddit.com/r/LivingWithMBC/comments/1m4j4f6](https://www.reddit.com/r/LivingWithMBC/comments/1m4j4f6) — open_web
- [https://www.reddit.com/r/LivingWithMBC/comments/1iu6zyv](https://www.reddit.com/r/LivingWithMBC/comments/1iu6zyv) — open_web
- [https://www.reddit.com/r/LivingWithMBC/comments/1romazt/little_bit_of_a_vent/](https://www.reddit.com/r/LivingWithMBC/comments/1romazt/little_bit_of_a_vent/) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/1fr0ceq](https://www.reddit.com/r/pancreaticcancer/comments/1fr0ceq) — open_web
- [https://www.reddit.com/r/sellaslifesciences/comments/1ft4bl1](https://www.reddit.com/r/sellaslifesciences/comments/1ft4bl1) — open_web
- [https://www.reddit.com/r/breastcancer/comments/1pdkgfo/qualifying_for_cdk_46_inhibitor/](https://www.reddit.com/r/breastcancer/comments/1pdkgfo/qualifying_for_cdk_46_inhibitor/) — open_web
- [https://www.reddit.com/r/LivingWithMBC/comments/1jggots](https://www.reddit.com/r/LivingWithMBC/comments/1jggots) — open_web
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-darolutamide-metastatic-castration-sensitive-prostate-cancer](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-darolutamide-metastatic-castration-sensitive-prostate-cancer) — open_web
- [https://www.fda.gov/drugs/resources-information-approved-drugs/oncology-cancerhematologic-malignancies-approval-notifications](https://www.fda.gov/drugs/resources-information-approved-drugs/oncology-cancerhematologic-malignancies-approval-notifications) — open_web
- [https://www.fda.gov/drugs/resources-information-approved-drugs/verified-clinical-benefit-cancer-accelerated-approvals](https://www.fda.gov/drugs/resources-information-approved-drugs/verified-clinical-benefit-cancer-accelerated-approvals) — open_web
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-imlunestrant-er-positive-her2-negative-esr1-mutated-advanced-or-metastatic-breast](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-imlunestrant-er-positive-her2-negative-esr1-mutated-advanced-or-metastatic-breast) — open_web
- [https://investors.amgen.com/static-files/4e8e58ab-1e91-441e-94ea-4c8285338ec9](https://investors.amgen.com/static-files/4e8e58ab-1e91-441e-94ea-4c8285338ec9) — open_web
- [https://www.fda.gov/news-events/press-announcements/fda-approves-first-cellular-therapy-treat-patients-unresectable-or-metastatic-melanoma](https://www.fda.gov/news-events/press-announcements/fda-approves-first-cellular-therapy-treat-patients-unresectable-or-metastatic-melanoma) — open_web
- [https://investors.amgen.com/news-releases/news-release-details/c-o-r-r-e-c-t-i-o-n-amgen-0/](https://investors.amgen.com/news-releases/news-release-details/c-o-r-r-e-c-t-i-o-n-amgen-0/) — open_web
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-cabozantinib-adults-and-pediatric-patients-12-years-age-and-older-pnet-and-epnet](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-cabozantinib-adults-and-pediatric-patients-12-years-age-and-older-pnet-and-epnet) — open_web
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-belantamab-mafodotin-blmf-relapsed-or-refractory-multiple-myeloma](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-belantamab-mafodotin-blmf-relapsed-or-refractory-multiple-myeloma) — open_web
- [https://www.fda.gov/drugs/drug-approvals-and-databases/fda-approves-dostarlimab-gxly-chemotherapy-endometrial-cancer](https://www.fda.gov/drugs/drug-approvals-and-databases/fda-approves-dostarlimab-gxly-chemotherapy-endometrial-cancer) — open_web
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-two-separate-indications-fam-trastuzumab-deruxtecan-nxki-her2-positive-early-stage](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-two-separate-indications-fam-trastuzumab-deruxtecan-nxki-her2-positive-early-stage) — open_web
- [https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-mirvetuximab-soravtansine-gynx-fra-positive-platinum-resistant-epithelial-ovarian](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-mirvetuximab-soravtansine-gynx-fra-positive-platinum-resistant-epithelial-ovarian) — open_web
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2025/218881Orig1s000RiskR.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2025/218881Orig1s000RiskR.pdf) — open_web
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2025/761352Orig1s000RiskR.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2025/761352Orig1s000RiskR.pdf) — open_web
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2023/125514Orig1s065.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2023/125514Orig1s065.pdf) — open_web
- [https://www.accessdata.fda.gov/drugsatfda_docs/nda/2025/761404Orig2s000RiskR.pdf](https://www.accessdata.fda.gov/drugsatfda_docs/nda/2025/761404Orig2s000RiskR.pdf) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/1uhilma/as_much_as_we_want_to_continue_the_trial_the/](https://www.reddit.com/r/pancreaticcancer/comments/1uhilma/as_much_as_we_want_to_continue_the_trial_the/) — open_web
- [https://www.reddit.com/r/biotech/comments/1u88crg/amgen_terminating_amg193_and_leaving_responding/](https://www.reddit.com/r/biotech/comments/1u88crg/amgen_terminating_amg193_and_leaving_responding/) — open_web
- [https://www.reddit.com/r/clinicalresearch/comments/1u88bm3/amgen_terminating_amg193_and_leaving_responding/](https://www.reddit.com/r/clinicalresearch/comments/1u88bm3/amgen_terminating_amg193_and_leaving_responding/) — open_web
- [https://www.reddit.com/r/POTS/comments/1skzezn/amgen_has_discontinued_corlanor_what_now/](https://www.reddit.com/r/POTS/comments/1skzezn/amgen_has_discontinued_corlanor_what_now/) — open_web
- [https://www.reddit.com/r/Vitiligo/comments/1sy3i2f/povorcitinib_achieves_primary_endpoint_in_phase_3/](https://www.reddit.com/r/Vitiligo/comments/1sy3i2f/povorcitinib_achieves_primary_endpoint_in_phase_3/) — open_web
- [https://www.reddit.com/r/Vitiligo/comments/1t3hdux/amg_714_is_failed_in_trial_phase_2_pharma_amgen/](https://www.reddit.com/r/Vitiligo/comments/1t3hdux/amg_714_is_failed_in_trial_phase_2_pharma_amgen/) — open_web
- [https://www.reddit.com/r/RegulatoryClinWriting/comments/1qvh4b8/fda_has_requested_amgen_to_voluntarily_withdraw/](https://www.reddit.com/r/RegulatoryClinWriting/comments/1qvh4b8/fda_has_requested_amgen_to_voluntarily_withdraw/) — open_web
- [https://www.reddit.com/r/edgar_news/comments/1qr5l91/amgen_inc/](https://www.reddit.com/r/edgar_news/comments/1qr5l91/amgen_inc/) — open_web
- [https://www.reddit.com/r/EU_Economics/comments/1uguqfp/eu_regulator_backs_revoking_amgens_right_to_sell/](https://www.reddit.com/r/EU_Economics/comments/1uguqfp/eu_regulator_backs_revoking_amgens_right_to_sell/) — open_web
- [https://www.reddit.com/r/biotech/comments/1s4odac/removed/](https://www.reddit.com/r/biotech/comments/1s4odac/removed/) — open_web
- [https://www.reddit.com/r/biotech_stocks/comments/1toifcn/weekly_biotech_catalyst_rundown_may_26_to_june_15/](https://www.reddit.com/r/biotech_stocks/comments/1toifcn/weekly_biotech_catalyst_rundown_may_26_to_june_15/) — open_web
- [https://arxiv.org/abs/1106.1381](https://arxiv.org/abs/1106.1381) — open_web
- [https://arxiv.org/abs/2310.15456](https://arxiv.org/abs/2310.15456) — open_web
- [https://arxiv.org/abs/1102.0448](https://arxiv.org/abs/1102.0448) — open_web
- [https://clinicaltrials.gov/study/NCT00107419?aggFilters=studyType%3Aint&intr=PEMETREXED+DISODIUM&rank=4&viewType=Table](https://clinicaltrials.gov/study/NCT00107419?aggFilters=studyType%3Aint&intr=PEMETREXED+DISODIUM&rank=4&viewType=Table) — open_web
- [https://clinicaltrials.gov/study/NCT03420014](https://clinicaltrials.gov/study/NCT03420014) — open_web
- [https://clinicaltrials.gov/study/NCT06422806](https://clinicaltrials.gov/study/NCT06422806) — open_web
- [https://clinicaltrials.gov/study/NCT06156410](https://clinicaltrials.gov/study/NCT06156410) — open_web
- [https://clinicaltrials.gov/study/NCT06474676](https://clinicaltrials.gov/study/NCT06474676) — open_web
- [https://clinicaltrials.gov/study/NCT06156410?aggFilters=status%3Anot+rec+ava&cond=Ewing&rank=9&viewType=Table](https://clinicaltrials.gov/study/NCT06156410?aggFilters=status%3Anot+rec+ava&cond=Ewing&rank=9&viewType=Table) — open_web
- [https://clinicaltrials.gov/study/NCT06422806?a=23&tab=history](https://clinicaltrials.gov/study/NCT06422806?a=23&tab=history) — open_web
- [https://clinicaltrials.gov/study/NCT06277154?rank=8&term=AREA%5BBasicSearch%5D%28AREA%5BBasicSearch%5D%28AREA%5BConditionSearch%5D%28Desmoplastic+small+round+cell+tumor+OR+%22Desmoplas.+small+round+cell+tumor%22+OR+%22+Desmoplas.+small+round+cell+tumour%22+OR+%22+Desmoplastic+small+round+cell+tumour%22+OR+%22+Desmoplastic+small+round-cell+neoplasm%22+OR+%22+Desmoplastic+small+round-cell+tumor%22+OR+%22+Desmoplastic+small+round-cell+tumour%22+OR+%22+DSRCT%22+OR+%22+Polyphenotypic+small+round+cell+tumor%22+OR+%22+Polyphenotypic+small+round+cell+tumour%22%29+AND+AREA%5BOverallStatus%5D%28NOT_YET_RECRUITING+OR+RECRUITING%29%29%29](https://clinicaltrials.gov/study/NCT06277154?rank=8&term=AREA%5BBasicSearch%5D%28AREA%5BBasicSearch%5D%28AREA%5BConditionSearch%5D%28Desmoplastic+small+round+cell+tumor+OR+%22Desmoplas.+small+round+cell+tumor%22+OR+%22+Desmoplas.+small+round+cell+tumour%22+OR+%22+Desmoplastic+small+round+cell+tumour%22+OR+%22+Desmoplastic+small+round-cell+neoplasm%22+OR+%22+Desmoplastic+small+round-cell+tumor%22+OR+%22+Desmoplastic+small+round-cell+tumour%22+OR+%22+DSRCT%22+OR+%22+Polyphenotypic+small+round+cell+tumor%22+OR+%22+Polyphenotypic+small+round+cell+tumour%22%29+AND+AREA%5BOverallStatus%5D%28NOT_YET_RECRUITING+OR+RECRUITING%29%29%29) — open_web
- [https://clinicaltrials.gov/study/NCT04995003](https://clinicaltrials.gov/study/NCT04995003) — open_web
- [https://cdn.clinicaltrials.gov/large-docs/99/NCT05993299/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/99/NCT05993299/Prot_000.pdf) — open_web
- [https://cdn.clinicaltrials.gov/large-docs/66/NCT04118166/Prot_SAP_000.pdf](https://cdn.clinicaltrials.gov/large-docs/66/NCT04118166/Prot_SAP_000.pdf) — open_web
- [https://cdn.clinicaltrials.gov/large-docs/81/NCT02406781/Prot_000.pdf](https://cdn.clinicaltrials.gov/large-docs/81/NCT02406781/Prot_000.pdf) — open_web
- [https://cdn.clinicaltrials.gov/documents/FinalRuleChanges-12Dec2016.pdf](https://cdn.clinicaltrials.gov/documents/FinalRuleChanges-12Dec2016.pdf) — open_web
- [https://cdn.clinicaltrials.gov/large-docs/29/NCT04220229/Prot_SAP_001.pdf](https://cdn.clinicaltrials.gov/large-docs/29/NCT04220229/Prot_SAP_001.pdf) — open_web
- [https://www.nature.com/articles/s41586-026-10197-0](https://www.nature.com/articles/s41586-026-10197-0) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC11216722/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11216722/) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC7066089/](https://pmc.ncbi.nlm.nih.gov/articles/PMC7066089/) — open_web
- [https://aacrjournals.org/clincancerres/article/28/7/1412/682202/Pan-cancer-Analysis-of-Homologous-Recombination](https://aacrjournals.org/clincancerres/article/28/7/1412/682202/Pan-cancer-Analysis-of-Homologous-Recombination) — open_web
- [https://pmc.ncbi.nlm.nih.gov/articles/PMC9905963/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9905963/) — open_web
- [https://pubs.acs.org/doi/10.1021/jm500415t](https://pubs.acs.org/doi/10.1021/jm500415t) — open_web
- [https://pubmed.ncbi.nlm.nih.gov/37932012/](https://pubmed.ncbi.nlm.nih.gov/37932012/) — open_web
- [https://www.nature.com/articles/s41467-017-00921-w](https://www.nature.com/articles/s41467-017-00921-w) — open_web
- [https://www.ncbi.nlm.nih.gov/sites/books/NBK615090/](https://www.ncbi.nlm.nih.gov/sites/books/NBK615090/) — open_web
- [https://doi.org/10.1002/ctm2.70586](https://doi.org/10.1002/ctm2.70586) — open_web
- [https://www.sciencedirect.com/science/article/pii/S1098360024000340](https://www.sciencedirect.com/science/article/pii/S1098360024000340) — open_web
- [https://pubmed.ncbi.nlm.nih.gov/38091153/](https://pubmed.ncbi.nlm.nih.gov/38091153/) — open_web
- [https://www.nature.com/articles/s41586-026-10197-0.pdf](https://www.nature.com/articles/s41586-026-10197-0.pdf) — open_web
- [https://www.annualreviews.org/docserver/fulltext/med/76/1/annurev-med-082523-083843.pdf?accname=guest&checksum=B02C731A3A25F58B58C71E293524E2B9&expires=1781707269&id=id](https://www.annualreviews.org/docserver/fulltext/med/76/1/annurev-med-082523-083843.pdf?accname=guest&checksum=B02C731A3A25F58B58C71E293524E2B9&expires=1781707269&id=id) — open_web
- [https://minerva-access.unimelb.edu.au/rest/bitstreams/95b16e4c-b83e-4855-a866-506ea50e71d9/retrieve](https://minerva-access.unimelb.edu.au/rest/bitstreams/95b16e4c-b83e-4855-a866-506ea50e71d9/retrieve) — open_web
- [https://www.annualreviews.org/docserver/fulltext/med/76/1/annurev-med-082523-083843.pdf?accname=guest&checksum=A6C8BB393593827FD3828092F2427DE4&expires=1776305109&id=id](https://www.annualreviews.org/docserver/fulltext/med/76/1/annurev-med-082523-083843.pdf?accname=guest&checksum=A6C8BB393593827FD3828092F2427DE4&expires=1776305109&id=id) — open_web
- [https://eprints.gla.ac.uk/241726/1/241726.pdf](https://eprints.gla.ac.uk/241726/1/241726.pdf) — open_web
- [https://www.ncbi.nlm.nih.gov/books/NBK615090/pdf/Bookshelf_NBK615090.pdf](https://www.ncbi.nlm.nih.gov/books/NBK615090/pdf/Bookshelf_NBK615090.pdf) — open_web
- [https://en.wikipedia.org/wiki/Synthetic_lethality](https://en.wikipedia.org/wiki/Synthetic_lethality) — open_web
- [https://arxiv.org/abs/2602.00151](https://arxiv.org/abs/2602.00151) — open_web
- [https://arxiv.org/abs/1602.00096](https://arxiv.org/abs/1602.00096) — open_web
- [https://arxiv.org/abs/1510.00815](https://arxiv.org/abs/1510.00815) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/1rfzlul/thoughts_on_kras_g12d_parp_synthetic_lethality/](https://www.reddit.com/r/pancreaticcancer/comments/1rfzlul/thoughts_on_kras_g12d_parp_synthetic_lethality/) — open_web
- [https://arxiv.org/abs/1406.6557](https://arxiv.org/abs/1406.6557) — open_web
- [https://www.reddit.com/r/breastcancer/comments/y1jmz0](https://www.reddit.com/r/breastcancer/comments/y1jmz0) — open_web
- [https://www.reddit.com/r/breastcancer/comments/13fmqqx](https://www.reddit.com/r/breastcancer/comments/13fmqqx) — open_web
- [https://www.reddit.com/r/breastcancer/comments/1ifsvpv](https://www.reddit.com/r/breastcancer/comments/1ifsvpv) — open_web
- [https://www.reddit.com/r/BRCA/comments/1u0g6cp/olaparib/](https://www.reddit.com/r/BRCA/comments/1u0g6cp/olaparib/) — open_web
- [https://www.reddit.com/r/Ovariancancer/comments/1s4ehzp/forgoing_parps_in_stage_3_hgsoc/](https://www.reddit.com/r/Ovariancancer/comments/1s4ehzp/forgoing_parps_in_stage_3_hgsoc/) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/183iep2](https://www.reddit.com/r/pancreaticcancer/comments/183iep2) — open_web
- [https://www.reddit.com/r/Ovariancancer/comments/1usuubv/no_maintenance_therapy_suggested_brcanegative/](https://www.reddit.com/r/Ovariancancer/comments/1usuubv/no_maintenance_therapy_suggested_brcanegative/) — open_web
- [https://www.reddit.com/r/Biotechplays/comments/l0a8yu](https://www.reddit.com/r/Biotechplays/comments/l0a8yu) — open_web
- [https://www.reddit.com/r/pancreaticcancer/comments/1r9fftw/highrisk_pathology_ned_on_ct_folfirinox_extension/](https://www.reddit.com/r/pancreaticcancer/comments/1r9fftw/highrisk_pathology_ned_on_ct_folfirinox_extension/) — open_web
- [https://www.reddit.com/r/lungcancer/comments/1swmse1/target_therapy_treatment_options_brca2_or_met_amp/](https://www.reddit.com/r/lungcancer/comments/1swmse1/target_therapy_treatment_options_brca2_or_met_amp/) — open_web
- [https://www.reddit.com/r/BRCA/comments/1esjsa5](https://www.reddit.com/r/BRCA/comments/1esjsa5) — open_web
- [https://clinicaltrials.gov/study/NCT05094336?utm_source=openai](https://clinicaltrials.gov/study/NCT05094336?utm_source=openai) — open_web
- [https://clinicaltrials.gov/study/NCT05094336?a=53&tab=history&utm_source=openai](https://clinicaltrials.gov/study/NCT05094336?a=53&tab=history&utm_source=openai) — open_web
