---
license: apache-2.0
language:
- en
tags:
- chemistry
pretty_name: medea_db
---

# MEDEA-DB 

This database contains curated databases and pre-trained model weights across multiple domains of tools leveraged by Medea, including:

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

## Data Sources & Citations

Please cite the original sources when using specific datasets or models.

---

## License

This dataset is released under the [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) license.