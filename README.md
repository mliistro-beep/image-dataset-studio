# Image Dataset Studio

Desktop app (PySide6) to prepare LoRA training datasets: **WD14 tagging**, **natural-language captioning with VLMs** and **prompt extraction from a single image**. Interface in English and Italian.

*[Versione italiana più sotto](#italiano)*

## Features

| Tab | What it does |
|---|---|
| **Batch Tag (WD14)** | Auto-tagging with WD14 ConvNeXtV2 / SwinV2 / MOAT (ONNX). Confidence thresholds, rating/banned tag filters, min/max tags, trigger word, prepend/postpend, append or overwrite, manual review, plus a **Mass Tag Editor** (frequency table, bulk replace/add/delete). |
| **Batch Caption (VLM)** | Natural-language captions with Florence-2, moondream2 or JoyCaption. Custom instruction with presets, prefix (trigger word), append/overwrite, find & replace across captions, and a clearly visible **ETA**. |
| **Single Image / Prompt Extraction** | Drop, open or paste (Ctrl+V) an image and get tags, a description or both (tags first), ready to copy to the clipboard. Nothing is written to disk; the last 20 analyses of the session are kept in a history panel. |

WD14 and the VLM are **never loaded in memory at the same time**: the app unloads one model before loading the other.

### Hardware profiles for captioning

| Profile | Recommended model | Alternative | Notes |
|---|---|---|---|
| Universal (CPU) | Florence-2-large (0.77B) | moondream2 | ~4 GB RAM, ~40-70 s/image on an older CPU |
| GPU (CUDA) | JoyCaption Beta One (Llama 3.1 8B, 4-bit NF4) | — | ~6-7 GB VRAM, e.g. RTX 3060 12 GB. Linux/Windows only |
| Older laptop / limited RAM | moondream2 (bf16) | Florence-2-base (0.23B) | 8 GB RAM: close other heavy apps |

Florence-2 does not accept free-form instructions: with it the instruction field becomes a level-of-detail selector.

## Installation

### Automatic (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/mliistro-beep/image-dataset-studio/main/install.sh | bash
```

The script detects an NVIDIA GPU and picks the matching PyTorch CUDA build (otherwise it installs the CPU version), installs missing system packages (asking first), downloads the repository into `~/image-dataset-studio`, creates the virtual environment and adds an `image-dataset-studio` command plus an applications menu entry. Run it again to update. Options: `--dir PATH`, `--cpu`, `--gpu`, `--no-desktop`, `--yes`, `--uninstall`.

### Manual

Requires Python 3.10+.

```bash
git clone https://github.com/mliistro-beep/image-dataset-studio.git
cd image-dataset-studio
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

CPU (desktop, laptop, Mac):

```bash
pip install -r requirements.txt
```

NVIDIA GPU (enables the JoyCaption profile):

```bash
pip install -r requirements-gpu.txt
```

Model weights are downloaded automatically from HuggingFace the first time they are used (WD14 into `~/.cache/wd14_tagger`, VLMs into the standard HuggingFace cache). Cached WD14 files are checked once against the HuggingFace hash: an incomplete or corrupted file is downloaded again. Without a network connection the cached file is used and the check is retried on the next run.

## Usage

```bash
python run.py
```

On first start you must accept the license. The interface language follows the operating system (Italian if the system is in Italian, English otherwise) and can be changed from the 🌐 menu; the choice is remembered.

### Dataset folder structure

Selecting a folder of images (or a ZIP/TAR archive) creates:

```
my_dataset/
├── original_dataset/    # copies of the source images renamed 000.jpg, 001.jpg, ... (source of truth) + rename_map.csv
├── dataset_tags/        # same images + .txt with WD14 tags
└── dataset_captions/    # same images + .txt with natural-language captions
```

Source files are never modified. Images are numbered in natural order (`img2` comes before `img10`). Use **Import new images** to add pictures to an existing dataset: they are numbered after the last one and only the new ones are processed. If `original_dataset` contains files with non-conforming names (e.g. `photo.jpg`, `0009.jpg`, `005.jpg` + `005.png`) processing is blocked with an explicit error.

## Development

The tests cover the pure logic (tags, dataset layout, archives, settings, downloads) and need neither torch nor onnxruntime:

```bash
python3 -m venv .venv
.venv/bin/pip install PySide6-Essentials numpy Pillow tqdm pytest
.venv/bin/python -m pytest -q tests
```

`tools/exit_repro.py` is a manual check for the crash on exit fixed in `run.py`. It needs the full installation and the WD14 model in the cache: `~/image-dataset-studio/venv/bin/python -I tools/exit_repro.py tags --runs 8` (the crash is intermittent, so it runs several times; exit code 1 if any run crashes).

## License

Copyright © 2026 Mauro Liistro

This program is free software: you can redistribute it and/or modify it under the terms of the **GNU Affero General Public License, version 3 only** (`AGPL-3.0-only`), as published by the Free Software Foundation. It is distributed WITHOUT ANY WARRANTY. See [LICENSE](LICENSE).

If you distribute this program or a modified version, **or let others use it over a network**, you must make the complete source code available under the same license.

The AI models are **not** part of this repository and are subject to their own licenses: WD14 Tagger (Apache-2.0), Florence-2 (MIT), moondream2 (Apache-2.0), JoyCaption (Llama 3.1 Community License).

---

<a name="italiano"></a>
# Italiano

Applicazione desktop (PySide6) per preparare dataset di training LoRA: **tagging WD14**, **caption in linguaggio naturale con VLM** ed **estrazione del prompt da una singola immagine**. Interfaccia in italiano e inglese.

## Funzionalità

| Scheda | Cosa fa |
|---|---|
| **Batch Tag (WD14)** | Auto-tagging con WD14 ConvNeXtV2 / SwinV2 / MOAT (ONNX). Soglie di confidenza, filtri rating/tag bannati, min/max tag, trigger word, prepend/postpend, append o sovrascrittura, revisione manuale e **Mass Tag Editor** (tabella frequenze, sostituzione/aggiunta/eliminazione in massa). |
| **Batch Caption (VLM)** | Caption in linguaggio naturale con Florence-2, moondream2 o JoyCaption. Istruzione personalizzabile con preset, prefisso (trigger word), append/sovrascrittura, trova e sostituisci su tutte le caption e **stima del tempo residuo** ben visibile. |
| **Singola Immagine / Estrazione Prompt** | Trascina, apri o incolla (Ctrl+V) un'immagine e ottieni tag, descrizione o entrambi (prima i tag), pronti da copiare negli appunti. Nessun file viene scritto su disco; le ultime 20 analisi della sessione restano nello storico. |

WD14 e il VLM **non vengono mai tenuti in memoria insieme**: l'app scarica un modello prima di caricare l'altro.

### Profili hardware per il captioning

| Profilo | Modello consigliato | Alternativa | Note |
|---|---|---|---|
| Universale (CPU) | Florence-2-large (0.77B) | moondream2 | ~4 GB di RAM, ~40-70 s/immagine su una CPU datata |
| GPU (CUDA) | JoyCaption Beta One (Llama 3.1 8B, 4-bit NF4) | — | ~6-7 GB di VRAM, es. RTX 3060 12 GB. Solo Linux/Windows |
| Portatile datato / RAM limitata | moondream2 (bf16) | Florence-2-base (0.23B) | 8 GB di RAM: chiudi le altre app pesanti |

Florence-2 non accetta istruzioni libere: con questo modello il campo istruzione diventa un selettore del livello di dettaglio.

## Installazione

### Automatica (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/mliistro-beep/image-dataset-studio/main/install.sh | bash
```

Lo script rileva una GPU NVIDIA e sceglie la versione di PyTorch CUDA adatta (altrimenti installa la versione CPU), installa i pacchetti di sistema mancanti (chiedendo prima), scarica il repository in `~/image-dataset-studio`, crea l'ambiente virtuale e aggiunge il comando `image-dataset-studio` e una voce nel menu applicazioni. Rilancialo per aggiornare. Opzioni: `--dir PERCORSO`, `--cpu`, `--gpu`, `--no-desktop`, `--yes`, `--uninstall`.

### Manuale

Serve Python 3.10 o superiore.

```bash
git clone https://github.com/mliistro-beep/image-dataset-studio.git
cd image-dataset-studio
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

CPU (desktop, portatile, Mac):

```bash
pip install -r requirements.txt
```

GPU NVIDIA (abilita il profilo JoyCaption):

```bash
pip install -r requirements-gpu.txt
```

I pesi dei modelli vengono scaricati automaticamente da HuggingFace al primo utilizzo (WD14 in `~/.cache/wd14_tagger`, i VLM nella cache standard di HuggingFace). I file WD14 in cache vengono controllati una volta con l'hash di HuggingFace: un file incompleto o danneggiato viene scaricato di nuovo. Senza connessione si usa il file in cache e il controllo si ripete all'avvio successivo.

## Uso

```bash
python run.py
```

Al primo avvio va accettata la licenza. La lingua dell'interfaccia segue quella del sistema operativo (italiano se il sistema è in italiano, altrimenti inglese) e si può cambiare dal menu 🌐; la scelta viene ricordata.

### Struttura delle cartelle

Selezionando una cartella di immagini (o un archivio ZIP/TAR) viene creato:

```
mio_dataset/
├── original_dataset/    # copie delle immagini sorgente rinominate 000.jpg, 001.jpg, ... (fonte di verità) + rename_map.csv
├── dataset_tags/        # stesse immagini + .txt con i tag WD14
└── dataset_captions/    # stesse immagini + .txt con le caption in linguaggio naturale
```

I file sorgente non vengono mai modificati. Le immagini vengono numerate in ordine naturale (`img2` viene prima di `img10`). Con **Importa nuove immagini** si aggiungono foto a un dataset esistente: vengono numerate dopo l'ultima e si elaborano solo quelle nuove. Se `original_dataset` contiene file con nomi non conformi (es. `foto.jpg`, `0009.jpg`, `005.jpg` + `005.png`) l'elaborazione si blocca con un errore esplicito.

## Sviluppo

I test coprono la logica pura (tag, struttura del dataset, archivi, impostazioni, download) e non richiedono né torch né onnxruntime:

```bash
python3 -m venv .venv
.venv/bin/pip install PySide6-Essentials numpy Pillow tqdm pytest
.venv/bin/python -m pytest -q tests
```

`tools/exit_repro.py` è una prova manuale del crash alla chiusura corretto in `run.py`. Serve l'installazione completa con il modello WD14 in cache: `~/image-dataset-studio/venv/bin/python -I tools/exit_repro.py tags --runs 8` (il crash è intermittente, quindi la prova si ripete più volte; codice di uscita 1 se almeno un avvio va in crash).

## Licenza

Copyright © 2026 Mauro Liistro

Questo programma è software libero: puoi ridistribuirlo e/o modificarlo secondo i termini della **GNU Affero General Public License, solo versione 3** (`AGPL-3.0-only`), pubblicata dalla Free Software Foundation. È distribuito SENZA ALCUNA GARANZIA. Vedi [LICENSE](LICENSE) (il testo in inglese è l'unico legalmente valido).

Se distribuisci il programma o una versione modificata, **oppure lo rendi utilizzabile ad altri tramite rete**, devi renderne disponibile il codice sorgente completo sotto la stessa licenza.

I modelli di intelligenza artificiale **non** fanno parte di questo repository e sono soggetti alle rispettive licenze: WD14 Tagger (Apache-2.0), Florence-2 (MIT), moondream2 (Apache-2.0), JoyCaption (Llama 3.1 Community License).
