"""Compare paired base and SFT validation reports with a plot and CSV."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("sft", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.base.read_text(encoding="utf-8"))
    sft = json.loads(args.sft.read_text(encoding="utf-8"))
    if (base["dataset_revision"], base["split"]) != (sft["dataset_revision"], sft["split"]):
        raise ValueError("Reports use different dataset revisions or splits")
    if base.get("visual_variant", "plain") != sft.get("visual_variant", "plain"):
        raise ValueError("Reports use different visual variants")
    before = {p["puzzle_id"]: p for p in base["puzzles"]}
    after = {p["puzzle_id"]: p for p in sft["puzzles"]}
    if before.keys() != after.keys():
        raise ValueError("Reports do not cover the same puzzle IDs")
    rows = []
    for pid in sorted(before):
        b, a = before[pid], after[pid]
        total = len(b["actions"])
        if total != len(a["actions"]):
            raise ValueError(f"Decision counts differ for {pid}")
        rows.append({"puzzle_id": pid, "total_cells": total,
                     "base_correct": b["correct_cells"], "sft_correct": a["correct_cells"],
                     "base_accuracy_percent": round(100*b["correct_cells"]/total, 2),
                     "sft_accuracy_percent": round(100*a["correct_cells"]/total, 2),
                     "base_solved": b["valid"], "sft_solved": a["valid"]})
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    base_correct = sum(row["base_correct"] for row in rows)
    sft_correct = sum(row["sft_correct"] for row in rows)
    total_cells = sum(row["total_cells"] for row in rows)
    improved = sum(row["sft_correct"] > row["base_correct"] for row in rows)
    worse = sum(row["sft_correct"] < row["base_correct"] for row in rows)
    tied = len(rows) - improved - worse
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.7),
                             gridspec_kw={"width_ratios": [1, 1.5]})
    values = [100*base_correct/total_cells, 100*sft_correct/total_cells]
    axes[0].bar(["Base", "SFT"], values, color=["#9bb5c3", "#176b8a"], width=.58)
    axes[0].set(title="Individual cell accuracy", ylabel="Correct decisions (%)", ylim=(0, 70))
    for i, value in enumerate(values):
        axes[0].text(i, value + 1.5, f"{value:.1f}%", ha="center", fontweight="bold")
    colors = ["#177c6b" if row["sft_correct"] > row["base_correct"]
              else "#be614b" if row["sft_correct"] < row["base_correct"] else "#71838f"
              for row in rows]
    axes[1].scatter([row["base_accuracy_percent"] for row in rows],
                    [row["sft_accuracy_percent"] for row in rows],
                    c=colors, s=34, alpha=.85)
    axes[1].plot([0, 100], [0, 100], color="#7b8b94", linestyle="--", linewidth=1)
    axes[1].set(xlabel="Base cell accuracy per puzzle (%)",
                ylabel="SFT cell accuracy per puzzle (%)",
                title=f"Same 46 puzzles: {improved} improved · {worse} declined · {tied} tied",
                xlim=(0, 100), ylim=(0, 100))
    axes[1].set_aspect("equal", adjustable="box")
    fig.suptitle("Train Tracks validation · base vs one-epoch SFT", fontsize=14,
                 fontweight="bold")
    fig.text(.5, .015, "Whole-puzzle success: 0/46 for both models. Cell accuracy alone does not show independent solving.",
             ha="center", fontsize=8, color="#536775")
    fig.tight_layout(rect=(0, .055, 1, .94))
    args.png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.png, dpi=180, facecolor="white")
    plt.close(fig)
    print(f"{args.csv}\n{args.png}")


if __name__ == "__main__":
    main()
