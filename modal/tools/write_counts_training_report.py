"""Build the counts SFT Markdown report from the complete Modal stdout log."""
import ast
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
LOG = HERE / "results/counts-full-training-stdout.log"
CSV = HERE / "training-logs/counts-full-sft-loss.csv"
REPORT = HERE / "docs/COUNTS_FULL_TRAINING.md"
RUN_URL = "https://modal.com/apps/zuhairsannnnn/main/ap-usgbPPtlhUwFPTsfM3q6VK"


def main():
    log = LOG.read_text(encoding="utf-8-sig").strip()
    metadata_start = log.rfind('\n{\n  "run_id":')
    if metadata_start < 0:
        raise ValueError("Final training report missing from Modal stdout")
    metadata = json.loads(log[metadata_start + 1:])
    summary = next(ast.literal_eval(line) for line in log.splitlines()
                   if line.startswith("{'train_runtime':"))
    with CSV.open(newline="", encoding="utf-8") as file:
        losses = list(csv.DictReader(file))
    if len(losses) != 70 or int(losses[-1]["step"]) != 700:
        raise ValueError("Expected 70 logged losses ending at step 700")
    if metadata["optimizer_steps"] != 700 or metadata["visual_variant"] != "counts":
        raise ValueError("Unexpected training run")

    text = f"""# Counts SFT: full training run

**Run:** [`{metadata['run_id']}`]({RUN_URL})  
**Status:** completed; checkpoint saved in the Modal Volume.

![Training and teacher-forced validation loss](../training-logs/counts-full-sft-loss.png)

| Measure | Value |
| --- | ---: |
| Training decisions | {metadata['train_rows']:,} |
| Validation decisions | {metadata['validation_rows']:,} |
| Optimizer steps | {metadata['optimizer_steps']:,} |
| Training time | {metadata['train_runtime_seconds'] / 60:.1f} minutes |
| Peak allocated GPU memory | {metadata['peak_gpu_memory_gib']:.2f} GiB |
| Mean training loss | {float(summary['train_loss']):.4f} |
| Teacher-forced validation loss, before | {metadata['validation_loss_before']:.4f} |
| Teacher-forced validation loss, after | {metadata['validation_loss_after']:.4f} |

The loss graph contains every logged training point, one per 10 optimizer steps.
The fall in teacher-forced validation loss shows fit to the verified decision
states. It does not measure independent whole-puzzle solving. That requires a
separate model-owned rollout on the 46 validation puzzles.

Model: `{metadata['model']}` at revision `{metadata['model_revision']}`. Dataset:
`{metadata['dataset']}` at revision `{metadata['dataset_revision']}`. Recipe:
one epoch, LoRA rank 16 / alpha 32 / dropout 0.05, learning rate 2e-4, batch
size 2 with 8 accumulation steps, seed 42. The visual variant is `counts`.
The checkpoint is at `{metadata['output_dir']}` in the Modal Volume.

[Plot data as CSV](../training-logs/counts-full-sft-loss.csv)

## Full training log

```text
{log}
```
"""
    REPORT.write_text(text, encoding="utf-8")
    print(f"{REPORT}: {len(losses)} loss records, {len(log.splitlines())} log lines")


if __name__ == "__main__":
    main()
