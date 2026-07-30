<p align="center">
  <img src="https://raw.githubusercontent.com/AtlasAnalyticsLab/AtlasPatch/main/assets/images/Logo.png" alt="AtlasPatch Logo" width="100%">
</p>

# AtlasPatch: Efficient Tissue Detection and High-throughput Patch Extraction for Computational Pathology at Scale

<p align="center">
  <a href="https://pypi.org/project/atlas-patch/"><img alt="PyPI" src="https://img.shields.io/pypi/v/atlas-patch"></a>
  <a href="https://pypi.org/project/atlas-patch/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/atlas-patch"></a>
  <a href="https://huggingface.co/AtlasAnalyticsLab/AtlasPatch"><img src="https://img.shields.io/badge/%F0%9F%A4%97%20HuggingFace-Model-yellow" alt="HuggingFace"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/License-CC--BY--NC--SA--4.0-blue"></a>
</p>

<p align="center">
  <a href="https://atlasanalyticslab.github.io/AtlasPatch/"><b>Project Page</b></a> |
  <a href="https://arxiv.org/abs/2602.03998"><b>Paper</b></a> |
  <a href="https://huggingface.co/AtlasAnalyticsLab/AtlasPatch"><b>Hugging Face</b></a> |
  <a href="https://github.com/AtlasAnalyticsLab/AtlasPatch"><b>GitHub</b></a>
</p>

## Table of Contents
- [Installation](#installation)
  - [1. Install OpenSlide](#1-install-openslide)
  - [2. Install AtlasPatch](#2-install-atlaspatch)
  - [3. Install SAM2](#3-install-sam2)
  - [Optional extras](#optional-extras)
  - [Alternative Installation Methods](#alternative-installation-methods)
- [Usage Guide](#usage-guide)
  - [Choose a Command](#choose-a-command)
  - [Quick Start](#quick-start)
    - [Full patch pipeline](#full-patch-pipeline)
    - [Slide encoding](#slide-encoding)
    - [Patient encoding](#patient-encoding)
  - [Supported Inputs](#supported-inputs)
  - [Visualization Samples](#visualization-samples)
- [Encoders](#encoders)
  - [Available Patch Feature Extractors](#available-patch-feature-extractors)
    - [Core vision backbones on Natural Images](#core-vision-backbones-on-natural-images)
    - [Medical- and Pathology-Specific Vision Encoders](#medical--and-pathology-specific-vision-encoders)
    - [CLIP-like models](#clip-like-models)
      - [Natural Images](#natural-images)
      - [Medical- and Pathology-Specific CLIP](#medical--and-pathology-specific-clip)
    - [Bring Your Own Encoder](#bring-your-own-encoder)
  - [Available Slide Encoders](#available-slide-encoders)
  - [Available Patient Encoders](#available-patient-encoders)
- [Output Files](#output-files)
  - [What AtlasPatch writes](#what-atlaspatch-writes)
    - [Per-Slide H5 files](#per-slide-h5-files)
    - [Patient embedding files](#patient-embedding-files)
    - [Optional image outputs](#optional-image-outputs)
  - [Reading the files](#reading-the-files)
    - [Patch coordinates](#patch-coordinates)
    - [Patch feature matrices](#patch-feature-matrices)
    - [Slide embeddings](#slide-embeddings)
    - [Patient embeddings](#patient-embeddings)
- [Orchestration at cohort scale](#orchestration-at-cohort-scale)
- [SLURM job scripts](#slurm-job-scripts)
- [Frequently Asked Questions (FAQ)](#frequently-asked-questions-faq)
- [Feedback](#feedback)
- [Citation](#citation)
- [License](#license)

## Installation

AtlasPatch targets Python 3.10+.

<a id="openslide-prerequisites"></a>

### 1. Install OpenSlide

AtlasPatch needs the OpenSlide system library before you install the Python package.

```bash
# conda
conda install -c conda-forge openslide

# Ubuntu / Debian
sudo apt-get install openslide-tools

# macOS
brew install openslide
```

### 2. Install AtlasPatch

```bash
pip install atlas-patch
```

### 3. Install SAM2

All WSI-facing AtlasPatch commands use SAM2 for tissue segmentation.

```bash
pip install git+https://github.com/facebookresearch/sam2.git
```

### Optional extras

The default install stays lean. Install only the model stacks you need.

| Use case | Install |
| --- | --- |
| Broader built-in patch encoder registry | `pip install "atlas-patch[patch-encoders]"` |
| TITAN slide encoding | `pip install "atlas-patch[titan]"` |
| PRISM slide encoding | `pip install "atlas-patch[prism]"` |
| MOOZY slide or patient encoding | `pip install "atlas-patch[moozy]"` |
| All bundled slide encoder extras | `pip install "atlas-patch[slide-encoders]"` |
| All bundled patient encoder extras | `pip install "atlas-patch[patient-encoders]"` |

Some patch encoders still require upstream project packages in addition to `atlas-patch[patch-encoders]`:

```bash
# Optional: CONCH patch encoders
pip install git+https://github.com/MahmoodLab/CONCH.git

# Optional: MUSK patch encoder
pip install git+https://github.com/lilab-stanford/MUSK.git
```

### Alternative Installation Methods

<details>
<summary><b>Using Conda Environment</b></summary>

```bash
# Create and activate environment
conda create -n atlas_patch python=3.10
conda activate atlas_patch

# Install OpenSlide
conda install -c conda-forge openslide

# Install AtlasPatch and SAM2
pip install atlas-patch
pip install git+https://github.com/facebookresearch/sam2.git
```

</details>

<details>
<summary><b>Using uv</b></summary>

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create and activate environment
uv venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate

# Install AtlasPatch and SAM2
uv pip install atlas-patch
uv pip install git+https://github.com/facebookresearch/sam2.git
```

</details>

## Usage Guide

AtlasPatch provides a flexible pipeline with **4 checkpoints** that you can use independently or combine based on your needs.

<p align="center">
  <img src="https://raw.githubusercontent.com/AtlasAnalyticsLab/AtlasPatch/main/assets/images/Checkouts.png" alt="AtlasPatch Pipeline Checkpoints" width="100%">
</p>

### Choose a Command

| Command | Use it when | Main outputs | Docs |
| --- | --- | --- | --- |
| `detect-tissue` | You only need tissue masks and overlays | `visualization/` | [docs/commands/detect-tissue.md](docs/commands/detect-tissue.md) |
| `segment-and-get-coords` | You want patch locations now and feature extraction later | `patches/<stem>.h5` | [docs/commands/segment-and-get-coords.md](docs/commands/segment-and-get-coords.md) |
| `process` | You want the full patch pipeline, including patch features | `patches/<stem>.h5`, optional `images/`, optional `visualization/` | [docs/commands/process.md](docs/commands/process.md) |
| `encode-slide` | You want slide embeddings added to each slide H5 file | `patches/<stem>.h5` with `slide_features/<encoder>` | [docs/commands/encode-slide.md](docs/commands/encode-slide.md) |
| `encode-patient` | You have a CSV file that lists which slides belong to each patient | `patient_features/<encoder>/<case_id>.h5` | [docs/commands/encode-patient.md](docs/commands/encode-patient.md) |

### Quick Start

#### Full patch pipeline

```bash
atlaspatch process /path/to/slide.svs \
  --output ./output \
  --patch-size 256 \
  --target-mag 20 \
  --feature-extractors uni_v2 \
  --device cuda
```

This writes a per-slide H5 file at `./output/patches/slide.h5` with:

- `coords`
- `features/uni_v2`
- slide metadata in file attributes

#### Slide encoding

```bash
atlaspatch encode-slide /path/to/slides \
  --output ./output \
  --slide-encoders titan \
  --patch-size 512 \
  --target-mag 20 \
  --device cuda
```

`encode-slide` is WSI-only. It creates or reuses the per-slide patch H5, backfills the required upstream patch features automatically, and appends slide embeddings into the same file.

See [Available Slide Encoders](#available-slide-encoders) for the built-in encoder list, requirements, and install extras.

If you want multiple slide encoders in one run, they must be compatible with one patch geometry. For example, `titan` and `prism` need different patch sizes, so they should be run separately.

#### Patient encoding

Create a CSV file:

```csv
case_id,slide_path,mpp
case-001,/data/case-001-slide-a.svs,0.25
case-001,/data/case-001-slide-b.svs,
case-002,/data/case-002-slide-a.svs,
```

Then run:

```bash
atlaspatch encode-patient cases.csv \
  --output ./output \
  --patient-encoders moozy \
  --patch-size 224 \
  --target-mag 20 \
  --device cuda
```

`encode-patient` groups slides by `case_id`, creates or reuses per-slide H5 files, ensures the required patch features exist, and writes one patient embedding per case.

See [Available Patient Encoders](#available-patient-encoders) for the built-in encoder list, requirements, and install extras.

### Supported Inputs

From `atlaspatch info`:

- WSI formats: `.svs`, `.tif`, `.tiff`, `.ndpi`, `.vms`, `.vmu`, `.scn`, `.mrxs`, `.bif`, `.dcm`
- image formats: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.gif`

### Visualization Samples

Below are some examples for the output masks and overlays (original image, predicted mask, overlay, contours, grid).

<p align="center">
  <img src="https://raw.githubusercontent.com/AtlasAnalyticsLab/AtlasPatch/main/assets/images/VisualizationSamples.png" alt="AtlasPatch visualization samples" width="100%">
</p>

Quantitative and qualitative analysis of AtlasPatch tissue detection against existing slide-preprocessing tools.

<p align="center">
  <img src="https://raw.githubusercontent.com/AtlasAnalyticsLab/AtlasPatch/main/assets/images/Comparisons.jpg" alt="AtlasPatch method comparison" width="100%">
</p>

Representative WSI thumbnails are shown from diverse tissue features and artifact conditions, with tissue masks predicted by thresholding methods (TIAToolbox, CLAM) and deep learning methods (pretrained "non-finetuned" SAM2 model, Trident-QC, Trident-Hest and AtlasPatch), highlighting differences in boundary fidelity, artifact suppression and handling of fragmented tissue. Tissue detection performance is also shown on the held-out test set for AtlasPatch and baseline pipelines, highlighting that AtlasPatch matches or exceeds their segmentation quality. The segmentation complexity–performance trade-off, plotting F1-score against segmentation runtime (on a random set of 100 WSIs), shows AtlasPatch achieves high performance with substantially lower wall-clock time than tile-wise detectors and heuristic pipelines, underscoring its suitability for large-scale WSI preprocessing.

## Encoders

### Available Patch Feature Extractors

#### Core vision backbones on Natural Images

| Name | Output Dim |
| --- | --- |
| `resnet18` | 512 |
| `resnet34` | 512 |
| `resnet50` | 2048 |
| `resnet101` | 2048 |
| `resnet152` | 2048 |
| `convnext_tiny` | 768 |
| `convnext_small` | 768 |
| `convnext_base` | 1024 |
| `convnext_large` | 1536 |
| `vit_b_16` | 768 |
| `vit_b_32` | 768 |
| `vit_l_16` | 1024 |
| `vit_l_32` | 1024 |
| `vit_h_14` | 1280 |
| [`dinov2_small`](https://huggingface.co/facebook/dinov2-small) ([DINOv2: Learning Robust Visual Features without Supervision](https://arxiv.org/abs/2304.07193)) | 384 |
| [`dinov2_base`](https://huggingface.co/facebook/dinov2-base) ([DINOv2: Learning Robust Visual Features without Supervision](https://arxiv.org/abs/2304.07193)) | 768 |
| [`dinov2_large`](https://huggingface.co/facebook/dinov2-large) ([DINOv2: Learning Robust Visual Features without Supervision](https://arxiv.org/abs/2304.07193)) | 1024 |
| [`dinov2_giant`](https://huggingface.co/facebook/dinov2-giant) ([DINOv2: Learning Robust Visual Features without Supervision](https://arxiv.org/abs/2304.07193)) | 1536 |
| [`dinov3_vits16`](https://huggingface.co/facebook/dinov3-vits16-pretrain-lvd1689m) ([DINOv3](https://arxiv.org/abs/2508.10104)) | 384 |
| [`dinov3_vits16_plus`](https://huggingface.co/facebook/dinov3-vits16plus-pretrain-lvd1689m) ([DINOv3](https://arxiv.org/abs/2508.10104)) | 384 |
| [`dinov3_vitb16`](https://huggingface.co/facebook/dinov3-vitb16-pretrain-lvd1689m) ([DINOv3](https://arxiv.org/abs/2508.10104)) | 768 |
| [`dinov3_vitl16`](https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m) ([DINOv3](https://arxiv.org/abs/2508.10104)) | 1024 |
| [`dinov3_vitl16_sat`](https://huggingface.co/facebook/dinov3-vitl16-pretrain-sat493m) ([DINOv3](https://arxiv.org/abs/2508.10104)) | 1024 |
| [`dinov3_vith16_plus`](https://huggingface.co/facebook/dinov3-vith16plus-pretrain-lvd1689m) ([DINOv3](https://arxiv.org/abs/2508.10104)) | 1280 |
| [`dinov3_vit7b16`](https://huggingface.co/facebook/dinov3-vit7b16-pretrain-lvd1689m) ([DINOv3](https://arxiv.org/abs/2508.10104)) | 4096 |
| [`dinov3_vit7b16_sat`](https://huggingface.co/facebook/dinov3-vit7b16-pretrain-sat493m) ([DINOv3](https://arxiv.org/abs/2508.10104)) | 4096 |

#### Medical- and Pathology-Specific Vision Encoders

| Name | Output Dim |
| --- | --- |
| [`uni_v1`](https://huggingface.co/MahmoodLab/UNI) ([Towards a General-Purpose Foundation Model for Computational Pathology](https://www.nature.com/articles/s41591-024-02857-3)) | 1024 |
| [`uni_v2`](https://huggingface.co/MahmoodLab/UNI2-h) ([Towards a General-Purpose Foundation Model for Computational Pathology](https://www.nature.com/articles/s41591-024-02857-3)) | 1536 |
| [`phikon_v1`](https://huggingface.co/owkin/phikon) ([Scaling Self-Supervised Learning for Histopathology with Masked Image Modeling](https://www.medrxiv.org/content/10.1101/2023.07.21.23292757v1)) | 768 |
| [`phikon_v2`](https://huggingface.co/owkin/phikon-v2) ([Phikon-v2, A large and public feature extractor for biomarker prediction](https://arxiv.org/abs/2409.09173)) | 1024 |
| [`virchow_v1`](https://huggingface.co/paige-ai/Virchow) ([Virchow: A Million-Slide Digital Pathology Foundation Model](https://arxiv.org/abs/2309.07778)) | 2560 |
| [`virchow_v2`](https://huggingface.co/paige-ai/Virchow2) ([Virchow2: Scaling Self-Supervised Mixed Magnification Models in Pathology](https://arxiv.org/abs/2408.00738)) | 2560 |
| [`prov_gigapath`](https://huggingface.co/prov-gigapath/prov-gigapath) ([A whole-slide foundation model for digital pathology from real-world data](https://www.nature.com/articles/s41586-024-07441-w)) | 1536 |
| [`chief-ctranspath`](https://github.com/hms-dbmi/CHIEF?tab=readme-ov-file) ([CHIEF: Clinical Histopathology Imaging Evaluation Foundation Model](https://www.nature.com/articles/s41586-024-07894-z)) | 768 |
| [`midnight`](https://huggingface.co/kaiko-ai/midnight) ([Training state-of-the-art pathology foundation models with orders of magnitude less data](https://arxiv.org/abs/2504.05186)) | 3072 |
| [`musk`](https://github.com/lilab-stanford/MUSK) ([MUSK: A Vision-Language Foundation Model for Precision Oncology](https://www.nature.com/articles/s41586-024-08378-w)) | 1024 |
| [`openmidnight`](https://sophontai.com/blog/openmidnight) ([How to Train a State-of-the-Art Pathology Foundation Model with $1.6k](https://sophontai.com/blog/openmidnight)) | 1536 |
| [`pathorchestra`](https://huggingface.co/AI4Pathology/PathOrchestra) ([PathOrchestra: A Comprehensive Foundation Model for Computational Pathology with Over 100 Diverse Clinical-Grade Tasks](https://arxiv.org/abs/2503.24345)) | 1024 |
| [`h_optimus_0`](https://huggingface.co/bioptimus/H-optimus-0) | 1536 |
| [`h_optimus_1`](https://huggingface.co/bioptimus/H-optimus-1) | 1536 |
| [`h0_mini`](https://huggingface.co/bioptimus/H0-mini) ([Distilling foundation models for robust and efficient models in digital pathology](https://doi.org/10.48550/arXiv.2501.16239)) | 1536 |
| [`conch_v1`](https://huggingface.co/MahmoodLab/CONCH) ([A visual-language foundation model for computational pathology](https://www.nature.com/articles/s41591-024-02856-4)) | 512 |
| [`conch_v15`](https://huggingface.co/MahmoodLab/conchv1_5) - [From TITAN](https://huggingface.co/MahmoodLab/TITAN) ([A multimodal whole-slide foundation model for pathology](https://www.nature.com/articles/s41591-025-03982-3)) | 768 |
| [`hibou_b`](https://huggingface.co/histai/hibou-B) ([Hibou: A Family of Foundational Vision Transformers for Pathology](https://arxiv.org/abs/2406.05074)) | 768 |
| [`hibou_l`](https://huggingface.co/histai/hibou-L) ([Hibou: A Family of Foundational Vision Transformers for Pathology](https://arxiv.org/abs/2406.05074)) | 1024 |
| [`lunit_resnet50_bt`](https://huggingface.co/1aurent/resnet50.lunit_bt) ([Benchmarking Self-Supervised Learning on Diverse Pathology Datasets](https://openaccess.thecvf.com/content/CVPR2023/papers/Kang_Benchmarking_Self-Supervised_Learning_on_Diverse_Pathology_Datasets_CVPR_2023_paper.pdf)) | 2048 |
| [`lunit_resnet50_swav`](https://huggingface.co/1aurent/resnet50.lunit_swav) ([Benchmarking Self-Supervised Learning on Diverse Pathology Datasets](https://openaccess.thecvf.com/content/CVPR2023/papers/Kang_Benchmarking_Self-Supervised_Learning_on_Diverse_Pathology_Datasets_CVPR_2023_paper.pdf)) | 2048 |
| [`lunit_resnet50_mocov2`](https://huggingface.co/1aurent/resnet50.lunit_mocov2) ([Benchmarking Self-Supervised Learning on Diverse Pathology Datasets](https://openaccess.thecvf.com/content/CVPR2023/papers/Kang_Benchmarking_Self-Supervised_Learning_on_Diverse_Pathology_Datasets_CVPR_2023_paper.pdf)) | 2048 |
| [`lunit_vit_small_patch16_dino`](https://huggingface.co/1aurent/vit_small_patch16_224.lunit_dino) ([Benchmarking Self-Supervised Learning on Diverse Pathology Datasets](https://openaccess.thecvf.com/content/CVPR2023/papers/Kang_Benchmarking_Self-Supervised_Learning_on_Diverse_Pathology_Datasets_CVPR_2023_paper.pdf)) | 384 |
| [`lunit_vit_small_patch8_dino`](https://huggingface.co/1aurent/vit_small_patch8_224.lunit_dino) ([Benchmarking Self-Supervised Learning on Diverse Pathology Datasets](https://openaccess.thecvf.com/content/CVPR2023/papers/Kang_Benchmarking_Self-Supervised_Learning_on_Diverse_Pathology_Datasets_CVPR_2023_paper.pdf)) | 384 |

> **Note:** Some encoders (e.g., `uni_v1`, etc.) require access approval from Hugging Face. To use these models:
> 1. Request access on the respective Hugging Face model page
> 2. Once approved, set your Hugging Face token as an environment variable:
>    ```bash
>    export HF_TOKEN=your_huggingface_token
>    ```
> 3. Then you can use the encoder in your commands

#### CLIP-like models

##### Natural Images

| Name | Output Dim |
| --- | --- |
| `clip_rn50` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 1024 |
| `clip_rn101` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 512 |
| `clip_rn50x4` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 640 |
| `clip_rn50x16` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 768 |
| `clip_rn50x64` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 1024 |
| `clip_vit_b_32` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 512 |
| `clip_vit_b_16` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 512 |
| `clip_vit_l_14` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 768 |
| `clip_vit_l_14_336` ([Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020)) | 768 |

##### Medical- and Pathology-Specific CLIP

| Name | Output Dim |
| --- | --- |
| [`plip`](https://github.com/PathologyFoundation/plip) ([Pathology Language and Image Pre-Training (PLIP)](https://www.nature.com/articles/s41591-023-02504-3)) | 512 |
| [`medsiglip`](https://huggingface.co/google/medsiglip-448) ([MedGemma Technical Report](https://arxiv.org/abs/2507.05201)) | 1152 |
| [`quilt_b_32`](https://quilt1m.github.io/) ([Quilt-1M: One Million Image-Text Pairs for Histopathology](https://arxiv.org/pdf/2306.11207)) | 512 |
| [`quilt_b_16`](https://quilt1m.github.io/) ([Quilt-1M: One Million Image-Text Pairs for Histopathology](https://arxiv.org/pdf/2306.11207)) | 512 |
| [`quilt_b_16_pmb`](https://quilt1m.github.io/) ([Quilt-1M: One Million Image-Text Pairs for Histopathology](https://arxiv.org/pdf/2306.11207)) | 512 |
| [`biomedclip`](https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224) ([BiomedCLIP: a multimodal biomedical foundation model pretrained from fifteen million scientific image-text pairs](https://aka.ms/biomedclip-paper)) | 512 |
| [`omiclip`](https://huggingface.co/WangGuangyuLab/Loki) ([A visual-omics foundation model to bridge histopathology with spatial transcriptomics](https://www.nature.com/articles/s41592-025-02707-1)) | 768 |

#### Bring Your Own Encoder

Add a custom encoder without touching AtlasPatch by writing a small plugin and pointing the CLI at it with `--feature-plugin /path/to/plugin.py`. The plugin must expose a `register_feature_extractors(registry, device, dtype, num_workers)` function; inside that hook call `register_custom_encoder` with a loader that knows how to load the model and run a forward pass.

```python
import torch
from torchvision import transforms
from atlas_patch.models.patch.custom import CustomEncoderComponents, register_custom_encoder


def build_my_encoder(device: torch.device, dtype: torch.dtype) -> CustomEncoderComponents:
    """
    Build the components used by AtlasPatch to embed patches with a custom model.

    Returns:
        CustomEncoderComponents describing the model, preprocess transform, and forward pass.
    """
    model = ...  # your torch.nn.Module
    model = model.to(device=device, dtype=dtype).eval()
    preprocess = transforms.Compose([transforms.Resize(224), transforms.ToTensor()])

    def forward(batch: torch.Tensor) -> torch.Tensor:
        return model(batch)  # must return [batch, embedding_dim]

    return CustomEncoderComponents(model=model, preprocess=preprocess, forward_fn=forward)


def register_feature_extractors(registry, device, dtype, num_workers):
    register_custom_encoder(
        registry=registry,
        name="my_encoder",
        embedding_dim=512,
        loader=build_my_encoder,
        device=device,
        dtype=dtype,
        num_workers=num_workers,
    )
```

Run AtlasPatch with `--feature-plugin /path/to/plugin.py --feature-extractors my_encoder` to benchmark your encoder alongside the built-ins. Multiple plugins and extractors can be added at once. Your custom embeddings will be written under `features/my_encoder`, row-aligned with `coords`, next to the built-in extractors.

### Available Slide Encoders

| Encoder | Embedding dim | Required patch encoder | Patch size | Model | Paper | Install |
| --- | --- | --- | --- | --- | --- | --- |
| `titan` | 768 | `conch_v15` | 512 | [MahmoodLab/TITAN](https://huggingface.co/MahmoodLab/TITAN) | [A multimodal whole-slide foundation model for pathology](https://www.nature.com/articles/s41591-025-03982-3) | `atlas-patch[titan]` or `atlas-patch[slide-encoders]` |
| `prism` | 1280 | `virchow_v1` | 224 | [paige-ai/Prism](https://huggingface.co/paige-ai/Prism) | [PRISM: A Multi-Modal Generative Foundation Model for Slide-Level Histopathology](https://arxiv.org/abs/2405.10254) | `atlas-patch[prism]` or `atlas-patch[slide-encoders]` |
| `moozy` | 768 | `lunit_vit_small_patch8_dino` | 224 | [AtlasAnalyticsLab/MOOZY](https://huggingface.co/AtlasAnalyticsLab/MOOZY) | [MOOZY: A Patient-First Foundation Model for Computational Pathology](https://arxiv.org/abs/2603.27048) | `atlas-patch[moozy]` or `atlas-patch[slide-encoders]` |

### Available Patient Encoders

| Encoder | Embedding dim | Required patch encoder | Patch size | Model | Paper | Install |
| --- | --- | --- | --- | --- | --- | --- |
| `moozy` | 768 | `lunit_vit_small_patch8_dino` | 224 | [AtlasAnalyticsLab/MOOZY](https://huggingface.co/AtlasAnalyticsLab/MOOZY) | [MOOZY: A Patient-First Foundation Model for Computational Pathology](https://arxiv.org/abs/2603.27048) | `atlas-patch[moozy]` or `atlas-patch[patient-encoders]` |

## Output Files

Everything AtlasPatch writes lives under the directory you pass to `--output`.

### What AtlasPatch writes

#### Per-Slide H5 files

Each processed slide gets one H5 file:

```text
<output>/patches/<stem>.h5
```

That file may contain:

- `coords`
- `features/<patch_encoder>`
- `slide_features/<slide_encoder>`

Rows in `features/<patch_encoder>` are aligned with `coords`.

#### Patient embedding files

Patient embeddings are written separately:

```text
<output>/patient_features/<encoder>/<case_id>.h5
```

Each patient H5 file stores the case embedding in `features`.

#### Optional image outputs

- patch PNGs: `<output>/images/<stem>/`
- overlays and masks: `<output>/visualization/`

### Reading the files

Per-slide H5 files keep patch coordinates, patch features, and slide embeddings together in one place.

#### Patch coordinates

- dataset: `coords`
- shape: `(N, 5)`
- columns: `(x, y, read_w, read_h, level)`
- `x` and `y` are level-0 pixel coordinates.
- `read_w`, `read_h`, and `level` describe how the patch was read from the WSI.
- the level-0 footprint of each patch is stored as the `patch_size_level0` file attribute

Example:

```python
import h5py
import numpy as np
import openslide
from PIL import Image

h5_path = "output/patches/sample.h5"
wsi_path = "/path/to/slide.svs"

with h5py.File(h5_path, "r") as f:
    coords = f["coords"][...]  # (N, 5) int32: [x, y, read_w, read_h, level]
    patch_size = int(f.attrs["patch_size"])

with openslide.OpenSlide(wsi_path) as wsi:
    for x, y, read_w, read_h, level in coords:
        img = wsi.read_region(
            (int(x), int(y)),
            int(level),
            (int(read_w), int(read_h)),
        ).convert("RGB")
        if img.size != (patch_size, patch_size):
            img = img.resize((patch_size, patch_size), resample=Image.BILINEAR)
        patch = np.array(img)  # (H, W, 3) uint8
```

#### Patch feature matrices

- group: `features/`
- dataset: `features/<patch_encoder>`
- shape: `(N, D)`

Rows in every feature matrix are aligned with `coords`.

```python
import h5py

with h5py.File("output/patches/sample.h5", "r") as f:
    feature_names = list(f["features"].keys())
    resnet50_features = f["features/resnet50"][...]
```

#### Slide embeddings

- group: `slide_features/`
- dataset: `slide_features/<slide_encoder>`
- shape: `(D,)`

```python
import h5py

with h5py.File("output/patches/sample.h5", "r") as f:
    titan_embedding = f["slide_features/titan"][...]
```

#### Patient embeddings

Patient embeddings are stored in separate H5 files under `patient_features/<encoder>/`.

```python
import h5py

with h5py.File("output/patient_features/moozy/case-001.h5", "r") as f:
    case_embedding = f["features"][...]
```

## Orchestration at cohort scale

The optional `atlas_conductor` layer runs the pipeline reliably across a whole cohort —
planning which slides to (re)process, dispatching work, validating the HDF5 outputs,
recovering from failures with bounded retries, and recording metadata-only telemetry —
without modifying the ML pipeline. Install it with the `orchestrator` extra and drive it
from a YAML job config:

```bash
pip install "atlas-patch[orchestrator]"
atlaspatch-conduct run job.yaml --dry-run   # preview the plan; drop --dry-run to execute
```

The layer ships **by-construction governance guardrails** (`atlas_conductor.governance`),
all additive over the metadata-only telemetry and none touching the ML pipeline: slide
stems are pseudonymized and HIPAA Safe-Harbor identifiers rejected before anything is
persisted, irreversible or expensive recovery actions (`force_reprocess`, `quarantine`,
`block_job`) are held for human confirmation unless the run is explicitly unattended, and
every consequential action is written to a tamper-evident, hash-chained audit trail. The
maintained **[System/Model Card](MODEL_CARD.md)** documents the non-SaMD scope boundary and
these safeguards as verifiable technical conditions (not a legal compliance certification).

See the **[orchestration usage guide](docs/orchestration.md)** for the job-config schema,
running with the fake (no-GPU) or real adapter, reading the report and decision trace, and
the recovery and telemetry model.

### Observability GUI

A read-only **static React** GUI renders the metadata-only telemetry: run history, per-slide
**verdicts** (the validator's structural pass/fail with a reason code — never a prediction or
confidence score), the per-slide **decision trace**, cohort metrics, and the **agent-choreography**
view (Level-1 component-state — planner / worker / validator / recovery / scheduler shown active or
idle with a "now processing slide X · stage Y" ticker — plus Level-2 message-flow edges). It
**imports nothing from the ML pipeline**, renders **no slide pixels**, and shows slide identifiers
exactly as persisted (pseudonymized for gated runs). It is strictly an observer — it submits no jobs
and confirms no actions.

The GUI is a **static, point-in-time renderer**: a prebuilt bundle is vendored in the wheel, so
`pip install atlas-patch` needs **no Node and no build step**. It reads one exported
`snapshot.json` — no Python runtime, no telemetry directory, no server. Out of the box it renders a
**bundled demo**; load a real run with the in-page **file picker or drag-and-drop**.

```bash
# Serve the packaged GUI locally and open it in a browser (stdlib HTTP server, no Node):
atlaspatch-conduct gui

# Export a run's snapshot, then load it in the GUI via the file picker / drag-and-drop:
atlaspatch-conduct export-report <output_dir>/telemetry --format json > snapshot.json
```

The `--format json` output is the versioned observability **snapshot** — a single,
schema-versioned, JSON-safe payload carrying everything the observability surface shows (run
history, per-slide structural verdicts, decision trace, cohort metrics, and the derived Level-1
choreography and Level-2 message-flow state). It is the one machine-readable contract the renderer
consumes; the SPA pins its `schema_version` and shows an explicit incompatibility state on mismatch.
The HTML sibling renders the same assembled data.

The GUI needs **no runtime Python dependency** (Streamlit was retired in favour of the static
bundle), so `pip install atlas-patch` and the core `atlaspatch` CLI stay GUI-free. The SPA source
lives at repo-root [`web/`](web/); CI rebuilds it and asserts the vendored bundle is byte-identical.

### Compliance dossier and per-run evidence

The maintained **[compliance dossier](COMPLIANCE.md)** positions the layer against the **EU
AI Act** (Annex IV technical documentation) and **ISO/IEC 42001**, mapping each applicable
obligation to an implemented control and the CI test that enforces it, under a documented
non-SaMD risk-tier determination. The mapping lives in a machine-checkable control register
(`atlas_conductor/compliance/controls.yaml`) that CI keeps in sync with the code — every cited
module/test must resolve and every row must appear in the dossier. It documents **verifiable
technical safeguards**, not a legal certification.

For a specific completed run, `export-dossier` emits a PHI-free **evidence bundle** — the audit
chain re-verified (reported broken if the trail was tampered with), the run's HITL
holds/approvals/waivers and telemetry-gate rejections, the per-slide outcomes and cohort counts,
and the control-register summary — from the same read path as `export-report`:

```bash
atlaspatch-conduct export-dossier <output_dir>/telemetry --format json   # or html
```

### Distributed agent choreography (A2A)

By default the four logical agents (planner, worker, validator, recovery) run as plain
in-process calls, and the scheduler is the in-process governor. The run can optionally wire
those four as **Google ADK agents exposed as A2A peers** (Agent2Agent protocol) so their
handoffs travel over the wire — purely for **watchable choreography**: the transport records
the same metadata-only `message_flow` telemetry either way and never changes what a run
computes, so the core is identical with or without it. Each peer is a *deterministic* custom
ADK agent (not an LLM agent), so the no-clinical-reasoning invariant holds even over A2A.
Select it per job config:

```yaml
# job.yaml
transport: a2a        # default: in-process
```

Then start the loopback peer set in one terminal and run the job in another:

```bash
python -m atlas_conductor.transport.a2a   # terminal 1: serve the four A2A peers on 127.0.0.1
atlaspatch-conduct run job.yaml           # terminal 2: run with transport: a2a
```

The `message_flow` family drives the GUI **Level-2 message-flow** view (directed edges
between agent nodes, pulsing on recency); a run recorded without message flow degrades to the
Level-1 component-state view. The ADK/A2A stack (`google-adk` and its dependencies) lives in
the `orchestrator` extra and is imported only inside `atlas_conductor/transport/a2a.py`, so
the base `atlaspatch` CLI import graph stays cloud-free; selecting `a2a` without the extra
fails with a clear "install `atlas-patch[orchestrator]`" error.

### Telemetry backend (local JSONL or BigQuery)

Telemetry defaults to the credential-free local JSONL backend. A run can instead append the
**same** metadata-only records to **BigQuery** — a cohort-scale, queryable backend — by
naming a dataset in the job config; switching the backend changes nothing about what any
agent records:

```yaml
# job.yaml
telemetry:
  backend: bigquery      # default: jsonl
  dataset: my_dataset    # required for bigquery; one table per record family
```

`google-cloud-bigquery` is imported only inside `atlas_conductor/telemetry_bigquery.py`
(behind the `orchestrator` extra), so the base install stays cloud-free. The GUI and the
report read the local JSONL backend; BigQuery is a write target for cohort-scale analysis.

### Data lineage (content-addressed provenance)

Where telemetry records *what a run decided*, **lineage** content-addresses *which exact input
bytes plus which config produced which output HDF5*: one record per output tying the SHA-256 of
each input WSI + a config fingerprint to the SHA-256 of the produced HDF5, keyed on the
pseudonymized stem. Record it post-hoc, or automatically at run end via a config block:

```bash
atlaspatch-conduct lineage <output_dir>              # default: stdlib manifest backend
atlaspatch-conduct lineage <output_dir> --backend dvc
```

```yaml
# job.yaml
lineage:
  backend: manifest      # 'manifest' (default, stdlib-only) or 'dvc' (opt-in)
```

The default `manifest` backend writes `<output_dir>/lineage/manifest.jsonl` with only the
standard library. The opt-in `dvc` backend writes a `dvc.yaml` stage + `.dvc` pointers so Git
history becomes the lineage record. Lineage persists **hashes, not pixels** — it never copies,
tracks, or `dvc push`-es a WSI/mask/embedding, and every tracked identifier is the `slide_<hex>`
pseudonym, so no raw filename or HIPAA identifier lands in the manifest or any tracked path.
`dvc` lives in the `orchestrator` extra and is touched only inside the DVC backend, so the base
CLI import graph stays DVC-free. See the [orchestration guide](docs/orchestration.md#data-lineage).

## SLURM job scripts

We prepared ready-to-run SLURM templates under `jobs/`:

- Patch extraction (SAM2 + H5/PNG): `jobs/atlaspatch_patch.slurm.sh`. Edits to make:
  - Set `WSI_ROOT`, `OUTPUT_ROOT`, `PATCH_SIZE`, `TARGET_MAG`, `SEG_BATCH`.
  - Ensure `--cpus-per-task` matches the CPU you want; the script passes `--patch-workers ${SLURM_CPUS_PER_TASK}` and caps `--max-open-slides` at 200.
  - `--fast-mode` is on by default; append `--no-fast-mode` to enable content filtering.
  - Submit with `sbatch jobs/atlaspatch_patch.slurm.sh`.
- Feature embedding (adds features into existing H5 files): `jobs/atlaspatch_features.slurm.sh`. Edits to make:
  - Set `WSI_ROOT`, `OUTPUT_ROOT`, `PATCH_SIZE`, and `TARGET_MAG`.
  - Configure `FEATURES` (comma/space list, multiple extractors are supported), `FEATURE_DEVICE`, `FEATURE_BATCH`, `FEATURE_WORKERS`, and `FEATURE_PRECISION`.
  - This script is intended for feature extraction; use the patch script when you need segmentation + coordinates, and run the feature script to embed one or more models into those H5 files.
  - Submit with `sbatch jobs/atlaspatch_features.slurm.sh`.
- Running multiple jobs: you can submit several jobs in a loop (for example, `for i in {1..50}; do sbatch jobs/atlaspatch_features.slurm.sh; done`). AtlasPatch uses per-slide lock files to avoid overlapping work on the same slide.

## Frequently Asked Questions (FAQ)

<details>
<summary><b>I'm facing an out of memory (OOM) error</b></summary>

This usually happens when too many WSI files are open simultaneously. Try reducing the `--max-open-slides` parameter:

```bash
atlaspatch process /path/to/slides --output ./output --max-open-slides 50
```

The default is 200. Lower this value if you're processing many large slides or have limited system memory.
</details>

<details>
<summary><b>I'm getting a CUDA out of memory error</b></summary>

Try one or more of the following:

1. **Reduce feature extraction batch size**:
   ```bash
   --feature-batch-size 16  # Default is 32
   ```

2. **Reduce segmentation batch size**:
   ```bash
   --seg-batch-size 1  # Default is 1
   ```

3. **Use lower precision**:
   ```bash
   --feature-precision float16  # or bfloat16
   ```

4. **Use a smaller patch size**:
   ```bash
   --patch-size 224  # Instead of 256
   ```
</details>

<details>
<summary><b>OpenSlide library not found</b></summary>

AtlasPatch requires the OpenSlide system library. Install it based on your system:

- **Conda**: `conda install -c conda-forge openslide`
- **Ubuntu/Debian**: `sudo apt-get install openslide-tools`
- **macOS**: `brew install openslide`

See [OpenSlide Prerequisites](#openslide-prerequisites) for more details.
</details>

<details>
<summary><b>Access denied for gated models (UNI, Virchow, etc.)</b></summary>

Some encoders require Hugging Face access approval:

1. Request access on the model's Hugging Face page (e.g., [UNI](https://huggingface.co/MahmoodLab/UNI))
2. Once approved, set your token:
   ```bash
   export HF_TOKEN=your_huggingface_token
   ```
3. Run AtlasPatch again
</details>

<details>
<summary><b>Missing microns-per-pixel (MPP) metadata</b></summary>

Some slides lack MPP metadata. You can provide it via a CSV file:

```bash
atlaspatch process /path/to/slides --output ./output --mpp-csv /path/to/mpp.csv
```

The CSV should have columns `wsi` (filename) and `mpp` (microns per pixel value).
</details>

<details>
<summary><b>Processing is slow</b></summary>

Try these optimizations:

1. **Enable fast mode** (skips content filtering, enabled by default):
   ```bash
   --fast-mode
   ```

2. **Increase parallel workers**:
   ```bash
   --patch-workers 16  # Match your CPU cores
   --feature-num-workers 8
   ```

3. **Increase batch sizes** (if GPU memory allows):
   ```bash
   --feature-batch-size 64
   --seg-batch-size 4
   ```

4. **Use multiple GPUs** by running separate jobs on different GPU devices.
</details>

<details>
<summary><b>My file format is not supported</b></summary>

AtlasPatch supports most common formats via OpenSlide and Pillow:
- **WSIs**: `.svs`, `.tif`, `.tiff`, `.ndpi`, `.vms`, `.vmu`, `.scn`, `.mrxs`, `.bif`, `.dcm`
- **Images**: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.gif`

If your format isn't supported, consider converting it to a supported format or [open an issue](https://github.com/AtlasAnalyticsLab/AtlasPatch/issues/new?template=feature_request.md).
</details>

<details>
<summary><b>How do I skip already processed slides?</b></summary>

`process` and `segment-and-get-coords` already skip existing per-slide H5 outputs by default. Use `--force` when you want to overwrite them:

```bash
atlaspatch process /path/to/slides --output ./output --force
```
</details>

<details>
<summary><b>Can I run multiple slide encoders in one command?</b></summary>

Yes, but only when they agree on the required patch geometry. `encode-slide` runs one patch pipeline and then appends the requested slide embeddings into the same per-slide H5 file, so all requested slide encoders in that run must agree on the patch size they need.

For example, `titan` and `prism` should be run separately because they require different patch sizes.
</details>

<details>
<summary><b>What does <code>encode-slide</code> or <code>encode-patient</code> reuse?</b></summary>

Both commands reuse existing per-slide H5 files by default. If the required patch features for the requested encoder are already present, AtlasPatch uses them directly. If the H5 file exists but the required patch feature dataset is missing, AtlasPatch runs the missing patch feature extraction step and then continues with slide or patient encoding.

Use `--force` if you want to rebuild instead of reuse.
</details>

<details>
<summary><b>What should the <code>encode-patient</code> CSV file look like?</b></summary>

The CSV file must contain:

- `case_id`
- `slide_path`

It may also contain:

- `mpp`

Each row links one slide to one patient. AtlasPatch groups rows by `case_id`, runs or reuses the per-slide H5 pipeline for each referenced slide, and then writes one patient embedding per patient.
</details>

<details>
<summary><b>Does <code>encode-patient</code> use slide embeddings?</b></summary>

No. In `v1.1.0`, patient encoding uses the patch features stored in each slide H5 file. It does not read `slide_features/<encoder>`.
</details>

<details>
<summary><b>Where are slide and patient embeddings written?</b></summary>

Slide embeddings are written into the per-slide H5 file under:

```text
slide_features/<slide_encoder>
```

Patient embeddings are written to separate files under:

```text
patient_features/<encoder>/<case_id>.h5
```
</details>

---

Have a question not covered here? Feel free to [open an issue](https://github.com/AtlasAnalyticsLab/AtlasPatch/issues/new) and ask!

## Feedback

- Report problems via the [bug report template](https://github.com/AtlasAnalyticsLab/AtlasPatch/issues/new?template=bug_report.md) so we can reproduce and fix them quickly.
- Suggest enhancements through the [feature request template](https://github.com/AtlasAnalyticsLab/AtlasPatch/issues/new?template=feature_request.md) with your use case and proposal.
- When opening a PR, fill out the [pull request template](.github/pull_request_template.md) and run the listed checks (lint, format, type-check, tests).

## Citation

If you use AtlasPatch in your research, please cite our paper:

```bibtex
@article{atlaspatch2026,
  title   = {AtlasPatch: Efficient Tissue Detection and High-throughput Patch Extraction for Computational Pathology at Scale},
  author  = {Alagha, Ahmed and Leclerc, Christopher and Kotp, Yousef and Metwally, Omar and Moras, Calvin and Rentopoulos, Peter and Rostami, Ghodsiyeh and Nguyen, Bich Ngoc and Baig, Jumanah and Khellaf, Abdelhakim and Trinh, Vincent Quoc-Huy and Mizouni, Rabeb and Otrok, Hadi and Bentahar, Jamal and Hosseini, Mahdi S.},
  journal = {arXiv preprint arXiv:2602.03998},
  year    = {2026}
}
```

## License

AtlasPatch is released under [CC BY-NC-SA 4.0](LICENSE).
