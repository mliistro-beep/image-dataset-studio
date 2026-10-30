# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Backend VLM per il captioning in linguaggio naturale, con interfaccia comune."""
import gc
import threading
from typing import Any, Callable, List, Optional

from PIL import Image

from ..config import VLM_MODELS, FLORENCE_TASKS, IS_MAC
from ..i18n import tr
from ..images import flatten_to_rgb

# Sotto questa dimensione un contatore di byte non viene mostrato (solo file di configurazione)
MIN_REPORTED_BYTES = 1048576
# File dei repository che i backend non usano: i GGUF per llama.cpp (3,7 GB nei vecchi commit di moondream2)
IGNORED_DOWNLOAD_PATTERNS = ["*.gguf"]

# Download lasciati andare avanti dallo Stop (vedi download_snapshot)
_background_downloads: List[threading.Thread] = []

try:
    import torch
except ImportError:
    torch = None

try:
    import transformers
except ImportError:
    transformers = None


def vlm_dependencies_missing() -> Optional[str]:
    """Ritorna un messaggio con il comando pip se mancano le librerie VLM, altrimenti None."""
    missing = []
    if torch is None:
        missing.append("torch")
    if transformers is None:
        missing.append("transformers accelerate")
    if not missing:
        return None
    return tr("vlm.deps_missing", libs=", ".join(missing))


def cuda_available() -> bool:
    return torch is not None and torch.cuda.is_available()


def gpu_profile_unavailable_reason() -> Optional[str]:
    if IS_MAC:
        return tr("vlm.gpu_mac")
    if torch is None:
        return tr("vlm.gpu_no_torch")
    if not torch.cuda.is_available():
        return tr("vlm.gpu_no_cuda")
    try:
        import bitsandbytes  # noqa: F401
    except ImportError:
        return tr("vlm.gpu_no_bnb")
    return None


def free_torch_memory():
    gc.collect()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def download_snapshot(repo_id: str, revision: Optional[str], log_cb: Callable[[str], None],
                      progress_cb: Callable[[str, float], None],
                      should_stop: Callable[[], bool] = lambda: False):
    """Scarica (o verifica in cache) il repository HF, inviando l'avanzamento all'interfaccia.
    InterruptedError se viene richiesto lo stop."""
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm as base_tqdm

    # huggingface_hub 2.x con hf_xet usa insieme due contatori di byte (rete e scrittura su disco) e uno dei
    # file: si mostra solo il più avanti dei contatori di byte, e il numero di file solo se non ce ne sono.
    reported = {"bytes_seen": False, "bytes_done": 0}

    class _ProgressTqdm(base_tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = False
            super().__init__(*args, **kwargs)
            # Il contatore dei byte nasce prima di quello dei file, anche se i primi byte arrivano dopo
            if self.unit == "B":
                reported["bytes_seen"] = True

        def update(self, n=1):
            super().update(n)
            # Dopo uno stop il download continua in background: l'interfaccia non va più aggiornata
            if not self.total or should_stop():
                return
            pct = self.n / self.total * 100
            if self.unit == "B":
                # Sotto 1 MB sono solo i file di configurazione iniziali: "0/0 MB (100%)" confonde
                if self.total < MIN_REPORTED_BYTES or self.n < reported["bytes_done"]:
                    return
                reported["bytes_done"] = self.n
                msg = tr("vlm.download_mb", repo=repo_id, done=f"{self.n / 1048576:.0f}",
                         total=f"{self.total / 1048576:.0f}", percent=f"{pct:.1f}")
            elif reported["bytes_seen"]:
                return
            else:
                msg = tr("vlm.download_files", repo=repo_id, done=self.n, total=self.total)
            progress_cb(msg, pct)

    # snapshot_download non è interrompibile: gira in un thread separato e qui si controlla lo stop.
    # Se si ferma, il download prosegue in background fino alla chiusura dell'app; i file parziali
    # restano nella cache HF e vengono ripresi al tentativo successivo.
    result = {}

    def _run():
        try:
            try:
                snapshot_download(repo_id, revision=revision, tqdm_class=_ProgressTqdm,
                                  ignore_patterns=IGNORED_DOWNLOAD_PATTERNS)
            except TypeError:
                snapshot_download(repo_id, revision=revision, ignore_patterns=IGNORED_DOWNLOAD_PATTERNS)
        except BaseException as e:  # rilanciata nel thread chiamante
            result["error"] = e

    log_cb(tr("vlm.download_start", repo=repo_id))
    thread = threading.Thread(target=_run, name=f"hf-download-{repo_id}", daemon=True)
    thread.start()
    while thread.is_alive():
        thread.join(0.3)
        if should_stop():
            _background_downloads.append(thread)
            raise InterruptedError(tr("wd14.download_cancelled"))
    if "error" in result:
        raise result["error"]
    log_cb(tr("vlm.download_done", repo=repo_id))


def downloads_in_background() -> bool:
    """True se un download fermato dallo Stop sta ancora scaricando.

    I thread di snapshot_download non sono daemon: all'uscita Python li aspetterebbe fino alla fine
    del download, con la finestra già chiusa (vedi run.py)."""
    _background_downloads[:] = [t for t in _background_downloads if t.is_alive()]
    return bool(_background_downloads)


class VLMBackend:
    supports_free_prompt = True

    def __init__(self, model_key: str, device: str, low_memory: bool = False):
        self.model_key = model_key
        self.info = VLM_MODELS[model_key]
        self.device = device
        self.low_memory = low_memory
        # Any: sono classi di transformers o codice remoto (moondream2), senza tipi utili
        self.model: Any = None
        self.processor: Any = None

    def load(self, log_cb, progress_cb, should_stop=lambda: False):
        raise NotImplementedError

    def caption(self, image: Image.Image, instruction: str, max_new_tokens: int = 256) -> str:
        raise NotImplementedError

    def unload(self):
        self.model = None
        self.processor = None
        free_torch_memory()


class Florence2Backend(VLMBackend):
    """Florence-2 (supporto nativo transformers). Accetta solo task token, non prompt liberi."""
    supports_free_prompt = False

    def load(self, log_cb, progress_cb, should_stop=lambda: False):
        from transformers import AutoProcessor, Florence2ForConditionalGeneration
        repo = self.info["repo"]
        revision = self.info.get("revision")
        download_snapshot(repo, revision, log_cb, progress_cb, should_stop)
        progress_cb(tr("vlm.loading", model=self.info['label']), 100.0)
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.processor = AutoProcessor.from_pretrained(repo, revision=revision)
        self.model = Florence2ForConditionalGeneration.from_pretrained(
            repo, revision=revision, dtype=self.dtype).to(self.device)
        self.model.eval()

    def caption(self, image, instruction, max_new_tokens=256):
        task = instruction if instruction in FLORENCE_TASKS.values() else "<MORE_DETAILED_CAPTION>"
        image = flatten_to_rgb(image)
        inputs = self.processor(text=task, images=image, return_tensors="pt").to(self.device, self.dtype)
        with torch.inference_mode():
            generated_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens, num_beams=3, do_sample=False)
        text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed = self.processor.post_process_generation(text, task=task, image_size=image.size)
        result = parsed.get(task, text) if isinstance(parsed, dict) else str(parsed)
        return str(result).strip()


class Moondream2Backend(VLMBackend):
    def load(self, log_cb, progress_cb, should_stop=lambda: False):
        from transformers import AutoModelForCausalLM
        repo = self.info["repo"]
        revision = self.info.get("revision")
        download_snapshot(repo, revision, log_cb, progress_cb, should_stop)
        progress_cb(tr("vlm.loading", model=self.info['label']), 100.0)
        # bf16 dimezza la RAM (~3.7 GB invece di ~7.4 GB): obbligatorio con 8 GB di RAM
        if self.device == "cuda" or self.low_memory:
            dtype = torch.bfloat16
        else:
            dtype = torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(
            repo, revision=revision, trust_remote_code=True,
            dtype=dtype, device_map={"": self.device},
        )
        self.model.eval()

    def caption(self, image, instruction, max_new_tokens=256):
        image = flatten_to_rgb(image)
        settings = {"max_tokens": max_new_tokens}
        with torch.inference_mode():
            if instruction.strip():
                result = self.model.query(image, instruction.strip(), settings=settings)["answer"]
            else:
                result = self.model.caption(image, length="normal", settings=settings)["caption"]
        return str(result).strip()


class JoyCaptionBackend(VLMBackend):
    SYSTEM_PROMPT = "You are a helpful image captioner."

    def load(self, log_cb, progress_cb, should_stop=lambda: False):
        from transformers import AutoProcessor, BitsAndBytesConfig, LlavaForConditionalGeneration
        repo = self.info["repo"]
        revision = self.info.get("revision")
        download_snapshot(repo, revision, log_cb, progress_cb, should_stop)
        progress_cb(tr("vlm.loading_vram", model=self.info['label']), 100.0)
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            # La torre visiva SigLIP e il proiettore restano in bf16: quantizzarli degrada molto la qualità
            llm_int8_skip_modules=["vision_tower", "multi_modal_projector"],
        )
        self.processor = AutoProcessor.from_pretrained(repo, revision=revision)
        self.model = LlavaForConditionalGeneration.from_pretrained(
            repo, revision=revision, quantization_config=quant_config, dtype=torch.bfloat16, device_map=0,
        )
        self.model.eval()

    def caption(self, image, instruction, max_new_tokens=256):
        prompt = instruction.strip() or "Write a long detailed description for this image."
        convo = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        # La combinazione apply_chat_template(tokenize=False) + processor() evita BOS duplicati
        convo_string = self.processor.apply_chat_template(convo, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[convo_string], images=[flatten_to_rgb(image)], return_tensors="pt").to("cuda")
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
        with torch.inference_mode():
            generate_ids = self.model.generate(
                **inputs, max_new_tokens=max_new_tokens, do_sample=True,
                suppress_tokens=None, use_cache=True, temperature=0.6, top_k=None, top_p=0.9,
            )[0]
        generate_ids = generate_ids[inputs["input_ids"].shape[1]:]
        return self.processor.tokenizer.decode(
            generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        ).strip()


BACKENDS = {
    "florence2": Florence2Backend,
    "moondream2": Moondream2Backend,
    "joycaption": JoyCaptionBackend,
}


def create_backend(model_key: str, device: str, low_memory: bool = False) -> VLMBackend:
    backend_cls = BACKENDS[VLM_MODELS[model_key]["backend"]]
    return backend_cls(model_key, device, low_memory)


def model_supports_free_prompt(model_key: str) -> bool:
    return BACKENDS[VLM_MODELS[model_key]["backend"]].supports_free_prompt
