"""Overlay the counts, ports, and defer SFT learning curves by epoch."""
import csv
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parents[1]
LOGS = HERE / "training-logs"


def read_csv(name):
    with (LOGS / name).open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def main():
    series = [
        ("Counts", read_csv("counts-full-sft-loss.csv"), "#176b8a",
         0.07265739142894745),
        ("Counts + ports", read_csv("ports-full-sft-loss.csv"), "#b05a2b",
         0.06438463181257248),
        ("Defer", read_csv("defer-full-sft-loss.csv"), "#6b4ca3",
         0.042200297117233276),
    ]
    if [len(rows) for _, rows, _, _ in series] != [70, 70, 110]:
        raise ValueError("Unexpected number of logged loss points")
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8),
                             gridspec_kw={"width_ratios": [2.2, 2.2, 1.2]})
    for label, rows, color, _ in series:
        epochs = [float(row["epoch"]) for row in rows]
        losses = [float(row["train_loss"]) for row in rows]
        for axis in axes[:2]:
            axis.plot(epochs, losses, label=label, color=color,
                      linewidth=1.7, alpha=0.9)
    axes[0].set(xlabel="Training epoch", ylabel="Training loss",
                title="All logged steps", xlim=(0, 1))
    axes[1].set(xlabel="Training epoch", ylabel="Training loss",
                title="Later training", xlim=(0.2, 1), ylim=(0, 0.3))
    for axis in axes[:2]:
        axis.grid(axis="y", color="#dce5ea", linewidth=0.8)
    axes[0].legend(frameon=False)
    after = [item[3] for item in series]
    axes[2].bar(["Counts", "Ports", "Defer"], after,
                color=[item[2] for item in series], width=0.6)
    axes[2].set(title="Teacher-forced\nvalidation loss", ylabel="Loss",
                ylim=(0, max(after) * 1.3))
    for index, value in enumerate(after):
        axes[2].text(index, value + max(after) * 0.02, f"{value:.3f}",
                     ha="center", va="bottom", fontsize=9)
    fig.suptitle("d1-2B SFT: counts, ports, and defer", fontsize=14,
                 fontweight="bold")
    fig.text(0.5, 0.015,
             "Epoch aligns runs with different step counts. Losses use different inputs and choices; compare puzzle rollouts for solving accuracy.",
             ha="center", fontsize=8, color="#536775")
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    output = LOGS / "counts-ports-defer-sft-loss.png"
    fig.savefig(output, dpi=180, facecolor="white")
    plt.close(fig)
    print(output)


if __name__ == "__main__":
    main()
