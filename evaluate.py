"""
Accuracy Evaluator for Feedback Categoriser
--------------------------------------------
Compares model classifications against manual labels.

Usage:
    python evaluate.py --classified output/feedback_classified_2025-01-01.csv \
                       --ground-truth data/ground_truth.csv
"""

import csv
import argparse
import json
from pathlib import Path
from collections import defaultdict


VALID_CATEGORIES = [
    "Bug", "Feature Request", "Performance", "UX / Usability",
    "Onboarding", "Pricing", "Documentation", "Security",
    "Positive Feedback", "Other",
]


def load_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compute_accuracy(classified: list[dict],
                     ground_truth: list[dict],
                     field: str = "category") -> dict:
    gt_map = {int(r["id"]): r[field] for r in ground_truth}
    correct = 0
    total   = 0
    errors  = []

    per_class = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    for row in classified:
        rid = int(row["id"])
        if rid not in gt_map:
            continue
        total += 1
        predicted = row.get(field, "")
        actual    = gt_map[rid]

        if predicted == actual:
            correct += 1
            per_class[actual]["tp"] += 1
        else:
            per_class[actual]["fn"] += 1
            per_class[predicted]["fp"] += 1
            errors.append({
                "id": rid,
                "predicted": predicted,
                "actual":    actual,
                "text":      row.get("feedback_text", "")[:80],
            })

    accuracy = correct / total if total > 0 else 0

    # Per-class precision / recall
    class_metrics = {}
    for cls, counts in per_class.items():
        tp = counts["tp"]; fp = counts["fp"]; fn = counts["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0)
        class_metrics[cls] = {
            "precision": round(precision, 3),
            "recall":    round(recall, 3),
            "f1":        round(f1, 3),
        }

    return {
        "accuracy": round(accuracy, 3),
        "correct":  correct,
        "total":    total,
        "per_class": class_metrics,
        "errors":   errors,
    }


def print_report(results: dict, field: str) -> None:
    print("=" * 60)
    print(f"  Accuracy Report — {field}")
    print("=" * 60)
    print(f"  Overall accuracy: {results['accuracy']:.1%}  "
          f"({results['correct']}/{results['total']})")
    print()
    print(f"  {'Class':<24} {'Precision':>9} {'Recall':>9} {'F1':>9}")
    print("  " + "─" * 54)
    for cls, m in sorted(results["per_class"].items()):
        print(f"  {cls:<24} {m['precision']:>9.3f} {m['recall']:>9.3f} {m['f1']:>9.3f}")

    if results["errors"]:
        print(f"\n  Top misclassifications (showing first 5):")
        for e in results["errors"][:5]:
            print(f"    ID {e['id']}: predicted '{e['predicted']}' → actual '{e['actual']}'")
            print(f"    Text: \"{e['text']}…\"")
            print()


def generate_ground_truth_template(classified_path: str,
                                   output_path: str = "data/ground_truth.csv") -> None:
    """Generate a template ground truth CSV from classified output."""
    rows = load_csv(classified_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "feedback_text", "category", "sentiment", "priority"])
        for r in rows:
            # Pre-fill with model predictions — human reviews and corrects
            writer.writerow([
                r["id"], r["feedback_text"],
                r.get("category", ""),
                r.get("sentiment", ""),
                r.get("priority", ""),
            ])
    print(f"Ground truth template written to {output_path}")
    print("Review and correct the labels, then run evaluate.py with --ground-truth.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--classified",    required=False)
    parser.add_argument("--ground-truth",  required=False)
    parser.add_argument("--generate-template", action="store_true")
    parser.add_argument("--field", default="category",
                        help="Which field to evaluate (category|sentiment|priority)")
    args = parser.parse_args()

    if args.generate_template:
        if not args.classified:
            print("[error] --classified required with --generate-template")
            return
        generate_ground_truth_template(args.classified)
        return

    if not args.classified or not args.ground_truth:
        print("Usage: python evaluate.py --classified <path> --ground-truth <path>")
        print("   or: python evaluate.py --generate-template --classified <path>")
        return

    classified   = load_csv(args.classified)
    ground_truth = load_csv(args.ground_truth)
    results = compute_accuracy(classified, ground_truth, field=args.field)
    print_report(results, args.field)


if __name__ == "__main__":
    main()
