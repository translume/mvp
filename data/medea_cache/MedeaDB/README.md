---
license: cc-by-nc-sa-4.0
language:
- en
tags:
- chemistry
pretty_name: medea_db
---

# MEDEA-DB 
**MEDEA-DB** is the curated data and model release accompanying **Medea: An AI agent for therapeutic reasoning across biological contexts**. It contains the databases, pre-trained embeddings, and model checkpoints used by Medea across its tool space.

🔗 **Links**
- 📄 **Paper (bioRxiv):** https://www.biorxiv.org/content/10.64898/2026.01.16.696667  <!-- replace with the DOI on your Version 2 submission page (BIORXIV/2025/696667) -->
- 💻 **Code (GitHub):** https://github.com/mims-harvard/Medea
- 🌐 **Project website:** https://medea.openscientist.ai
- 🧬 **Yeast E-MAP screen (Figshare):** https://doi.org/10.6084/m9.figshare.32782446

This repository contains curated databases and pre-trained model weights across multiple domains of tools leveraged by Medea, including:

- PPI networks & Multi-scale gene/protein embeddings (PINNACLE, TranscriptFormer, etc.)
- Gene correlation and dependency statistics (Chronos gene-effect profiles from DepMap 24Q2 CRISPR)
- Immunotherapy response prediction model checkpoints (COMPASS pretrain checkpoint)

---

## Available Data & Resources

### 1. Gene/Protein Embeddings

#### **PINNACLE Embeddings** (`pinnacle_embeds/`)
- **Model**: PINNACLE
- **Files**:
  - `pinnacle_protein_embed.pth`: Protein-level embeddings with cell type specificity
  - `pinnacle_mg_embed.pth`: Meta-graph level embeddings on cellular interactions and tissue hierarchy
  - `ppi_embed_dict.pth`: PPI-based embeddings
  - `pinnacle_labels_dict.txt`: Gene/protein labels
- **Config Names**: `pinnacle_protein_embed`, `labels_dict`
- **Format**: PyTorch tensors

#### **Transcriptformer Embeddings** (`transcriptformer_embedding/`)
- **Model**: Transcriptformer (Transcriptomics transformer)
- **Structure**:
  - `embedding_generation/`: Scripts for generating embeddings
  - `embedding_store/`: Pre-computed embeddings (138 `.npy` files)
- **Format**: NumPy arrays, compressed archives

---

### 2. Gene Dependency & Correlation Data

#### **DepMap 24Q2** (`depmap_24q2/`)
- **Release**: DepMap Public 24Q2
- **Files**:
  - `corr_matrix.npy`: Gene correlation matrix
  - `p_val_matrix.npy`: Statistical significance values
  - `p_adj_matrix.npy`: Adjusted p-values (multiple testing correction)
  - `gene_correlations.h5`: HDF5 format correlations
  - `gene_idx_array.npy`: Gene index mappings
  - `gene_names.txt`: Gene identifiers

---

### 3. Immunotherapy Response Prediction Models

#### **COMPASS Checkpoints** (`compass/checkpoint/`)
- **Model**: COMPASS
- **Checkpoints**:
  - `pretrainer.pt`: Pre-trained base model
  - `pft_leave_IMVigor210.pt`: Leave-one-cohort-out (IMVigor210) fintuned model   

---

## Citation

If you use MEDEA-DB or Medea in your work, please cite:

```bibtex
@article {Sui2026.01.16.696667,
	author = {Sui, Pengwei and Li, Michelle and Munson, Brenton P. and Gao, Shanghua and Shen, Wanxiang and Giunchiglia, Valentina and Shen, Andrew and Huang, Yepeng and Kong, Zhenglun and Licon, Katherine and Ideker, Trey and Zitnik, Marinka},
	title = {Medea: An AI agent for therapeutic reasoning across biological contexts},
	year = {2026},
	doi = {10.64898/2026.01.16.696667},
	URL = {https://www.biorxiv.org/content/10.64898/2026.01.16.696667},
	journal = {bioRxiv}
}
```

Please also cite the original sources of any specific dataset or model you use (PINNACLE, TranscriptFormer, DepMap, COMPASS, etc.).

---

## License

This dataset is released under the [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) license.