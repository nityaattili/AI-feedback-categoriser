"""
User Feedback Categoriser
--------------------------
Classifies product feedback (support tickets, app reviews, NPS comments)
using Claude. Outputs a categorised CSV and a summary dashboard chart.

Usage:
    python app.py --input data/sample_feedback.csv
    python app.py --input data/sample_feedback.csv --output results/
    python app.py --input data/sample_feedback.csv --batch-size 10
"""

import os
import json
import argparse
import csv
import datetime
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False


# ── Taxonomy ──────────────────────────────────────────────────────────────────
CATEGORIES = [
    "Bug",
    "Feature Request",
    "Performance",
    "UX / Usability",
    "Onboarding",
    "Pricing",
    "Documentation",
    "Security",
    "Positive Feedback",
    "Other",
]

AFFECTED_FEATURES = [
    "Authentication",
    "Dashboard",
    "Settings",
    "Search",
    "Notifications",
    "Billing",
    "API",
    "Mobile App",
    "Onboarding Flow",
    "Reporting",
    "Integrations",
    "Data Export",
    "General",
]

SYSTEM_PROMPT = f"""You are a product analyst at a B2B SaaS company.
Classify each piece of user feedback and return ONLY a JSON array.
Each element must have exactly these keys:

{{
  "id": <the input id integer>,
  "category": one of {json.dumps(CATEGORIES)},
  "affected_feature": one of {json.dumps(AFFECTED_FEATURES)},
  "sentiment": "Positive" | "Neutral" | "Negative",
  "priority": "High" | "Medium" | "Low",
  "one_line_summary": "under 15 words, plain English, no quotes"
}}

Priority rules:
- High: data loss, security issue, feature completely broken, payment failure
- Medium: partial functionality broken, significant friction, repeated complaint
- Low: cosmetic issue, nice-to-have, already works but could be better

Return ONLY the JSON array. No markdown, no preamble, no explanation."""


# ── Sample data generator ──────────────────────────────────────────────────────
SAMPLE_FEEDBACK = [
    "The app crashes every time I try to export a report to PDF. This is urgent.",
    "Would love dark mode support. My eyes hurt using this at night.",
    "Login takes 10 seconds on mobile. Very frustrating.",
    "The dashboard is clean and easy to understand. Great work!",
    "I can not find where to add team members. The settings are confusing.",
    "Why is the API rate limit so low? 100 requests/hour is not enough for production.",
    "Billing page shows wrong amount after applying coupon code.",
    "The onboarding tutorial is excellent, very clear.",
    "Search is useless — it only searches titles, not content inside documents.",
    "Data export does not include custom fields. This is a blocker for us.",
    "Would be amazing if you integrated with Slack for notifications.",
    "The notification emails are going to spam. Please fix DKIM.",
    "Password reset email takes over 15 minutes to arrive.",
    "Love the new filters on the dashboard!",
    "Mobile app does not save my session — I have to log in every time I open it.",
    "Can you add two-factor authentication? Security is important for our compliance.",
    "The CSV export encoding is broken — special characters show as question marks.",
    "Documentation is outdated, still references the old UI.",
    "Really happy with the product overall. Support team is also great.",
    "Charts do not render on Firefox. Works fine on Chrome.",
]


def generate_sample_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "feedback_text", "source", "date"])
        sources = ["App Store", "Google Play", "Support Ticket", "NPS Survey", "In-app"]
        import random; random.seed(42)
        for i, text in enumerate(SAMPLE_FEEDBACK, 1):
            writer.writerow([
                i, text,
                random.choice(sources),
                f"2025-{random.randint(1,3):02d}-{random.randint(1,28):02d}",
            ])
    print(f"  Sample data written to {path}")


# ── Classification ─────────────────────────────────────────────────────────────
def build_batch_message(rows: list[dict]) -> str:
    items = []
    for row in rows:
        items.append(f'{{"id": {row["id"]}, "feedback": {json.dumps(row["feedback_text"])}}}')
    return "Classify the following feedback items:\n[\n" + ",\n".join(items) + "\n]"


def classify_batch(rows: list[dict], client) -> list[dict]:
    """Send one batch to the LLM and return list of classified dicts."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_batch_message(rows)}],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\n?```$",       "", raw, flags=re.MULTILINE)
    return json.loads(raw)


def classify_all(rows: list[dict], api_key: str,
                 batch_size: int = 10) -> list[dict]:
    if not ANTHROPIC_AVAILABLE:
        raise ImportError("Run: pip install anthropic")
    client = anthropic.Anthropic(api_key=api_key)

    results = []
    total   = len(rows)
    for start in range(0, total, batch_size):
        batch = rows[start:start + batch_size]
        print(f"  Classifying items {start+1}–{min(start+batch_size, total)} of {total} …")
        try:
            classified = classify_batch(batch, client)
            results.extend(classified)
        except json.JSONDecodeError as e:
            print(f"  [warn] JSON parse error in batch {start}: {e}")
        except Exception as e:
            print(f"  [warn] Batch {start} failed: {e}")
        if start + batch_size < total:
            time.sleep(0.5)   # gentle rate limiting
    return results


# ── Merge & Save ──────────────────────────────────────────────────────────────
def merge_results(original_rows: list[dict],
                  classified: list[dict]) -> list[dict]:
    """Join original rows with classification results on id."""
    classified_map = {r["id"]: r for r in classified}
    merged = []
    for row in original_rows:
        c = classified_map.get(row["id"], {})
        merged.append({
            "id":               row["id"],
            "feedback_text":    row["feedback_text"],
            "source":           row.get("source", ""),
            "date":             row.get("date", ""),
            "category":         c.get("category", "Other"),
            "affected_feature": c.get("affected_feature", "General"),
            "sentiment":        c.get("sentiment", "Neutral"),
            "priority":         c.get("priority", "Medium"),
            "one_line_summary": c.get("one_line_summary", ""),
        })
    return merged


def save_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


# ── Dashboard ─────────────────────────────────────────────────────────────────
PALETTE = {
    "Bug":              "#E24B4A",
    "Feature Request":  "#534AB7",
    "Performance":      "#BA7517",
    "UX / Usability":   "#1D9E75",
    "Onboarding":       "#185FA5",
    "Pricing":          "#D4537E",
    "Documentation":    "#639922",
    "Security":         "#D85A30",
    "Positive Feedback":"#0F6E56",
    "Other":            "#888780",
}
PRIORITY_COLORS = {"High": "#E24B4A", "Medium": "#BA7517", "Low": "#1D9E75"}


def generate_dashboard(rows: list[dict], output_dir: Path) -> None:
    if not PLOTTING_AVAILABLE:
        print("  [skip] matplotlib/pandas not available — skipping charts.")
        return

    df = pd.DataFrame(rows)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor("#FAFAF8")
    fig.suptitle("User Feedback Analysis Dashboard",
                 fontsize=16, fontweight="bold", y=0.98)

    # ── Chart 1: Category distribution ────────────────────────────────────────
    ax1 = axes[0, 0]
    cat_counts = df["category"].value_counts()
    colors1 = [PALETTE.get(c, "#888780") for c in cat_counts.index]
    bars = ax1.barh(cat_counts.index, cat_counts.values, color=colors1, edgecolor="none")
    ax1.set_title("Feedback by Category", fontweight="bold", fontsize=12)
    ax1.set_xlabel("Count")
    ax1.invert_yaxis()
    for bar, val in zip(bars, cat_counts.values):
        ax1.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                 str(val), va="center", fontsize=9)
    ax1.set_facecolor("#F9F8F5")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    # ── Chart 2: Sentiment breakdown ──────────────────────────────────────────
    ax2 = axes[0, 1]
    sentiment_counts = df["sentiment"].value_counts()
    sent_colors = {"Positive": "#0F6E56", "Neutral": "#888780", "Negative": "#E24B4A"}
    colors2 = [sent_colors.get(s, "#888780") for s in sentiment_counts.index]
    wedges, texts, autotexts = ax2.pie(
        sentiment_counts.values, labels=sentiment_counts.index,
        colors=colors2, autopct="%1.0f%%", startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2}
    )
    ax2.set_title("Sentiment Distribution", fontweight="bold", fontsize=12)

    # ── Chart 3: Priority breakdown ───────────────────────────────────────────
    ax3 = axes[1, 0]
    priority_order = ["High", "Medium", "Low"]
    priority_counts = df["priority"].value_counts().reindex(priority_order, fill_value=0)
    colors3 = [PRIORITY_COLORS[p] for p in priority_order]
    ax3.bar(priority_order, priority_counts.values, color=colors3, edgecolor="none", width=0.5)
    ax3.set_title("Feedback by Priority", fontweight="bold", fontsize=12)
    ax3.set_ylabel("Count")
    for i, (p, v) in enumerate(zip(priority_order, priority_counts.values)):
        ax3.text(i, v + 0.1, str(v), ha="center", fontsize=11, fontweight="bold")
    ax3.set_facecolor("#F9F8F5")
    ax3.spines["top"].set_visible(False)
    ax3.spines["right"].set_visible(False)

    # ── Chart 4: Top affected features ────────────────────────────────────────
    ax4 = axes[1, 1]
    feat_counts = df["affected_feature"].value_counts().head(8)
    ax4.barh(feat_counts.index, feat_counts.values,
             color="#534AB7", alpha=0.8, edgecolor="none")
    ax4.set_title("Top Affected Features", fontweight="bold", fontsize=12)
    ax4.set_xlabel("Count")
    ax4.invert_yaxis()
    ax4.set_facecolor("#F9F8F5")
    ax4.spines["top"].set_visible(False)
    ax4.spines["right"].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    chart_path = output_dir / "dashboard.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Dashboard chart → {chart_path}")


def print_summary(rows: list[dict]) -> None:
    total = len(rows)
    high  = sum(1 for r in rows if r["priority"] == "High")
    neg   = sum(1 for r in rows if r["sentiment"] == "Negative")

    print("\n" + "=" * 60)
    print("  Classification Summary")
    print("=" * 60)
    print(f"  Total items classified : {total}")
    print(f"  High priority items    : {high}")
    print(f"  Negative sentiment     : {neg}")
    print()

    # Category breakdown
    from collections import Counter
    cat_counts = Counter(r["category"] for r in rows)
    print("  By category:")
    for cat, count in cat_counts.most_common():
        bar = "█" * count
        print(f"    {cat:<22} {bar} {count}")

    # High priority items
    hp_items = [r for r in rows if r["priority"] == "High"]
    if hp_items:
        print(f"\n  High priority items (fix first):")
        for r in hp_items[:5]:
            print(f"    [{r['category']}] {r['one_line_summary']}")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="User Feedback Categoriser")
    parser.add_argument("--input",      required=False, default=None)
    parser.add_argument("--output",     default="output/")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--generate-sample", action="store_true",
                        help="Generate a sample CSV and exit")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.generate_sample:
        generate_sample_csv(Path("data/sample_feedback.csv"))
        return

    if not args.input:
        print("[info] No --input specified. Generating sample data and classifying it.")
        sample_path = Path("data/sample_feedback.csv")
        generate_sample_csv(sample_path)
        args.input = str(sample_path)

    print("=" * 60)
    print("  User Feedback Categoriser")
    print("=" * 60)

    # Load input CSV
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] File not found: {input_path}")
        return

    with open(input_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Ensure id is int
    for r in rows:
        r["id"] = int(r.get("id", 0))

    print(f"\n[1/3] Loaded {len(rows)} feedback items from {input_path}")

    # Classify
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[error] ANTHROPIC_API_KEY not set.")
        return

    print(f"\n[2/3] Classifying with Claude (batch size={args.batch_size}) …")
    classified = classify_all(rows, api_key, batch_size=args.batch_size)
    merged = merge_results(rows, classified)

    # Save
    date_slug = datetime.date.today().isoformat()
    csv_path  = out_dir / f"feedback_classified_{date_slug}.csv"
    save_csv(merged, csv_path)

    # Dashboard
    print(f"\n[3/3] Generating dashboard …")
    generate_dashboard(merged, out_dir)

    print_summary(merged)
    print(f"\n✓ Classified CSV  → {csv_path}")


if __name__ == "__main__":
    main()
