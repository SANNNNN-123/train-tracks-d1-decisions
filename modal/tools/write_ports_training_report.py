"""Build a ports training report with the complete log and counts comparison."""
import ast
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PORTS_LOG = HERE / "results/ports-full-training-stdout.log"
COUNTS_LOG = HERE / "results/counts-full-training-stdout.log"
PORTS_CSV = HERE / "training-logs/ports-full-sft-loss.csv"
REPORT = HERE / "docs/PORTS_FULL_TRAINING.md"
RUN_URL = "https://modal.com/apps/zuhairsannnnn/main/ap-lL6EdMTERYDOiQdWdw2QfL"


def parse_log(path):
    log = path.read_text(encoding="utf-8-sig").strip()
    start = log.rfind('\n{\n  "run_id":')
    if start < 0:
        raise ValueError(f"Final training report missing from {path}")
    metadata = json.loads(log[start + 1:])
    summary = next(ast.literal_eval(line) for line in log.splitlines()
                   if line.startswith("{'train_runtime':"))
    return log, metadata, summary


def main():
    log, ports, ports_summary = parse_log(PORTS_LOG)
    _, counts, counts_summary = parse_log(COUNTS_LOG)
    with PORTS_CSV.open(newline="", encoding="utf-8") as file:
        losses = list(csv.DictReader(file))
    if len(losses) != 70 or int(losses[-1]["step"]) != 700:
        raise ValueError("Expected 70 ports loss points through step 700")
    if ports["visual_variant"] != "ports" or counts["visual_variant"] != "counts":
        raise ValueError("Unexpected training variants")
    if (ports["dataset_revision"] != counts["dataset_revision"]
            or ports["model_revision"] != counts["model_revision"]
            or ports["train_rows"] != counts["train_rows"]):
        raise ValueError("Training runs are not directly paired")

    text = f"""# Ports SFT: full training run

**Run:** [`{ports['run_id']}`]({RUN_URL})  
**Status:** completed; checkpoint saved in the Modal Volume.

![Ports training and validation loss](../training-logs/ports-full-sft-loss.png)

## Comparison with counts SFT

![Counts versus ports training loss](../training-logs/counts-vs-ports-sft-loss.png)

| Measure | [Counts SFT](COUNTS_FULL_TRAINING.md) | Ports SFT |
| --- | ---: | ---: |
| Training decisions | {counts['train_rows']:,} | {ports['train_rows']:,} |
| Validation decisions | {counts['validation_rows']:,} | {ports['validation_rows']:,} |
| Optimizer steps | {counts['optimizer_steps']:,} | {ports['optimizer_steps']:,} |
| Training time | {counts['train_runtime_seconds'] / 60:.1f} min | {ports['train_runtime_seconds'] / 60:.1f} min |
| Peak allocated GPU memory | {counts['peak_gpu_memory_gib']:.2f} GiB | {ports['peak_gpu_memory_gib']:.2f} GiB |
| Mean training loss | {float(counts_summary['train_loss']):.4f} | {float(ports_summary['train_loss']):.4f} |
| Teacher-forced validation loss, before | {counts['validation_loss_before']:.4f} | {ports['validation_loss_before']:.4f} |
| Teacher-forced validation loss, after | {counts['validation_loss_after']:.4f} | {ports['validation_loss_after']:.4f} |

Both runs used `LiquidAI/d1-2B` revision `{ports['model_revision']}` and dataset
`{ports['dataset']}` revision `{ports['dataset_revision']}`. Each used one epoch,
LoRA rank 16 / alpha 32 / dropout 0.05, learning rate 2e-4, batch size 2 with
8 accumulation steps, and seed 42. The ports variant adds neighboring-port
status to the counts state. The different input states produce different loss
scales; a lower supervised loss does **not** establish better whole-puzzle
solving. Run an independent 46-puzzle validation rollout before selecting a
checkpoint. The held-out test splits remain untouched.

The checkpoint is at `{ports['output_dir']}` in the Modal Volume.

[Ports loss CSV](../training-logs/ports-full-sft-loss.csv)

## Full ports training log

```text
{log}
```
"""
    REPORT.write_text(text, encoding="utf-8")
    print(f"{REPORT}: {len(losses)} loss records, {len(log.splitlines())} log lines")


if __name__ == "__main__":
    main()
