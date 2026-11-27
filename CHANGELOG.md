# Changelog

*[Versione italiana più sotto](#italiano)*

## 1.0.0 — 2026-11-27

First stable release.

### Features

- **Batch Tag (WD14)**: ConvNeXtV2 / SwinV2 / MOAT models (ONNX, CUDA with CPU fallback), confidence thresholds,
  rating and banned tag filters, min/max tags, trigger word, prepend/postpend, append or overwrite, manual review and
  a **Mass Tag Editor** (frequency table, bulk replace/add/delete).
- **Batch Caption (VLM)**: Florence-2, moondream2 and JoyCaption Beta One (4-bit on CUDA), instruction presets,
  prefix, append/overwrite, find & replace, ETA. One caption per line in each `.txt`.
- **Single Image / Prompt Extraction**: drop, open or paste an image and get tags, a description or both; nothing is
  written to disk, with a history of the last 20 analyses.
- Dataset layout with `original_dataset/` as the source of truth (sequential names in natural order,
  `rename_map.csv`), archive import, `dataset_tags/` and `dataset_captions/`.
- Interface in 8 languages (en, it, es, de, fr, pt_BR, zh_CN, ja); Linux installer with NVIDIA GPU detection.

### Reliability

- Only one model in memory at a time; Stop works during model downloads too.
- WD14 models verified against the Hugging Face hash; offline use of a verified cache.
- VLM models pinned to fixed Hub revisions; abandoned partial downloads are cleaned up.
- Text in the editors is never lost: save or confirm before discarding; `.txt` and `settings.json` written atomically.
- Clean exit with no crash when closing the app.

<a id="italiano"></a>

## 1.0.0 — 27/11/2026 (italiano)

Prima versione stabile.

### Funzioni

- **Batch Tag (WD14)**: modelli ConvNeXtV2 / SwinV2 / MOAT (ONNX, CUDA con ripiego su CPU), soglie di confidenza,
  filtri per rating e tag esclusi, numero minimo/massimo di tag, trigger word, prefisso/suffisso, aggiunta in coda o
  sovrascrittura, revisione manuale e **Mass Tag Editor** (tabella delle frequenze, sostituzione/aggiunta/cancellazione
  in blocco).
- **Batch Caption (VLM)**: Florence-2, moondream2 e JoyCaption Beta One (4-bit su CUDA), istruzioni predefinite,
  prefisso, aggiunta in coda/sovrascrittura, trova e sostituisci, tempo stimato. Una caption per riga in ogni `.txt`.
- **Singola Immagine / Estrazione prompt**: trascina, apri o incolla un'immagine e ottieni tag, descrizione o
  entrambi; niente viene scritto su disco, con la cronologia delle ultime 20 analisi.
- Struttura del dataset con `original_dataset/` come fonte di verità (nomi sequenziali in ordine naturale,
  `rename_map.csv`), importazione di archivi, `dataset_tags/` e `dataset_captions/`.
- Interfaccia in 8 lingue (it, en, es, de, fr, pt_BR, zh_CN, ja); installazione per Linux con rilevamento della GPU
  NVIDIA.

### Affidabilità

- Un solo modello in memoria alla volta; lo Stop funziona anche durante i download dei modelli.
- Modelli WD14 verificati con l'hash di Hugging Face; uso senza rete di una cache verificata.
- Modelli VLM fissati a revisioni precise dell'Hub; i download parziali abbandonati vengono cancellati.
- Il testo negli editor non va mai perso: si salva o si chiede prima di scartarlo; `.txt` e `settings.json` scritti in
  modo atomico.
- Chiusura dell'app pulita, senza crash.
