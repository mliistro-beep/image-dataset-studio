# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Backend VLM per il captioning in linguaggio naturale, con interfaccia comune."""
import gc
from typing import Callable, Optional

from PIL import Image

from ..config import VLM_MODELS, FLORENCE_TASKS, IS_MAC
from ..i18n import tr

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
                      progress_cb: Callable[[str, float], None]):
    """Scarica (o verifica in cache) il repository HF, inviando l'avanzamento all'interfaccia."""
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm as base_tqdm

    class _ProgressTqdm(base_tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = False
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            super().update(n)
            if self.total:
                pct = self.n / self.total * 100
                unit_mb = self.unit == "B"
                if unit_mb:
                    msg = tr("vlm.download_mb", repo=repo_id, done=f"{self.n / 1048576:.0f}",
                             total=f"{self.total / 1048576:.0f}", percent=f"{pct:.1f}")
                else:
                    msg = tr("vlm.download_files", repo=repo_id, done=self.n, total=self.total)
                progress_cb(msg, pct)

    log_cb(tr("vlm.download_start", repo=repo_id))
    try:
        snapshot_download(repo_id, revision=revision, tqdm_class=_ProgressTqdm)
    except TypeError:
        snapshot_download(repo_id, revision=revision)
    log_cb(tr("vlm.download_done", repo=repo_id))


class VLMBackend:
    supports_free_prompt = True

    def __init__(self, model_key: str, device: str, low_memory: bool = False):
        self.model_key = model_key
        self.info = VLM_MODELS[model_key]
        self.device = device
        self.low_memory = low_memory
        self.model = None
        self.processor = None

    def load(self, log_cb, progress_cb):
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

    def load(self, log_cb, progress_cb):
        from transformers import AutoProcessor, Florence2ForConditionalGeneration
        repo = self.info["repo"]
        download_snapshot(repo, None, log_cb, progress_cb)
        progress_cb(tr("vlm.loading", model=self.info['label']), 100.0)
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.processor = AutoProcessor.from_pretrained(repo)
        self.model = Florence2ForConditionalGeneration.from_pretrained(repo, dtype=self.dtype).to(self.device)
        self.model.eval()

    def caption(self, image, instruction, max_new_tokens=256):
        task = instruction if instruction in FLORENCE_TASKS.values() else "<MORE_DETAILED_CAPTION>"
        image = image.convert("RGB")
        inputs = self.processor(text=task, images=image, return_tensors="pt").to(self.device, self.dtype)
        with torch.inference_mode():
            generated_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens, num_beams=3, do_sample=False)
        text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed = self.processor.post_process_generation(text, task=task, image_size=image.size)
        result = parsed.get(task, text) if isinstance(parsed, dict) else str(parsed)
        return str(result).strip()


class Moondream2Backend(VLMBackend):
    def load(self, log_cb, progress_cb):
        from transformers import AutoModelForCausalLM
        repo = self.info["repo"]
        revision = self.info.get("revision")
        download_snapshot(repo, revision, log_cb, progress_cb)
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
        image = image.convert("RGB")
        settings = {"max_tokens": max_new_tokens}
        with torch.inference_mode():
            if instruction.strip():
                result = self.model.query(image, instruction.strip(), settings=settings)["answer"]
            else:
                result = self.model.caption(image, length="normal", settings=settings)["caption"]
        return str(result).strip()


class JoyCaptionBackend(VLMBackend):
    SYSTEM_PROMPT = "You are a helpful image captioner."

    def load(self, log_cb, progress_cb):
        from transformers import AutoProcessor, BitsAndBytesConfig, LlavaForConditionalGeneration
        repo = self.info["repo"]
        download_snapshot(repo, None, log_cb, progress_cb)
        progress_cb(tr("vlm.loading_vram", model=self.info['label']), 100.0)
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            # La torre visiva SigLIP e il proiettore restano in bf16: quantizzarli degrada molto la qualità
            llm_int8_skip_modules=["vision_tower", "multi_modal_projector"],
        )
        self.processor = AutoProcessor.from_pretrained(repo)
        self.model = LlavaForConditionalGeneration.from_pretrained(
            repo, quantization_config=quant_config, dtype=torch.bfloat16, device_map=0,
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
        inputs = self.processor(text=[convo_string], images=[image.convert("RGB")], return_tensors="pt").to("cuda")
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
