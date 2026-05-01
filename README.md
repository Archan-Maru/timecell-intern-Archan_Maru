# Timecell Internship — Technical Test

> **Author:** Archan Maru  
> **Stack:** Python 3.12+ · Google Gemini API · yfinance · dotenv

---

## General Notes — Codebase Philosophy & Standards

The entire codebase across all four tasks follows a consistent set of production-grade engineering standards. These are not afterthoughts — they were architectural decisions made from the start.

### Comprehensive Docstrings

Every public function in every module carries a **Google-style docstring** documenting its purpose, arguments, return values, and (where relevant) side effects. This ensures any developer can understand, maintain, or extend the code without needing to reverse-engineer intent from implementation.

| Module | Functions | Docstring Coverage |
| :--- | :---: | :---: |
| `task_1.py` | 5 | 100% |
| `task_2.py` | 8 | 100% |
| `task_3.py` | 9 | 100% |
| `task_4.py` | 12 | 100% |

Each file also opens with a **module-level docstring** summarizing the task's purpose, architecture, and usage instructions — making it immediately obvious what the file does, without reading a single function.

### Type Hints Throughout

All function signatures use Python type annotations (`-> dict`, `-> float`, `-> str | None`, etc.). Where complex structures are reused (Task 4), **dataclasses** (`Portfolio`, `DecisionInput`, `Assumption`, `PreMortemReport`) replace raw dicts to enforce schema at the language level. This eliminates an entire class of runtime key-errors and makes IDE autocompletion reliable.

### Deterministic Math vs. LLM Separation

A deliberate architectural principle across Tasks 3 and 4: **the LLM never does arithmetic.** All financial calculations — crash losses, runway months, fragility scores, rupee impacts — are computed in pure Python with traceable formulas. The LLM's role is strictly limited to language tasks (assumption extraction, explanation generation, critique). This makes every number in the output auditable and reproducible.


### How to Run

```bash
# Install dependencies
pip install google-generativeai python-dotenv yfinance requests tabulate

# Set up API key
echo GEMINI_API_KEY=your-key-here > .env

# Run any task
python task_1.py
python task_2.py
python task_3.py
python task_4.py
```

---

# Task 01 — Portfolio Risk Calculator
**Run:** `python task_1.py`

---

## Approach
The core logic resides in the `compute_risk_metrics(portfolio, crash_severity)` function. This function is designed to be asset-agnostic, accepting any portfolio dictionary and returning a comprehensive risk assessment.

* **Dynamic Severity:** A key design decision was implementing a `crash_severity` parameter (**0.0** to **1.0**). This eliminates code duplication by allowing a single function to handle both "Severe" and "Moderate" scenarios.
    * **1.0** represents a full market crash.
    * **0.5** represents a moderate **50%** magnitude crash.

### Edge Case Handling
The system includes four explicit assertion tests that validate logic before the main execution:
* **100% Cash Portfolio:** Reports zero loss as the crash percentage for cash is **0**.
* **Zero Allocation Assets:** Assets with **0%** allocation (e.g., BTC at **0%**) do not affect the total value.
* **Empty Portfolio:** Handled via early returns with safe default values to prevent division-by-zero errors.
* **Zero Monthly Expenses:** Returns an **infinite runway** instead of crashing the calculation.

### Bonus Features
* **Parameterized Scenarios:** Moderate crashes are handled via logic rather than redundant functions.
* **Visual CLI:** A horizontal bar chart is rendered in the terminal using ASCII characters via the `print_allocation_chart` function.

 ### AI Usage
 This project was developed using a pair-programming approach with ***claude*** and **Gemini via Antigravity**.
 * **Scaffolding:** AI generated the initial draft of the portfolio structure and output formats.
 * **Edge Case Discovery:** AI assisted in identifying potential failures, such as the division-by-zero risk in expense calculations.
 * **Architecture Review:** The `crash_severity` parameter was adopted following an AI suggestion to improve code modularity and reduce duplication.

---



# Task 02 — Live Market Data Fetch
**Run:** `python task_2.py`

---

## Approach
The script fetches real-time data for three diverse assets using a multi-source pipeline:

| Asset | Source | Rationale |
| :--- | :--- | :--- |
| **BTC** | CoinGecko API | Reliable public API; no authentication required for basic fetching. |
| **NIFTY50** | yfinance (`^NSEI`) | Industry standard for Indian equity indices. |
| **Gold** | yfinance (`GC=F`) | Global benchmark (Gold Futures) converted to local rates. |

### Currency & Gold Transformation
To provide a relevant metric for Indian investors (INR per gram), the script implements a two-step transformation:

* **Live Conversion API:** Integrated a dedicated exchange rate API to automate the **USD/INR** conversion. This demonstrates how real-time currency transformations can be implemented with minimal overhead, ensuring the dashboard remains accurate to current market fluctuations.
* **Unit Conversion:** Gold is globally quoted in USD per troy ounce. The script applies the following formula:

$$\text{Price per Gram (INR)} = \frac{\text{Price per Ounce (USD)} \times \text{Live USD/INR Rate}}{31.1035}$$

### Error Handling & Reliability
* **Graceful Degradation:** Each fetch is wrapped in a `try-except` block. If one API fails, the error is logged, and the specific row displays `ERR` while other assets continue to load.
* **Exit Codes:** The script exits with **Code 1** upon any failure, allowing for easy integration with monitoring systems.
* **Fallback Chain:** Using `yfinance`, the script checks a sequence of data points (**last_price** $\rightarrow$ **regularMarketPrice** $\rightarrow$ **history**) to ensure data is captured even during low-liquidity windows.

### Design Decisions
* **Tabulate Integration:** Used for clean, auto-aligned table rendering in the CLI.
* **Constants:** API URLs and conversion factors are defined at the top of the file for easy maintenance.
* **Logging:** Technical errors are sent to a logger rather than standard `print` statements to keep the UI clean.

### Future Improvements
* **Environment Variables:** Transition from hardcoded keys to a `.env` file structure to meet production security standards.

---



# Task 03 — AI-Powered Portfolio Explainer
**Run:** `python task_3.py`
**Requires:** `GEMINI_API_KEY` in a `.env` file

---

## Approach
The script sends a portfolio to **Google Gemini** (`gemini-2.5-flash-lite`) and receives a structured, plain-English risk explanation — written as a friendly but honest financial advisor would speak to a client.

### Why Gemini?
Google Gemini was chosen for two practical reasons: free-tier availability via [AI Studio](https://aistudio.google.com) and strong instruction-following for structured JSON output. The prompt engineering matters far more than the provider, and Gemini proved reliable at consistently returning valid JSON with minimal post-processing.

### Architecture

The codebase enforces a clean three-layer separation:

| Layer | Function | Responsibility |
| :--- | :--- | :--- |
| **Prompt Builder** | `build_prompt()` | Constructs system + user prompts with pre-computed math |
| **API Caller** | `call_gemini()` | Sends prompts, returns raw text |
| **Output Parser** | `parse_output()` | Validates JSON schema and verdict enum |

This separation ensures each layer can be tested, swapped, or debugged independently.

### Prompt Engineering — What Was Tried, What Worked, What Changed

#### Iteration 1 — Naive prompt
The initial prompt was a simple instruction: *"Explain this portfolio's risk."* The output was vague, generic, and inconsistent in format — sometimes returning bullet points, sometimes paragraphs, and never referencing actual numbers.

#### Iteration 2 — Pre-computed math injection
The first major improvement was **feeding pre-computed crash math into the user prompt** rather than asking the LLM to calculate. The prompt now includes:
* Exact post-crash portfolio value (computed in Python)
* Months of runway post-crash
* Per-asset loss breakdown in ₹

This anchors the LLM to real numbers and eliminates hallucinated arithmetic. A rule was added: *"You MUST mention the months of expenses covered post-crash."* This single constraint dramatically improved output quality — but the responses still lacked consistent structure.

#### Iteration 3 — Role-Context-Task prompting (final)
The final prompt architecture uses the **Role-Context-Task (RCT)** prompting pattern — a structured technique where the prompt is decomposed into three distinct layers:

1. **Role:** The system prompt opens by assigning a persona — *"You are a financial advisor reviewing an Indian investor's portfolio"* — grounding the model's tone and domain expertise.
2. **Context:** The user prompt provides all factual inputs — portfolio value, asset allocation, pre-computed crash losses, and runway months — as structured data the model can reference but never recompute.
3. **Task:** The system prompt closes with an explicit JSON schema (`summary`, `doing_well`, `consider_changing`, `verdict`) and hard constraints on output format, specificity, and verdict values.

This three-layer separation made outputs **consistent, specific, and auditable** across runs. The model stops inventing numbers because the numbers are already provided; it stops being vague because the constraints demand asset names and reasons; and it stops deviating from the format because the schema is enforced both in the prompt and in `parse_output()`.

#### What specifically changed and why:
* **Added anti-vagueness rules:** *"Never be vague. 'Consider rebalancing' alone is not acceptable — say what to rebalance and why."* Without this, the model defaulted to hedge-fund boilerplate.
* **Verdict enum enforcement:** Constrained to exactly `Aggressive | Balanced | Conservative` with validation in `parse_output()`. Early versions occasionally returned `Moderately Aggressive` or similar inventions.
* **Tone-aware system prompts:** Each tone (`beginner`, `experienced`, `expert`) uses a distinct instruction block that adjusts vocabulary and assumed knowledge — not just a temperature change.

### Bonus Features

#### Configurable Tone
Three tone profiles adjust the system prompt's language:

| Tone | Style |
| :--- | :--- |
| `beginner` | No jargon, warm and encouraging, explains every term |
| `experienced` | Direct, skips basics, uses standard investing vocabulary |
| `expert` | Precise financial language — drawdown, concentration risk, liquidity runway |

#### Critic Review (Second LLM Call)
After the primary explanation, a second Gemini call receives both the generated analysis and the raw portfolio data, then critiques it for:
* Numerical accuracy — are the claims grounded in the actual data?
* Actionability — is the advice specific enough to act on?
* Verdict justification — does the label match the numbers?

This self-review catches hallucinations before they reach the client.

### Interactive CLI
The script supports two modes:
* **Example portfolio** — runs the standard ₹1 Crore, 4-asset portfolio from Task 1.
* **Custom input** — interactively collects portfolio details from the terminal, allowing the explainer to work with any asset mix.

### AI Usage
This project was developed using a pair-programming approach with ***Claude*** and **Gemini via Antigravity**.
* **Prompt Iteration:** AI assisted in identifying failure modes in early prompt versions — particularly the tendency for LLMs to invent numbers when not anchored to pre-computed math.
* **Schema Validation:** The JSON parsing and key/verdict validation logic was refined through AI-suggested edge cases (malformed JSON, unexpected verdict strings).
* **Critic Design:** The critic prompt's structure was collaboratively designed to evaluate accuracy against source data rather than just surface-level coherence.

---



# Task 04 — The Pre-Mortem Decision Engine
**Run:** `python task_4.py`
**Requires:** `GEMINI_API_KEY` in a `.env` file

---

## Why This Exists

> *"Show me the assumption you'd have to be wrong about for this to be the wrong call."*

After completing Tasks 1–3, a gap became clear: the system could tell a client their portfolio's **current** risk, but couldn't help them evaluate a **future decision** before committing capital. In wealth management, the most expensive mistakes aren't bad trades — they're unexamined assumptions.

The Pre-Mortem Engine is a CLI tool where a principal describes a capital decision in plain English (e.g., *"I want to move 20% of my portfolio from NIFTY50 into BTC"*), and the system surfaces the hidden assumptions behind that decision, stress-tests each one against real portfolio math, and produces a one-page decision brief.

### Design Philosophy — Math vs. Language

The core architectural decision was a strict separation of concerns, following Timecell's own philosophy of tethering AI reasoning to hard financial math:

| Responsibility | Handled By | Why |
| :--- | :--- | :--- |
| **Assumption extraction** | Gemini (LLM) | Requires natural language understanding to surface implicit beliefs |
| **Fragility scoring** | Python (deterministic) | Must be reproducible and auditable — no LLM arithmetic |
| **Rupee impact calculation** | Python (deterministic) | Financial numbers must be traceable to a formula |
| **Critical question generation** | Gemini (LLM) | Requires synthesis across assumptions — a language task |
| **Final verdict** | Python (rule-based) | Deterministic rules based on runway and fragility counts |

**The LLM never does arithmetic.** Every number in the report links back to a Python function and a traceable formula string.

### Architecture

The pipeline follows four stages:

```
Decision (plain English)
       │
       ▼
┌─────────────────────┐
│  Gemini: Extract    │  ← Language task only
│  3 hidden           │
│  assumptions        │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Python: Score       │  ← Deterministic math
│  fragility, compute │
│  ₹ impact, trace    │
│  formulas           │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Gemini: Generate   │  ← Synthesis task
│  critical question  │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Python: Verdict    │  ← Rule-based
│  PROCEED | CAUTION  │
│  | PAUSE            │
└─────────────────────┘
```

### Assumption Categories & Math

Each assumption maps to a deterministic category with its own math engine:

| Category | Math Applied | Example Break-Even |
| :--- | :--- | :--- |
| **Drawdown Risk** | `reallocated_capital × crash_magnitude` | BTC must not fall more than 80% |
| **Opportunity Cost** | `reallocated_capital × source_asset_return × horizon` | BTC must beat NIFTY50's ~12% annualised return |
| **Liquidity Risk** | `illiquid_capital vs. (monthly_burn × horizon)` | Liquid assets must cover ₹14.4L over 18 months |

### Traceability
Every number in the report carries a `traceable_formula` string that shows exactly how it was computed. For example:

```
At risk:    ₹16,00,000
Formula:    Reallocated Capital (₹20,00,000) × BTC crash magnitude (80%)
```

This ensures a wealth manager can defend any number in the report — no black boxes.

### Fragility Scoring
Each assumption receives a **fragility score** (0–100) computed deterministically:

| Score Range | Label | Meaning |
| :--- | :--- | :--- |
| **0–34** | `SOLID` | Assumption is well-supported by the portfolio math |
| **35–64** | `UNCERTAIN` | Could go either way — warrants monitoring |
| **65–100** | `FRAGILE` | High probability of breaking — the decision hinges on this |

The score is derived from the assumption's category plus portfolio-specific modifiers (e.g., low liquidity ratio increases Liquidity Risk fragility).

### Verdict Rules
The final verdict is **never generated by the LLM** — it follows deterministic rules:

* **PAUSE:** Worst-case runway < 12 months OR ≥ 2 fragile assumptions
* **PROCEED WITH CAUTION:** Worst-case runway < 24 months OR 1 fragile assumption OR forced-seller risk
* **PROCEED:** All other cases

### Sensitivity Analysis (Interactive)
After the initial report, the tool enters an interactive loop where the user can adjust the BTC expected crash percentage and instantly see how the entire report recalculates. This allows a principal to ask *"What if BTC drops 90% instead of 80%?"* and see the downstream effects on runway, fragility, and verdict — all without a new LLM call for the math.

### Error Handling
* **Rate Limit Resilience:** All Gemini calls use `generate_with_retry()` with exponential backoff (base delay: 10s, up to 5 retries) to handle `ResourceExhausted` (HTTP 429) errors gracefully.
* **Deep Copy Isolation:** Sensitivity runs operate on `copy.deepcopy()` of the original input, ensuring mutations never leak between runs.
* **Structured Validation:** LLM responses are validated for required JSON keys and category enums before entering the math pipeline.

### AI Usage
This project was developed using a pair-programming approach with ***Claude*** and **Gemini via Antigravity**.
* **Concept Ideation:** The pre-mortem framework was inspired by researching and discussion with AI about what decision tools are missing in wealth management  — the idea of surfacing *assumptions* rather than making *predictions* emerged from this conversation.
* **Architecture Review:** The strict math-vs-LLM separation was refined through AI code review, which flagged early versions where the LLM was inadvertently asked to compute rupee impacts.
* **Traceability Design:** The `traceable_formula` pattern was adopted after AI suggested that financial tools must be auditable — every number should link back to its computation.
* **Rate Limit Handling:** The exponential backoff wrapper was implemented following AI guidance on production-grade API integration patterns.
