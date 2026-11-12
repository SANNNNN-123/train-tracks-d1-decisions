"""Fine-tune Liquid d1-2B on a normalized Hugging Face image decision dataset.

Run: uv run modal run modal/train.py --mode smoke --visual-variant focus
Defaults to the uploaded Train Tracks Hugging Face dataset; --dataset overrides it.
Use --mode full for one epoch. Requires train and validation splits with
id, images (List[Image]), state (Json), question (Json), and label (string).

Uses d1-2B's native prompt/media/attention helpers, with Liquid's LFM3 LoRA setup:
https://huggingface.co/LiquidAI/d1-2B
https://github.com/Liquid4All/cookbook/blob/main/finetuning/notebooks/lfm3_vl_sft_with_trl.ipynb
"""

import importlib
import json
import os
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

import modal

VOLUME_NAME = "train-tracks-d1-training"
VOLUME_PATH = f"/mnt/{VOLUME_NAME}"
ROOT = Path(VOLUME_PATH)
DEFAULT_DATASET = "zuhairsan/train-tracks-decisions"
MODEL = "LiquidAI/d1-2B"
REVISION = "97c57047d5852d77e02dfac211f8768aff77a8b2"
HERE = Path(__file__).resolve().parent
app = modal.App("train-tracks-d1-2b-finetune")
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .uv_pip_install(
        "torch==2.14.0",
        "torchvision==0.29.0",
        "transformers==5.19.0",
        "trl==1.15.0",
        "peft==0.21.2",
        "datasets==4.8.4",
        "accelerate==1.15.0",
        "huggingface-hub==1.31.0",
        "safetensors==0.8.0",
        "pillow==12.3.0",
        "flash-linear-attention==0.5.2",
        "einops",
    )
    .uv_pip_install("opencv-python-headless==4.11.0.86", "numpy<3")
    .env({"HF_HUB_CACHE": f"{VOLUME_PATH}/hf-hub"})
    .add_local_file(str(HERE / "board.py"), remote_path="/root/board.py")
    .add_local_file(str(HERE / "clue_state.py"), remote_path="/root/clue_state.py")
    .add_local_file(str(HERE / "defer.py"), remote_path="/root/defer.py")
    .add_local_file(str(HERE / "clues.json"), remote_path="/root/clues.json")
)


def ensure_hf_token():
    """Accept the key names used by this project's uploader, then use HF_TOKEN."""
    token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
             or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    if not token:
        raise ValueError("Modal Secret hf-train-tracks needs HF_TOKEN or a supported Hugging Face token key")
    os.environ["HF_TOKEN"] = token


def prepare_dataset(dataset, processor, prompt, visual_variant="plain"):
    """Render d1 decisions; TRL handles image batching and completion-only labels."""
    from datasets import Image, List
    from board import FOCUS_NOTE, highlight_image
    from clue_state import (COUNTS_NOTE, PORTS_NOTE, load_clues,
                            target_counts, target_ports)
    from io import BytesIO

    if visual_variant == "defer":
        return prepare_defer_dataset(dataset, processor, prompt)

    clues = load_clues() if visual_variant in {"counts", "ports"} else None

    tokenizer = processor.tokenizer
    media = importlib.import_module(f"{prompt.__package__}.media")
    image_marker = media.template_markup(processor, "image")

    def render(row):
        if (
            not row["images"] or not isinstance(row["state"], dict)
            or row["question"]["type"] != "choice"
            or row["label"] not in row["question"]["criteria"]
        ):
            raise ValueError(f"Invalid image decision: {row['id']}")
        names = list(row["question"]["criteria"])
        random.Random(f"42:{row['id']}").shuffle(names)
        question = {
            **row["question"],
            "criteria": {name: row["question"]["criteria"][name] for name in names},
        }
        code, _ = dict(zip(names, prompt.aliases(tokenizer, names)))[row["label"]]
        state = dict(row["state"])
        images = row["images"]
        if visual_variant in {"focus", "counts", "ports"}:
            state["task"] += FOCUS_NOTE
            target = (state["target_cell"]["row"] - 1,
                      state["target_cell"]["column"] - 1)
            if visual_variant in {"counts", "ports"}:
                state["task"] += COUNTS_NOTE
                state.update(target_counts(clues[row["puzzle_id"]], target,
                                           state["past_actions"]))
            if visual_variant == "ports":
                state["task"] += PORTS_NOTE
                state.update(target_ports(clues[row["puzzle_id"]], target,
                                          state["past_actions"]))
            focused = highlight_image(images[0], row["rows"], row["columns"], target)
            buffer = BytesIO()
            focused.save(buffer, format="PNG")
            images = [{"bytes": buffer.getvalue(), "path": None}]
        text = prompt.render(
            tokenizer,
            state,
            prompt.as_question(question),
            bos=tokenizer.bos_token or "",
            lead=prompt.default_lead("lfm3_vl", tokenizer),
            media=image_marker * len(images),
        )
        return {"images": images, "prompt": text,
                "completion": code + tokenizer.eos_token}

    # The focus variant redraws only visual cues; the plain variant reuses bytes.
    return (
        dataset.cast_column("images", List(Image(mode="RGB", decode=False)))
        .map(
            render,
            remove_columns=[c for c in dataset.column_names if c != "images"],
            writer_batch_size=16,
        )
        .cast_column("images", List(Image(mode="RGB")))
    )


def prepare_defer_dataset(dataset, processor, prompt):
    """Rebuild teacher-owned queue states from each puzzle's first image."""
    from collections import defaultdict
    from io import BytesIO

    from datasets import Image, List
    from board import Board, FOCUS_NOTE
    from clue_state import COUNTS_NOTE, PORTS_NOTE, load_clues, target_counts, target_ports
    from defer import DEFER_NOTE, question_with_defer, teacher_trajectory

    clues = load_clues()
    groups = defaultdict(list)
    first_indices = {}
    for index, row in enumerate(dataset):
        puzzle_id = row["puzzle_id"]
        groups[puzzle_id].append({"step_index": row["step_index"],
                                  "state": row["state"], "label": row["label"]})
        if row["step_index"] == 0:
            first_indices[puzzle_id] = index
    specs = []
    indices = []
    targets_by_puzzle = {}
    for puzzle_id, rows in groups.items():
        if puzzle_id not in first_indices:
            raise ValueError(f"Missing first image for {puzzle_id}")
        ordered = sorted(rows, key=lambda row: row["step_index"])
        targets_by_puzzle[puzzle_id] = [
            (row["state"]["target_cell"]["row"] - 1,
             row["state"]["target_cell"]["column"] - 1) for row in ordered
        ]
        for source, label, actions, deferred, streak, budget, forced, distance in teacher_trajectory(
                rows, clues[puzzle_id]):
            specs.append((puzzle_id, source["state"]["target_cell"], label,
                          actions, deferred, streak, budget, forced, distance))
            indices.append(first_indices[puzzle_id])
    print(f"Defer trajectories: {len(specs)} decisions from {len(groups)} puzzles", flush=True)
    tokenizer = processor.tokenizer
    media = importlib.import_module(f"{prompt.__package__}.media")
    image_marker = media.template_markup(processor, "image")

    def render(row, index):
        puzzle_id, target_cell, label, actions, deferred, streak, budget, forced, distance = specs[index]
        target = target_cell["row"] - 1, target_cell["column"] - 1
        board = Board(row["images"][0], row["rows"], row["columns"],
                      targets_by_puzzle[puzzle_id])
        for action in actions:
            board.add((action["row"] - 1, action["column"] - 1), action["value"])
        for cell in deferred:
            board.defer(cell)
        buffer = BytesIO()
        board.render(target, "defer").save(buffer, format="PNG")
        state = dict(row["state"])
        state["task"] += FOCUS_NOTE + COUNTS_NOTE + PORTS_NOTE + DEFER_NOTE
        state["target_cell"] = target_cell
        state["past_actions"] = actions
        state["deferred_cells"] = [
            {"row": r + 1, "column": c + 1} for r, c in deferred
        ]
        state["defer_streak"] = streak
        state["decisions_remaining"] = budget
        state["other_forced_cells"] = forced
        state["next_forced_distance"] = distance
        state.update(target_counts(clues[puzzle_id], target, actions))
        state.update(target_ports(clues[puzzle_id], target, actions))
        question = question_with_defer(row["question"])
        names = list(question["criteria"])
        random.Random(f"42:{puzzle_id}:{index}").shuffle(names)
        question["criteria"] = {name: question["criteria"][name] for name in names}
        code, _ = dict(zip(names, prompt.aliases(tokenizer, names)))[label]
        text = prompt.render(
            tokenizer, state, prompt.as_question(question),
            bos=tokenizer.bos_token or "",
            lead=prompt.default_lead("lfm3_vl", tokenizer), media=image_marker,
        )
        return {"images": [{"bytes": buffer.getvalue(), "path": None}],
                "prompt": text, "completion": code + tokenizer.eos_token}

    return (
        dataset.select(indices)
        .cast_column("images", List(Image(mode="RGB", decode=False)))
        .map(render, with_indices=True,
             remove_columns=[c for c in dataset.column_names if c != "images"],
             writer_batch_size=16)
        .cast_column("images", List(Image(mode="RGB")))
    )


@app.function(
    image=image,
    gpu="RTX-PRO-6000",
    cpu=4,
    memory=16384,
    timeout=4 * 60 * 60,
    secrets=[modal.Secret.from_name("hf-train-tracks")],
    volumes={VOLUME_PATH: volume},
)
def train(dataset: str = DEFAULT_DATASET, mode: str = "smoke", revision: str = "main",
          visual_variant: str = "plain"):
    """Fine-tune, evaluate, and save the adapter and native d1 checkpoint."""
    import torch
    from datasets import load_dataset
    from huggingface_hub import HfApi, snapshot_download
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModel, AutoProcessor, set_seed
    from trl import SFTConfig, SFTTrainer

    if mode not in {"smoke", "full"}:
        raise ValueError("mode must be 'smoke' or 'full'")
    if visual_variant not in {"plain", "focus", "counts", "ports", "defer"}:
        raise ValueError("visual_variant must be plain, focus, counts, ports, or defer")
    if not dataset:
        raise ValueError("Pass --dataset namespace/repository")
    ensure_hf_token()
    set_seed(42)
    data_revision = HfApi().dataset_info(dataset, revision=revision).sha
    data = load_dataset(
        dataset, revision=data_revision, cache_dir=str(ROOT / "hf-datasets")
    )
    train_rows, val_rows = data["train"], data["validation"]
    required = {"id", "images", "state", "question", "label", "puzzle_id", "split"}
    if not required.issubset(train_rows.column_names) or not required.issubset(val_rows.column_names):
        raise ValueError("Dataset is missing Train Tracks decision columns")
    if any(row["split"] != "train" for row in train_rows) or any(row["split"] != "validation" for row in val_rows):
        raise ValueError("Train/validation split metadata mismatch")
    if mode == "smoke":
        if visual_variant == "defer":
            # A partial prefix contains no useful defer/revisit examples.
            train_id = train_rows[0]["puzzle_id"]
            val_id = val_rows[0]["puzzle_id"]
            train_rows = train_rows.select([
                i for i, puzzle_id in enumerate(train_rows["puzzle_id"])
                if puzzle_id == train_id
            ])
            val_rows = val_rows.select([
                i for i, puzzle_id in enumerate(val_rows["puzzle_id"])
                if puzzle_id == val_id
            ])
        else:
            train_rows = train_rows.select(range(min(16, len(train_rows))))
            val_rows = val_rows.select(range(min(4, len(val_rows))))
    checkpoint = Path(
        snapshot_download(
            MODEL,
            revision=REVISION,
            local_dir=str(ROOT / "model" / REVISION),
        )
    )
    # Load the native d1 class, but don't call system_one on this training instance:
    # creating its inference engine fuses projections that LoRA needs separately.
    model = AutoModel.from_pretrained(checkpoint, trust_remote_code=True, dtype=torch.bfloat16)
    package = type(model).__module__.rsplit(".", 1)[0]
    prompt = importlib.import_module(f"{package}.prompt")
    state_attention = importlib.import_module(f"{package}.attention").state_attention
    processor = AutoProcessor.from_pretrained(checkpoint, trust_remote_code=True)
    processor.tokenizer.padding_side = "right"
    processor.tokenizer.d1_codes = model.config.d1_codes
    processor.tokenizer.d1_prompt = getattr(model.config, "d1_prompt", 1)
    train_dataset = prepare_dataset(train_rows, processor, prompt, visual_variant)
    val_dataset = prepare_dataset(val_rows, processor, prompt, visual_variant)

    model = get_peft_model(
        model,
        LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "gate_proj",
                "o_proj",
                "out_proj",
                "in_proj",
                "w1",
                "w2",
                "w3",
            ],
            exclude_modules=r".*vision_tower.*",
        ),
    ).to("cuda")
    model.config.use_cache = False
    trainable_parameters = sum(p.numel() for p in model.parameters() if p.requires_grad)
    run_id = f"d1-2b-{visual_variant}-{mode}-{dataset.split('/')[-1]}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True)
    print(f"Training {MODEL}: {run_id}", flush=True)

    class DecisionTrainer(SFTTrainer):
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            # With one question, d1's set attention reads the whole prompt both ways.
            # Answers stay causal and invisible to the prompt, preventing label leakage.
            prompt_lengths = (inputs["labels"] != -100).int().argmax(dim=1)
            with state_attention(model, prompt_lengths):
                return super().compute_loss(model, inputs, return_outputs, num_items_in_batch)

    trainer = DecisionTrainer(
        model=model,
        args=SFTConfig(
            output_dir=str(run_dir / "trainer"),
            num_train_epochs=1,
            max_steps=4 if mode == "smoke" else -1,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=8,
            per_device_eval_batch_size=2,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            warmup_steps=0.05,
            logging_steps=1 if mode == "smoke" else 10,
            eval_strategy="no",
            save_strategy="no",
            bf16=True,
            report_to="none",
            completion_only_loss=True,
            max_length=None,
            seed=42,
            data_seed=42,
            dataloader_num_workers=0,
        ),
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=processor,
    )
    before = trainer.evaluate()["eval_loss"]
    training_result = trainer.train()
    after = trainer.evaluate()["eval_loss"]
    optimizer_steps = trainer.state.global_step
    del trainer
    model.save_pretrained(run_dir / "adapter")
    merged = model.merge_and_unload()
    merged.config.use_cache = True
    merged_dir = run_dir / "merged"
    merged.save_pretrained(merged_dir)
    processor.save_pretrained(merged_dir)
    for source in checkpoint.iterdir():
        if source.suffix == ".py" or source.name == "LICENSE":
            shutil.copy2(source, merged_dir / source.name)
    config_path = merged_dir / "config.json"
    config = json.loads(config_path.read_text())
    config["auto_map"] = json.loads((checkpoint / "config.json").read_text())[
        "auto_map"
    ]
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    report = {
        "run_id": run_id,
        "mode": mode,
        "visual_variant": visual_variant,
        "label_source": "visible-rule teacher trajectory" if visual_variant == "defer" else "dataset.label",
        "decision_budget_per_cell": 2 if visual_variant == "defer" else 1,
        "dataset": dataset,
        "dataset_revision": data_revision,
        "model": MODEL,
        "model_revision": REVISION,
        "validation_split": "validation",
        "optimizer_steps": optimizer_steps,
        "trainable_parameters": trainable_parameters,
        "train_runtime_seconds": training_result.metrics["train_runtime"],
        "peak_gpu_memory_gib": torch.cuda.max_memory_allocated() / 2**30,
        "train_rows": len(train_rows),
        "validation_rows": len(val_rows),
        "train_decisions": len(train_dataset),
        "validation_decisions": len(val_dataset),
        "validation_loss_before": before,
        "validation_loss_after": after,
        "output_dir": str(run_dir),
    }
    (run_dir / "training.json").write_text(json.dumps(report, indent=2) + "\n")
    volume.commit()
    print(json.dumps(report, indent=2))
    return report


@app.local_entrypoint()
def main(dataset: str = DEFAULT_DATASET, mode: str = "smoke", revision: str = "main",
         visual_variant: str = "plain"):
    call = train.spawn(dataset, mode, revision, visual_variant)
    print(f"Training call: {call.object_id}")
    print(call.get())
