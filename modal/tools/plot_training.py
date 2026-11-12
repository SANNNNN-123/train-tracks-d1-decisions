"""Extract logged SFT losses and create a standalone training plot."""
import argparse
import ast
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--validation-before", type=float, required=True)
    parser.add_argument("--validation-after", type=float, required=True)
    parser.add_argument("--expected-points", type=int)
    parser.add_argument("--title", default="Train Tracks d1-2B | one-epoch LoRA SFT")
    args = parser.parse_args()

    entries = []
    for line in args.log.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("{'loss':"):
            record = ast.literal_eval(line)
            entries.append({"step": len(entries) * 10 + 10,
                            "epoch": float(record["epoch"]),
                            "train_loss": float(record["loss"]),
                            "learning_rate": float(record["learning_rate"])})
    if not entries or (args.expected_points is not None
                       and len(entries) != args.expected_points):
        raise ValueError(f"Expected {args.expected_points} loss records; found {len(entries)}")

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(entries[0]))
        writer.writeheader()
        writer.writerows(entries)

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5),
                             gridspec_kw={"width_ratios": [2.2, 1]})
    steps = [entry["step"] for entry in entries]
    losses = [entry["train_loss"] for entry in entries]
    axes[0].plot(steps, losses, color="#176b8a", linewidth=1.8,
                 marker="o", markersize=2.4)
    axes[0].set(xlabel="Optimizer step", ylabel="Training loss",
                title="Training loss (logged every 10 steps)",
                xlim=(0, max(steps) * 1.02))
    axes[0].grid(axis="y", color="#dce5ea", linewidth=0.8)
    axes[1].bar(["Before", "After"],
                [args.validation_before, args.validation_after],
                color=["#9bb5c3", "#176b8a"], width=0.55)
    axes[1].set(title="Teacher-forced validation loss", ylabel="Loss",
                ylim=(0, max(args.validation_before, args.validation_after) * 1.2))
    for index, value in enumerate([args.validation_before, args.validation_after]):
        axes[1].text(index, value + max(args.validation_before, args.validation_after) * 0.015,
                     f"{value:.3f}", ha="center", va="bottom")
    fig.suptitle(args.title, fontsize=14, fontweight="bold")
    fig.text(0.5, 0.01, "Loss describes supervised fit; independent puzzle success needs a separate evaluation.",
             ha="center", fontsize=8, color="#536775")
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    args.png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.png, dpi=180, facecolor="white")
    plt.close(fig)
    print(f"{args.csv}\n{args.png}")


if __name__ == "__main__":
    main()
