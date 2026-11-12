"""Turn a saved evaluation report and local HF export into an HTML gallery."""
import argparse
import collections
import html
import json
import os
import statistics
from pathlib import Path
import sys

import pyarrow.parquet as parquet

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from board import Board

ROOT = Path(__file__).resolve().parents[2]


def first_images(parquet_path, puzzle_ids):
    found = {}
    columns = ["puzzle_id", "step_index", "images", "rows", "columns"]
    for batch in parquet.ParquetFile(parquet_path).iter_batches(batch_size=128, columns=columns):
        for row in batch.to_pylist():
            pid = row["puzzle_id"]
            if pid in puzzle_ids and row["step_index"] == 0:
                found[pid] = row
        if len(found) == len(puzzle_ids):
            break
    missing = puzzle_ids - found.keys()
    if missing:
        raise ValueError(f"Missing first images: {sorted(missing)}")
    return found


def reference_actions(parquet_path, puzzle_ids):
    actions = collections.defaultdict(dict)
    columns = ["puzzle_id", "step_index", "label", "state"]
    for batch in parquet.ParquetFile(parquet_path).iter_batches(batch_size=256, columns=columns):
        for row in batch.to_pylist():
            if row["puzzle_id"] in puzzle_ids:
                target = row["state"]["target_cell"]
                actions[row["puzzle_id"]][row["step_index"]] = {
                    "row": target["row"], "column": target["column"],
                    "value": row["label"]}
    return {pid: [items[i] for i in sorted(items)] for pid, items in actions.items()}


def render_board(first, actions, output, reference):
    targets = [(action["row"] - 1, action["column"] - 1) for action in reference]
    board = Board(first["images"][0], first["rows"], first["columns"], targets)
    for action in actions:
        target = action["row"] - 1, action["column"] - 1
        if action["value"] == "defer":
            board.defer(target)
        else:
            board.add(target, action["value"])
    board.render().save(output)


def make_html(report, cards, output):
    total = report.get("total_cells", report["total_decisions"])
    correct = sum(p["correct_cells"] for p in report["puzzles"])
    model_label = "Fine-tuned d1-2B" if report.get("run_id") else "Base d1-2B"
    if report.get("visual_variant", "plain") == "focus":
        model_label += " (focus input)"
    elif report.get("visual_variant", "plain") == "counts":
        model_label += " (counts input)"
    elif report.get("visual_variant", "plain") == "ports":
        model_label += " (counts and ports input)"
    elif report.get("visual_variant", "plain") == "defer":
        model_label += " (defer input)"
    cards_html = []
    for card in cards:
        pid = html.escape(card["id"])
        badge = '<span class="solved-badge">Solved</span>' if card["solved"] else ''
        decision_info = (f'<p class="decision-meta">{card["deferrals"]} deferrals; '
                         f'{card["unresolved"]} unresolved cells</p>'
                         if report.get("visual_variant") == "defer" else "")
        cards_html.append(f'''<article class="card" data-id="{pid}" data-accuracy="{card['accuracy']}">
  <div class="card-head"><h2>{pid} {badge}</h2><span>{card['correct']}/{card['total']} cells · {card['accuracy']:.1f}%</span></div>
  {decision_info}
  <div class="boards">
    <figure><a href="{card['predicted']}"><img loading="lazy" src="{card['predicted']}" alt="Predicted board for {pid}"></a><figcaption>{model_label} prediction</figcaption></figure>
    <figure><a href="{card['reference']}"><img loading="lazy" src="{card['reference']}" alt="Verified board for {pid}"></a><figcaption>Verified solution</figcaption></figure>
  </div>
</article>''')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Train Tracks · {model_label} validation</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, sans-serif; background: #f3f5f6; color: #17212b; }}
body {{ margin: 0; }} header {{ background: #142635; color: white; padding: 28px max(24px, calc((100vw - 1300px)/2)); }}
h1 {{ margin: 0 0 8px; font-size: clamp(24px,3vw,36px); }} header p {{ margin: 0; color: #cbd8e0; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 20px; }}
.stat {{ background: #263e50; border-radius: 10px; padding: 12px 18px; min-width: 145px; }}
.stat strong {{ display: block; font-size: 24px; }} .stat span {{ font-size: 13px; color: #d0dce3; }}
main {{ max-width: 1300px; margin: auto; padding: 24px; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 20px; }}
input, select {{ font: inherit; padding: 9px 12px; border: 1px solid #adbbc5; border-radius: 8px; background: white; }}
input {{ min-width: 225px; }} .cards {{ display: grid; gap: 22px; }}
.card {{ background: white; border: 1px solid #d8e0e5; border-radius: 14px; padding: 18px; box-shadow: 0 3px 12px #1024360b; }}
.card-head {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; align-items: baseline; margin-bottom: 12px; }}
.card h2 {{ font-size: 19px; margin: 0; }} .card-head span {{ color: #40566a; font-weight: 650; }}
.decision-meta {{ margin: -3px 0 12px; color: #536775; font-size: 13px; }}
.card-head .solved-badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #d9f3e4; color: #175b35; font-size: 12px; vertical-align: middle; }}
.boards {{ display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 18px; }}
figure {{ margin: 0; }} img {{ display: block; width: 100%; max-height: 480px; object-fit: contain; background: white; border: 1px solid #d9e1e6; }}
figcaption {{ padding-top: 7px; font-size: 14px; color: #435b6b; }}
@media(max-width: 700px) {{ .boards {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<header><h1>{model_label} · validation boards</h1><p>Each prediction is the model's own sequence of choices. The reference appears only for review after evaluation.</p>
<div class="stats"><div class="stat"><strong>{report['valid']}/{report['attempted']}</strong><span>puzzles solved</span></div>
<div class="stat"><strong>{correct}/{total}</strong><span>cells correct ({100*correct/total:.1f}%)</span></div>
<div class="stat"><strong>{report.get('total_deferrals', 0)}</strong><span>deferrals</span></div>
<div class="stat"><strong>{report.get('unresolved_cells', 0)}</strong><span>unresolved cells</span></div>
<div class="stat"><strong>{report['malformed']}</strong><span>malformed answers</span></div></div></header>
<main><div class="controls"><input id="search" type="search" placeholder="Find puzzle ID" aria-label="Find puzzle ID">
<select id="sort" aria-label="Sort puzzles"><option value="id">Puzzle ID</option><option value="high">Most cells correct</option><option value="low">Fewest cells correct</option></select>
<span id="shown"></span></div><div class="cards" id="cards">{''.join(cards_html)}</div></main>
<script>
const cards=document.getElementById('cards'), search=document.getElementById('search'), sort=document.getElementById('sort'), shown=document.getElementById('shown');
function update() {{
  const q=search.value.trim().toLowerCase(), order=sort.value;
  const items=[...cards.children].sort((a,b)=>order==='high'?Number(b.dataset.accuracy)-Number(a.dataset.accuracy):order==='low'?Number(a.dataset.accuracy)-Number(b.dataset.accuracy):a.dataset.id.localeCompare(b.dataset.id));
  items.forEach(x=>{{cards.appendChild(x);x.hidden=!x.dataset.id.toLowerCase().includes(q)}});
  shown.textContent=items.filter(x=>!x.hidden).length+' of '+items.length+' puzzles';
}}
search.addEventListener('input',update);sort.addEventListener('change',update);update();
</script></body></html>'''
    output.write_text(page, encoding="utf-8")


def make_markdown(report, cards, output, run_url, report_name, gallery_dir):
    puzzles = report["puzzles"]
    correct = sum(p["correct_cells"] for p in puzzles)
    total = report.get("total_cells", report["total_decisions"])
    seconds = sum(p["seconds"] for p in puzzles)
    deferred = report.get("visual_variant") == "defer"
    method = (
        "The model could choose defer to revisit a cell. Deferred cells remained "
        "unassigned; after at most two decisions per unknown cell, unresolved "
        "cells counted as incorrect. All tile choices were model-owned."
        if deferred else
        "The model completed each puzzle in row-major order, seeing its own "
        "earlier actions. All tile choices were model-owned."
    )
    lines = [
        "# d1-2B puzzle evaluation", "",
        f"- Run: {run_url}" if run_url else "- Run: Modal validation baseline",
        f"- Report: `{report['dataset']}` / `{report['split']}`; Modal Volume `train-tracks-d1-training/rollouts/{report_name}`",
        f"- Model: `{report['model']}` at `{report['model_revision']}`",
        f"- Dataset revision: `{report['dataset_revision']}`", "",
        "## Results", "",
        f"- Whole puzzles solved: **{report['valid']}/{report['attempted']} ({100*report['valid']/report['attempted']:.1f}%)**",
        f"- Correct cell decisions: **{correct}/{total} ({100*correct/total:.1f}%)**",
        f"- Malformed answers: **{report['malformed']}/{report['total_decisions']}**",
        f"- Decisions: **{report['total_decisions']}**; deferrals: **{report.get('total_deferrals', 0)}**; unresolved cells: **{report.get('unresolved_cells', 0)}**",
        f"- Sum of per-puzzle evaluation time: **{seconds:.1f} seconds**; median **{statistics.median(p['seconds'] for p in puzzles):.2f} seconds** per puzzle. This excludes model loading and dataset download.",
        "", "## Method", "",
        method + " The verified solution was used only for scoring after rollout.",
        "", f"[Open the visual gallery]({Path(os.path.relpath(gallery_dir, output.parent)).as_posix()}/index.html)",
        "", "## Per-puzzle results", "",
        "| Puzzle | Solved | Correct cells | Cell accuracy | Seconds |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for card, puzzle in zip(cards, puzzles):
        lines.append(f"| {card['id']} | {'Yes' if puzzle['valid'] else 'No'} | {card['correct']}/{card['total']} | {card['accuracy']:.1f}% | {puzzle['seconds']:.2f} |")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    out = args.output_dir or ROOT / "modal/eval-gallery" / args.report.stem
    out.mkdir(parents=True, exist_ok=True)
    puzzle_ids = {p["puzzle_id"] for p in report["puzzles"]}
    source = ROOT / "decision-dataset/huggingface/data" / f"{report['split']}.parquet"
    images = first_images(source, puzzle_ids)
    references = reference_actions(source, puzzle_ids)
    cards = []
    for puzzle in report["puzzles"]:
        pid = puzzle["puzzle_id"]
        predicted = puzzle["actions"]
        reference = references[pid]
        predicted_name, reference_name = f"{pid}-predicted.png", f"{pid}-reference.png"
        render_board(images[pid], predicted, out / predicted_name, reference)
        render_board(images[pid], reference, out / reference_name, reference)
        cards.append({"id": pid, "solved": puzzle["valid"],
                      "correct": puzzle["correct_cells"],
                      "total": len(reference),
                      "deferrals": puzzle.get("deferrals", 0),
                      "unresolved": puzzle.get("unresolved_cells", 0),
                      "accuracy": 100 * puzzle["correct_cells"] / len(reference),
                      "predicted": predicted_name, "reference": reference_name})
    make_html(report, cards, out / "index.html")
    if args.markdown:
        make_markdown(report, cards, args.markdown, args.run_url, args.report.name, out)
    print(out / "index.html")


if __name__ == "__main__":
    main()
