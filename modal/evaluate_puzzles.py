"""Evaluate d1-2B by independently completing Train Tracks puzzles."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import modal
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train import (DEFAULT_DATASET, MODEL, REVISION, ROOT, VOLUME_PATH,
                   ensure_hf_token, image, volume)

HERE = Path(__file__).resolve().parent
app = modal.App("train-tracks-d1-evaluate-puzzles")
rollout_image = (image
    .add_local_file(str(HERE / "train.py"), remote_path="/root/train.py")
    .add_local_file(str(HERE / "board.py"), remote_path="/root/traintracks/board.py"))


@app.function(image=rollout_image, gpu="RTX-PRO-6000", cpu=4, memory=24576,
              timeout=4 * 60 * 60,
              secrets=[modal.Secret.from_name("hf-train-tracks")],
              volumes={VOLUME_PATH: volume})
def run(dataset: str, split: str = "validation", run_id: str = "",
        revision: str = "main", limit_puzzles: int = 0, allow_test: bool = False,
        visual_variant: str = "plain"):
    import sys
    import time
    import torch
    from datasets import Image, List, load_dataset
    from huggingface_hub import HfApi, snapshot_download
    from transformers import AutoModel

    sys.path.insert(0, "/root/traintracks")
    from board import Board, CHOICES, FOCUS_NOTE
    from clue_state import (COUNTS_NOTE, PORTS_NOTE, load_clues,
                            target_counts, target_ports)
    from defer import (DEFER, DEFER_NOTE, MAX_DECISIONS_PER_CELL,
                       forced_other_status, question_with_defer)

    if not dataset:
        raise ValueError("Pass --dataset namespace/repository")
    if split not in {"validation", "test_small", "test_medium"}:
        raise ValueError("Choose validation, test_small, or test_medium")
    if split != "validation" and not allow_test:
        raise ValueError("Test splits are frozen; pass --allow-test only after configuration is frozen")
    if visual_variant not in {"plain", "focus", "counts", "ports", "defer"}:
        raise ValueError("visual_variant must be plain, focus, counts, ports, or defer")
    ensure_hf_token()
    volume.reload()
    if run_id:
        training = json.loads((ROOT / "runs" / run_id / "training.json").read_text())
        if training["dataset"] != dataset:
            raise ValueError("Training and rollout datasets differ")
        data_revision = training["dataset_revision"]
        checkpoint = ROOT / "runs" / run_id / "merged"
        model_revision = training["model_revision"]
        visual_variant = training.get("visual_variant", "plain")
    else:
        data_revision = HfApi().dataset_info(dataset, revision=revision).sha
        model_revision = REVISION
        checkpoint = Path(snapshot_download(
            MODEL, revision=REVISION, local_dir=str(ROOT / "model" / REVISION)))
    rows = load_dataset(dataset, split=split, revision=data_revision,
                        cache_dir=str(ROOT / "hf-datasets"))
    rows = rows.cast_column("images", List(Image(decode=False)))
    clues = load_clues() if visual_variant in {"counts", "ports", "defer"} else None
    puzzles = {}
    for row in rows:
        puzzles.setdefault(row["puzzle_id"], []).append(row)
    puzzles = list(puzzles.items())
    if limit_puzzles > 0:
        puzzles = puzzles[:limit_puzzles]
    model = AutoModel.from_pretrained(
        checkpoint, trust_remote_code=True, dtype=torch.bfloat16).to("cuda").eval()
    results = []
    with torch.inference_mode():
        for puzzle_id, decisions in puzzles:
            start = time.monotonic()
            decisions.sort(key=lambda row: row["step_index"])
            if [row["step_index"] for row in decisions] != list(range(len(decisions))):
                raise ValueError(f"Incomplete or duplicate decision sequence: {puzzle_id}")
            template = decisions[0]
            targets = [(row["state"]["target_cell"]["row"] - 1,
                        row["state"]["target_cell"]["column"] - 1) for row in decisions]
            board = Board(template["images"][0], template["rows"],
                          template["columns"], targets)
            history = []
            queue = list(board.unknown)
            budget = (MAX_DECISIONS_PER_CELL if visual_variant == "defer" else 1) * len(queue)
            defer_streak = 0
            question = (question_with_defer(template["question"])
                        if visual_variant == "defer" else template["question"])
            for step in range(budget):
                if not queue:
                    break
                target = queue.pop(0)
                state = dict(template["state"])
                state["target_cell"] = {"row": target[0] + 1, "column": target[1] + 1}
                state["past_actions"] = list(board.actions)
                if visual_variant in {"focus", "counts", "ports", "defer"}:
                    state["task"] += FOCUS_NOTE
                if visual_variant in {"counts", "ports", "defer"}:
                    state["task"] += COUNTS_NOTE
                    state.update(target_counts(clues[puzzle_id], target,
                                               state["past_actions"]))
                if visual_variant in {"ports", "defer"}:
                    state["task"] += PORTS_NOTE
                    state.update(target_ports(clues[puzzle_id], target,
                                              state["past_actions"]))
                if visual_variant == "defer":
                    state["task"] += DEFER_NOTE
                    state["deferred_cells"] = [
                        {"row": r + 1, "column": c + 1} for r, c in sorted(board.deferred)
                    ]
                    state["defer_streak"] = defer_streak
                    state["decisions_remaining"] = budget - step
                    forced, distance = forced_other_status(
                        clues[puzzle_id], queue, state["past_actions"])
                    state["other_forced_cells"] = forced
                    state["next_forced_distance"] = distance
                answer = model.system_one(
                    state, {"track_shape": question},
                    media=[board.render(target, visual_variant)])
                choice = answer.get("answers", {}).get("track_shape", {}).get("choice")
                if choice not in CHOICES and not (visual_variant == "defer" and choice == DEFER):
                    choice = "invalid"
                if choice == DEFER:
                    board.defer(target)
                    queue.append(target)
                    defer_streak += 1
                    history.append({"row": target[0] + 1, "column": target[1] + 1,
                                    "value": DEFER})
                else:
                    board.add(target, choice)
                    defer_streak = 0
                    history.append(dict(board.actions[-1]))
            # The audited collection has exactly one valid solution per puzzle.
            # Labels are used only here, after the full model-owned rollout.
            labels = {target: row["label"] for target, row in zip(targets, decisions)}
            correct = sum(action["value"] == labels[(action["row"] - 1,
                                                     action["column"] - 1)]
                          for action in board.actions)
            valid = not queue and correct == len(decisions)
            grid = [["given" for _ in range(board.width)] for _ in range(board.height)]
            for row, column in board.unknown:
                grid[row][column] = "unassigned"
            for action in board.actions:
                grid[action["row"] - 1][action["column"] - 1] = action["value"]
            results.append({"puzzle_id": puzzle_id, "valid": valid,
                            "correct_cells": correct,
                            "unresolved_cells": len(queue),
                            "deferrals": sum(a["value"] == DEFER for a in history),
                            "malformed": sum(a["value"] == "invalid" for a in history),
                            "seconds": round(time.monotonic() - start, 3),
                            "actions": history, "board": grid})
            print(f"{split}: {len(results)}/{len(puzzles)} puzzles", flush=True)
    report = {"model": MODEL, "model_revision": model_revision,
              "run_id": run_id or None, "dataset": dataset,
              "dataset_revision": data_revision, "split": split,
              "visual_variant": visual_variant,
              "score_type": "exact_match_to_unique_verified_solution",
              "valid": sum(row["valid"] for row in results), "attempted": len(results),
              "malformed": sum(row["malformed"] for row in results),
              "total_decisions": sum(len(row["actions"]) for row in results),
              "total_cells": sum(len(row["actions"]) - row["deferrals"] for row in results)
                             + sum(row["unresolved_cells"] for row in results),
              "total_deferrals": sum(row["deferrals"] for row in results),
              "unresolved_cells": sum(row["unresolved_cells"] for row in results),
              "decision_budget_per_cell": MAX_DECISIONS_PER_CELL if visual_variant == "defer" else 1,
              "puzzles": results}
    name = f"{split}-{visual_variant}-{'sft-' + run_id if run_id else 'base'}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output = ROOT / "rollouts" / name
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    volume.commit()
    return {"valid": report["valid"], "attempted": report["attempted"],
            "malformed": report["malformed"],
            "total_decisions": report["total_decisions"],
            "total_deferrals": report["total_deferrals"],
            "unresolved_cells": report["unresolved_cells"], "output": str(output)}


@app.local_entrypoint()
def main(dataset: str = DEFAULT_DATASET, split: str = "validation", run_id: str = "",
         revision: str = "main", limit_puzzles: int = 0, allow_test: bool = False,
         visual_variant: str = "plain"):
    print(run.remote(dataset, split, run_id, revision, limit_puzzles, allow_test,
                     visual_variant))
