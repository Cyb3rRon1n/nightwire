# 4U box: train the narrator on 👍/👎 and A/B a 14B model

Status: approved 2026-11-22 (both 4U box cards kept). Roadmap item 6. Runs on the 4U box: RTX 4070 (12 GB)
and RTX 3060 Ti (8 GB). Nothing here runs on the current CPU-only setup except the export step.

**Goal:** a narrator tuned on the owner's own ratings, and a measured answer on whether 14B beats 8B. Both are judged by
the soak scorecard, not by feel.

## Sources

- **TRL KTOTrainer** (huggingface.co/docs/trl/kto_trainer, verified).
  - The data format is unpaired `{prompt, completion, label}`.
  - Defaults: `beta=0.1`, `learning_rate=1e-6`.
  - The weighted ratio of liked to disliked examples should be 1:1 to 4:3, set with `desirable_weight` and
    `undesirable_weight`.
  - `precompute_ref_log_probs=True` saves memory.
  - QLoRA works through `peft_config` plus a 4-bit `quantization_config`.
  - The KL estimate needs a per-device batch above 1.
  - Long inputs are truncated from the right.
- **KTO** (Ethayarajh et al., ICML 2024, arXiv:2402.01306). Abstract verified: it learns from unpaired good/bad labels.
- **Unsloth requirements** (verified). The absolute minimums are 6 GB for 8B QLoRA and 8.5 GB for 14B QLoRA. Those
  figures are for short-context fine-tuning. We found no measured KTO numbers at 6-8k tokens, so step 2 measures it.
- **Ollama.**
  - Import docs (verified): `FROM` takes a GGUF or a safetensors directory, and Ollama does not quantize a GGUF on
    import.
  - FAQ (verified): `OLLAMA_CONTEXT_LENGTH`; `OLLAMA_KV_CACHE_TYPE=q8_0` halves the KV cache; a model that doesn't fit
    on one GPU is spread across all of them.
  - Model card (verified): qwen3:14b Q4_K_M is 9.3 GB.

## Steps

### 0. Now, on CPU (done)

`python -m tools.ratings_export out.jsonl` writes TRL's format:
- the system prompt plus the turn prompt, as chat messages;
- the oldest "Recent events" lines are trimmed so the reply is never cut;
- it prints the weights that put the ratio in 1:1 to 4:3.

Tests: `tests/test_ratings_export.py`.

### 1. Gate: enough ratings

- Train only when there are at least 300 rated turns, and at least 60 of each kind. This is a practical floor; no
  source gives a minimum.
- Until then, liked turns keep working as prompt examples.
- Stop if there are fewer.

### 2. Measure memory first

- On the 4070, run one KTO step of Qwen3-8B, the Hugging Face base model rather than the Ollama GGUF, with:
  - QLoRA 4-bit, gradient checkpointing, `precompute_ref_log_probs=True`;
  - per-device batch 2, gradient accumulation 8;
  - `max_length` 4096, then 6144, then 8192.
- Record the peak VRAM of each run.
- Pick the largest `max_length` that fits, and re-run the export with that number as `--max-tokens`.
- Batch 2 is too big at that length if no setting fits. Then use `loss_type="apo_zero_unpaired"`, which needs no KL
  batch. This is a judgement call made from the docs.

### 3. Train

- Settings: `beta=0.1`, the weights from step 0, LoRA r=16 on the attention and MLP projections, 1-2 epochs.
- Try an adapter learning rate between 5e-6 and 2e-5. This range is not verified; the TRL docs say only that adapters
  "typically use a higher learning rate".
- Hold out 10% of the ratings, and watch the reward margin on them.

### 4. Back into Ollama

1. Run PEFT `merge_and_unload` into the bf16 base.
2. Convert with llama.cpp `convert_hf_to_gguf.py`.
3. Quantize with `llama-quantize` to Q4_K_M.
4. Build a Modelfile with `FROM` pointing at that file, using the chat template and parameters copied from
   `ollama show qwen3:8b --modelfile`. Then run `ollama create nightwire-kto`.

### 5. A/B on the scorecard

Run the 33-turn soak 3 times for each model:

| Model | Context |
|---|---|
| Stock qwen3:8b | 8k |
| nightwire-kto (8B) | 8k |
| qwen3:14b | 8k, then 16k, with `OLLAMA_KV_CACHE_TYPE=q8_0` |

- The 14B splits across both GPUs automatically if it doesn't fit on the 4070.
- Compare the scorecard and its memory probes, plus median seconds per turn.
- A model wins only if it is better on most measures and no slower than 1.5× the stock model.
- The owner reads two transcripts side by side for each winner, because the scorecard can't judge feel.

### 6. Ship

- Set the winning model in the narrator config.
- Keep the stock model one setting away to roll back.
- Retrain each time the ratings grow by another 300.

## Risks

- **Too few dislikes.** The owner mostly rates in check-ins, so the ratings may be nearly all likes. The weights
  correct for a moderate skew. If there are fewer than 60 dislikes, stop at step 1.
- **Overfitting to one player's taste.** The 10% hold-out and the soak catch this.
- **Repeating the training data.** The 8-word repeat cut still runs at play time.
