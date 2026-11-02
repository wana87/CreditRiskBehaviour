# Credit Behaviour Profiler

A Python Streamlit app built around the five supplied YAML configurations and the five synthetic reports in `data/test-data.jsonl`.

## Run locally

Use Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The bundled demo runs automatically. Select a borrower report to inspect the summary, payment windows, facilities, graph, and complete feature output. You can also upload JSON/JSONL or paste a report, then click **Run profiler**. Export selected/all results as JSON, or the scalar features as CSV.

The refreshed dashboard includes a blue gradient header, icon-led metric cards and tabs, a borrower identity section, historical observation summaries, interactive payment-window comparisons, a monthly timeline, and a facility-exposure chart. Teal identifies months with no overdue days, while amber identifies months with overdue days reported. Colours describe historical observations, not predicted credit ratings.

## Deploy to Streamlit Community Cloud

1. Extract the ZIP and upload the entire contents of this project directory to a GitHub repository. Include `app.py`, `ui.py`, `styles.css`, `engine.py`, `requirements.txt`, `.streamlit/`, `config/`, and `data/`. The hidden `.streamlit/` directory supplies the light dashboard theme.
2. In Streamlit Community Cloud, create an app and select that repository and branch.
3. Set the main file path to `app.py` (or the relative path to it if you used a subfolder).
4. Under advanced settings, select Python 3.12 and deploy.

Dependencies are installed from `requirements.txt`. No API keys, database, or external profiling service are required. Deployment instructions: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## How the configuration is used

| File | Role |
| --- | --- |
| `config/input-mappings.yml` | Extracts and converts scalar/array values from the incoming report. |
| `config/pre-processing.yml` | Normalizes the report date and calculates the hidden timestamp. |
| `config/feature-encoders.yml` | Calculates all 19 configured snapshot, payment-window, and rate features in file order. |
| `config/graph.yml` | Builds Borrower and Report vertices plus the SUBMITTED edge. |
| `config/summary.yml` | Controls the displayed summary labels, order, and value paths. |

The application and orchestration are Python. The original expressions embedded in YAML use Lua syntax; they run through Lupa's embedded Lua 5.4 runtime so the supplied formulas remain editable and retain their behavior. `in.$1` / `out.$1` references are adapted to runtime input/output arrays. This is not a rewrite of the formulas into native Python.

Edit the repository's YAML files and restart/redeploy to modify the pipeline. Configurations are viewable in the app; visitors can upload data only. The runtime exposes only the helpers needed by the supplied expressions and limits Lua memory and instruction count.

## Calculation semantics and compatibility

- The analysis reporting period, not today's date, anchors the 3-, 12-, and 24-month inclusive windows.
- Only payment slots marked `REPORTED` contribute to payment history metrics. Future periods and out-of-window periods are excluded.
- Slot counts span all facilities. Two facilities reported in the same month contribute two slots.
- Zero reported slots produce a null rate; no delinquency produces a null recency. `<NaN>` defaults export as JSON `null` and display as N/A.
- Outstanding principal is summed across all reported facilities, exactly as configured.
- Missing array leaves retain their positions so related payment/facility arrays stay aligned.
- Missing transaction dates use the current UTC time. `_query_id` uses a supplied `_query_id` or falls back to the transaction ID. These are application conventions because the original engine context was not supplied.
- The hidden `transaction.ts` is calculated internally and omitted from exported visible features.
- Graphs are built per report and exported as JSON; the app does not persist a graph database or combine reports into a graph history.
- Supported encodings are `expression-encoding` and the supplied ISO-8601-to-Unix-milliseconds conversion. Supported paths are the supplied dotted scalar paths, array projections such as `$.facilities..payment_history_24m..period`, and flat feature lookups such as `$.features.['transaction.id']`. Arbitrary JSONPath operators and other engine encoding types are not implemented.
- Maximum input size is 5 MB and 100 report objects. Invalid records are listed with errors while valid records still process. Results are held in Streamlit session memory and downloads; uploaded inputs are not saved to disk by application code.

## Verify

```bash
python -m unittest -v test_engine.py test_app.py
```

Tests compare all five supplied reports against independent Python reference calculations and check empty histories, missing fields, month boundaries, date normalization, JSON formats, graph/summary output, and restricted expression execution. Original-engine expected output was not supplied, so these tests establish agreement with the supplied formulas rather than parity with an external engine.

All 11 tests passed on Python 3.12.14 with the pinned dependencies in `requirements.txt`. The UI tests render the five demo reports, switch between them, process pasted JSON, and check validation feedback. A browser preview was also checked locally. Generated outputs for the supplied data are included in `data/demo-results.json`.

`app.py` orchestrates the UI, `ui.py` provides presentation helpers and interactive charts, and `styles.css` plus `.streamlit/config.toml` define the visual theme. `engine.py` remains independent of presentation and can also be imported directly:

```python
from engine import load_config, parse_records, profile

config = load_config("config")
with open("data/test-data.jsonl", encoding="utf-8") as file:
    records = parse_records(file.read())
result = profile(records[0], config)
```
