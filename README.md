# User Feedback Categoriser

**AI-powered classification of product feedback at scale.**

Takes a CSV of support tickets, app reviews, or NPS comments and classifies each one by category, affected feature, sentiment, and priority. Outputs a clean CSV and a 4-panel dashboard chart.

---

## The Problem It Solves

Product teams receive hundreds of feedback items per month. Manually categorising them takes a data analyst 2–3 days per quarter. This tool does it in under 60 seconds — with consistent taxonomy and a built-in accuracy evaluator.

**Target user:** Product managers and data analysts at companies with active user feedback pipelines.

---

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/feedback-categoriser
cd feedback-categoriser
pip install -r requirements.txt

cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

# Run with built-in sample data
python app.py

# Run with your own CSV
python app.py --input your_feedback.csv --output results/
```

---

## Input Format

Your CSV must have at minimum: `id`, `feedback_text`

Optional columns: `source`, `date`

```csv
id,feedback_text,source,date
1,The app crashes on export,App Store,2025-01-15
2,Would love dark mode,Support Ticket,2025-01-16
```

---

## Output

| File | Description |
|------|-------------|
| `output/feedback_classified_YYYY-MM-DD.csv` | Original rows + 5 new classification columns |
| `output/dashboard.png` | 4-panel chart: categories, sentiment, priority, top features |

**New columns added to CSV:**

| Column | Values |
|--------|--------|
| `category` | Bug / Feature Request / Performance / UX / Onboarding / Pricing / Documentation / Security / Positive Feedback / Other |
| `affected_feature` | Authentication / Dashboard / Settings / Search / Notifications / Billing / API / Mobile App / Onboarding Flow / Reporting / Integrations / Data Export / General |
| `sentiment` | Positive / Neutral / Negative |
| `priority` | High / Medium / Low |
| `one_line_summary` | ≤15 word plain-English summary |

---

## Accuracy Evaluation

After classifying, manually label a sample of 20–50 items and measure accuracy:

```bash
# Step 1: Generate a template with pre-filled model predictions
python evaluate.py --generate-template \
    --classified output/feedback_classified_2025-01-01.csv

# Step 2: Open data/ground_truth.csv and correct the labels

# Step 3: Run the evaluation
python evaluate.py \
    --classified output/feedback_classified_2025-01-01.csv \
    --ground-truth data/ground_truth.csv
```

**Evaluation output:**
```
Overall accuracy: 84.0%  (42/50)

Class                    Precision    Recall        F1
────────────────────────────────────────────────────
Bug                          0.923     0.857     0.889
Feature Request              0.800     0.889     0.842
Performance                  0.833     0.833     0.833
...
```

---

## Cost Model

| Scale | Items | API cost |
|-------|-------|----------|
| Small team | 100 items/month | ~$0.02/month |
| Mid-size | 1,000 items/month | ~$0.20/month |
| Large | 10,000 items/month | ~$2.00/month |

*Based on Claude Sonnet pricing, 10 items per batch.*

---

## Technical Decisions

**Why batch processing?** Sending all items in one request risks hitting context limits and makes partial failure handling harder. Batches of 10 are reliable and cost-efficient.

**Why a fixed taxonomy?** Open-ended categorisation produces inconsistent labels that are hard to aggregate. A fixed taxonomy with well-defined priority rules enables reliable trend analysis over time.

**Why Claude Sonnet?** The structured JSON output and priority rules require genuine reasoning, not just pattern matching. Sonnet produces significantly more consistent priority assignments than Haiku.

---

## What I Would Build Next (v2)

1. **Trend detection** — flag categories that have increased > 20% week-over-week
2. **Slack integration** — post daily summary of High priority items to #product-feedback
3. **Notion database push** — automatically create Notion entries for each High priority item
4. **Multi-language support** — classify feedback in Hindi, Spanish, etc.

---

## PM Brief

**User problem:** Manual feedback categorisation is slow, inconsistent, and does not scale. Important signals (bug spikes, feature demand clusters) arrive days late.

**Solution:** Automated classification pipeline with consistent taxonomy, priority scoring, and visual dashboard.

**Success metrics:**
- Classification accuracy ≥ 80% vs human labels
- Processing time < 60 seconds for 100 items
- API cost < $0.05 per 100 items

**Top two risks:**
1. Taxonomy drift — the fixed categories may not fit every product domain. Mitigation: expose taxonomy as a configurable JSON file in v2.
2. Priority disagreement — "High" vs "Medium" judgment calls vary by company context. Mitigation: expose priority rules as editable config.

---

*Built as part of a 12-week AI PM Portfolio Programme.*
