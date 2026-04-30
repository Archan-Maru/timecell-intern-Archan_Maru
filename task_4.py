"""
Task 04 — The Pre-Mortem Engine

"Show me the assumption you'd have to be wrong about for this to be the wrong call."

A principal describes a capital decision in plain English.
This tool surfaces the hidden assumptions behind that decision,
stress-tests each one against the actual portfolio math, and
produces a one-page decision brief they can defend in any room.

Architecture follows Timecell's four pillars:
  A — Math:      All numbers computed deterministically. The LLM never does arithmetic.
  B — Conviction: Every assumption carries a fragility score backed by the math.
  C — Coverage:  BTC and Indian equity are first-class inputs.
  D — Traceable: Every output links back to the input and the formula that produced it.

Usage:
    load your Gemini API key in the .env file as GEMINI_API_KEY="your-key-here"
    python task_4.py
"""

import os
import copy
import json
import time
import textwrap
from datetime import datetime
from dataclasses import dataclass
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))


@dataclass
class Portfolio:
    """Current state of the principal's capital."""
    total_value_inr:       float
    monthly_expenses_inr:  float
    liquid_assets_pct:     float   # % of portfolio accessible within 30 days
    assets: list[dict]             # same structure as Tasks 01-03


@dataclass
class DecisionInput:
    """A capital decision the principal is considering."""
    description:        str       # plain English: "I want to move 20% into BTC"
    portfolio:          Portfolio
    horizon_months:     int       # how long before they might need this capital
    dependents:         int       # number of people relying on this portfolio
    # Extracted fields to make math fully deterministic
    reallocated_pct:    float = 20.0
    source_asset:       str = "NIFTY50"
    target_asset:       str = "BTC"


@dataclass
class ExtractedAssumption:
    """Raw assumption extracted by the LLM."""
    category: str
    text: str


@dataclass
class Assumption:
    """
    One assumption that the decision depends on.
    Math is computed deterministically — the LLM only surfaces the assumption text.
    """
    text:              str        # what the assumption is
    fragility_score:   int        # 0–100: how easily this breaks (higher = more fragile)
    fragility_label:   str        # SOLID | UNCERTAIN | FRAGILE
    break_even_value:  str        # the number at which this assumption fails
    rupee_impact:      float      # portfolio loss in INR if this assumption is wrong
    traceable_formula: str        # the exact formula used to compute rupee_impact


@dataclass
class PreMortemReport:
    """Full output of the pre-mortem analysis."""
    decision:            str
    assumptions:         list[Assumption]
    worst_case_loss_inr: float
    current_runway:      float      # months at current portfolio value
    worst_case_runway:   float      # months if all fragile assumptions break
    forced_seller_risk:  bool       # would they be forced to sell at worst time?
    critical_question:   str        # the one question they must answer before acting
    verdict:             str        # PROCEED | PROCEED WITH CAUTION | PAUSE
    current_runway_trace:  str      # traceable formula string for current runway
    worst_case_runway_trace: str    # traceable formula string for worst-case runway


# ── Math engine (deterministic — no LLM) ─────────────────────────────────────

def compute_runway(portfolio_value: float, monthly_expenses: float) -> float:
    """How many months can expenses be covered from this portfolio value."""
    if monthly_expenses <= 0:
        return float("inf")
    return round(portfolio_value / monthly_expenses, 1)


def compute_post_crash_value(portfolio: Portfolio, crash_severity: float = 1.0) -> float:
    """
    Portfolio value after crash scenario.
    crash_severity: 1.0 = full crash, 0.5 = moderate.
    Formula: sum of (asset_value × crash_pct × severity) across all assets.
    """
    post_crash = portfolio.total_value_inr
    for asset in portfolio.assets:
        asset_value  = portfolio.total_value_inr * (asset["allocation_pct"] / 100)
        crash_loss   = asset_value * (asset["expected_crash_pct"] / 100) * crash_severity
        post_crash  += crash_loss
    return round(post_crash, 2)


def compute_liquid_capital(portfolio: Portfolio) -> float:
    """Capital accessible within 30 days."""
    return portfolio.total_value_inr * (portfolio.liquid_assets_pct / 100)


def compute_fragility_score(extracted: ExtractedAssumption, decision_input: DecisionInput) -> tuple[int, str, str]:
    """
    Deterministic fragility scoring based on assumption category and portfolio math.
    Returns: (score 0-100, label, break_even_value_description)
    """
    portfolio = decision_input.portfolio
    horizon_months = decision_input.horizon_months
    category = extracted.category
    
    score = 40  

    if category == "Drawdown Risk":
        score += 35
        target_assets = [a for a in portfolio.assets if decision_input.target_asset.lower() in a["name"].lower()]
        if target_assets:
            target = target_assets[0]
            crash_pct = abs(target["expected_crash_pct"])
            alloc_value = portfolio.total_value_inr * (target["allocation_pct"] / 100)
            break_even = f"{target['name']} must not fall more than {crash_pct}% (a loss of ₹{alloc_value * (crash_pct/100):,.0f})"
        else:
            break_even = "Target asset must not experience severe drawdown."

    elif category == "Opportunity Cost":
        score += 15
        # Assuming 12% annualized return for NIFTY as baseline for opportunity cost
        expected_annual_return = 12.0
        expected_period_return = expected_annual_return * (horizon_months / 12)
        realloc_value = portfolio.total_value_inr * (decision_input.reallocated_pct / 100)
        expected_gain = realloc_value * (expected_period_return / 100)
        
        break_even = f"{decision_input.target_asset} must appreciate >₹{expected_gain:,.0f} ({expected_period_return:.1f}%) over {horizon_months}m just to match {decision_input.source_asset} historical returns."

    elif category == "Liquidity Risk":
        liquid_ratio = portfolio.liquid_assets_pct / 100
        if liquid_ratio < 0.20:
            score += 25
        elif liquid_ratio > 0.50:
            score -= 10
            
        liquid = compute_liquid_capital(portfolio)
        required_liquid = portfolio.monthly_expenses_inr * horizon_months
        break_even = f"You need ≥ ₹{required_liquid:,.0f} liquid for the {horizon_months}m horizon (currently have ₹{liquid:,.0f})"

    else:
        # Default safety net
        safe_runway = compute_runway(compute_post_crash_value(portfolio), portfolio.monthly_expenses_inr)
        break_even = f"Post-crash runway must stay above 12 months (currently {safe_runway:.1f} months)"

    score = max(0, min(100, score))

    if score >= 65:
        label = "FRAGILE"
    elif score >= 35:
        label = "UNCERTAIN"
    else:
        label = "SOLID"

    return score, label, break_even


def compute_rupee_impact(extracted: ExtractedAssumption, decision_input: DecisionInput) -> tuple[float, str]:
    """
    Deterministic rupee impact if this assumption breaks.
    Returns: (loss in INR, formula description for traceability)
    """
    portfolio = decision_input.portfolio
    category = extracted.category

    if category == "Drawdown Risk":
        target_assets = [a for a in portfolio.assets if decision_input.target_asset.lower() in a["name"].lower()]
        if target_assets:
            target = target_assets[0]
            crash_pct = abs(target["expected_crash_pct"])
            alloc_value = portfolio.total_value_inr * (decision_input.reallocated_pct / 100)
            crash_loss = alloc_value * (crash_pct / 100)
            formula = f"Reallocated Capital (₹{alloc_value:,.0f}) × {target['name']} crash magnitude ({crash_pct}%)"
            return round(crash_loss, 2), formula

    elif category == "Opportunity Cost":
        expected_annual_return = 12.0
        expected_period_return = expected_annual_return * (decision_input.horizon_months / 12)
        realloc_value = portfolio.total_value_inr * (decision_input.reallocated_pct / 100)
        expected_gain = realloc_value * (expected_period_return / 100)
        formula = f"Reallocated Capital (₹{realloc_value:,.0f}) × {decision_input.source_asset} expected return ({expected_period_return:.1f}% over {decision_input.horizon_months}m)"
        return round(expected_gain, 2), formula

    elif category == "Liquidity Risk":
        illiquid_value = portfolio.total_value_inr * (1 - portfolio.liquid_assets_pct / 100)
        formula = f"Illiquid capital (₹{illiquid_value:,.0f}) = {100 - portfolio.liquid_assets_pct}% of total portfolio"
        return round(illiquid_value, 2), formula

    # Default
    post_crash = compute_post_crash_value(portfolio)
    total_loss = portfolio.total_value_inr - post_crash
    formula    = f"Full crash scenario: ₹{portfolio.total_value_inr:,.0f} → ₹{post_crash:,.0f}"
    return round(total_loss, 2), formula


# ── LLM layer (assumption extraction only) ───────────────────────────────────

def generate_with_retry(model: genai.GenerativeModel, prompt: str, max_retries: int = 5, base_delay: float = 10.0):
    """Wrapper to handle Gemini's ResourceExhausted (429) rate limits with exponential backoff."""
    delay = base_delay
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except ResourceExhausted as e:
            if attempt == max_retries - 1:
                raise
            print(f"  [rate limit] API quota exceeded. Retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2


def extract_assumptions(decision_input: DecisionInput) -> list[ExtractedAssumption]:
    """
    Gemini's only job: read a plain-English decision and surface
    the hidden assumptions behind it. No math. No recommendations.
    
    Returns structured categories to map to deterministic math properly.
    """
    asset_summary = ", ".join(
        f"{a['name']} ({a['allocation_pct']}%, expected crash: {a['expected_crash_pct']}%)" for a in decision_input.portfolio.assets
    )

    system_prompt = textwrap.dedent("""
        You are a CIO at an Indian family office. Your job is to surface the hidden assumptions
        behind a capital decision — the things the principal is betting on without saying out loud.

        Rules:
        - Return EXACTLY 3 assumptions as a JSON array of objects.
        - The objects must have two keys: "category" and "text".
        - The categories MUST BE EXACTLY: "Drawdown Risk", "Opportunity Cost", and "Liquidity Risk".
        - When mentioning crash scenarios, you MUST use the exact expected crash percentage provided in the asset mix (e.g., if BTC crash is -80%, use 80%, do NOT invent a number like 50%).
        - Assumptions must be falsifiable — something that can be proven wrong by a real event.
        - Do NOT give advice. Do NOT recommend. Only surface what is being assumed.
        - Return only the JSON array. Nothing else.

        Example output format:
        [
          {"category": "Drawdown Risk", "text": "BTC will not suffer its expected 80% drawdown within the 18-month horizon."},
          {"category": "Opportunity Cost", "text": "The 20% moved to BTC will outperform the reliable historical yield of NIFTY50."},
          {"category": "Liquidity Risk", "text": "The remaining liquid assets will cover the ₹80,000 monthly burn without forcing an early sale."}
        ]
    """).strip()

    user_prompt = textwrap.dedent(f"""
        Capital decision: "{decision_input.description}"

        Current portfolio:
        - Total value: ₹{decision_input.portfolio.total_value_inr:,}
        - Monthly expenses: ₹{decision_input.portfolio.monthly_expenses_inr:,}
        - Liquid assets: {decision_input.portfolio.liquid_assets_pct}% of portfolio
        - Asset mix: {asset_summary}
        - Investment horizon: {decision_input.horizon_months} months
        - Dependents relying on this portfolio: {decision_input.dependents}

        What are the 3 assumptions this decision depends on? Return them in the specified JSON format.
    """).strip()

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction=system_prompt
    )
    response = generate_with_retry(model, user_prompt)

    raw = response.text.strip()
    cleaned = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    
    data = json.loads(cleaned)
    return [ExtractedAssumption(category=item["category"], text=item["text"]) for item in data]


def generate_critical_question(decision_input: DecisionInput, assumptions: list[Assumption]) -> str:
    """
    Gemini's second job: given the assumptions and their fragility scores,
    produce the single most important question the principal must answer.
    """
    assumption_summary = "\n".join(
        f"  - [{a.fragility_label}] {a.text} → ₹{a.rupee_impact:,.0f} at risk"
        for a in assumptions
    )

    prompt = textwrap.dedent(f"""
        A principal is considering this decision: "{decision_input.description}"

        The hidden assumptions and their risk:
        {assumption_summary}

        They have {decision_input.dependents} dependents and a {decision_input.horizon_months}-month horizon.

        Write ONE question — the single most important thing they must be able to answer
        honestly before acting. Make it specific to their numbers. Make it the kind of
        question a CIO would ask before signing off.

        Return only the question. No preamble.
    """).strip()

    model = genai.GenerativeModel("gemini-2.5-flash-lite")
    response = generate_with_retry(model, prompt)

    return response.text.strip()


# ── Report assembly ───────────────────────────────────────────────────────────

def build_report(decision_input: DecisionInput) -> PreMortemReport:
    """
    Full pipeline:
      1. Extract assumptions via Gemini (language only)
      2. Stress-test each assumption with deterministic math
      3. Assemble the report
    """
    # Step 1: Gemini extracts assumption texts
    extracted_assumptions = extract_assumptions(decision_input)

    # Step 2: For each assumption, run deterministic math
    assumptions: list[Assumption] = []
    for ext in extracted_assumptions:
        score, label, break_even = compute_fragility_score(ext, decision_input)
        rupee_impact, formula = compute_rupee_impact(ext, decision_input)

        assumptions.append(Assumption(
            text              = ext.text,
            fragility_score   = score,
            fragility_label   = label,
            break_even_value  = break_even,
            rupee_impact      = rupee_impact,
            traceable_formula = formula,
        ))

    # Step 3: Portfolio-level math
    current_value       = decision_input.portfolio.total_value_inr
    monthly_expenses    = decision_input.portfolio.monthly_expenses_inr
    post_crash_value    = compute_post_crash_value(decision_input.portfolio, crash_severity=1.0)
    worst_case_loss     = current_value - post_crash_value
    current_runway      = compute_runway(current_value,    monthly_expenses)
    worst_case_runway   = compute_runway(post_crash_value, monthly_expenses)
    liquid_capital      = compute_liquid_capital(decision_input.portfolio)
    forced_seller_risk  = liquid_capital < (monthly_expenses * decision_input.horizon_months)

    # Step 4: Gemini generates the critical question
    critical_question = generate_critical_question(decision_input, assumptions)

    # Step 5: Verdict — deterministic rule, not LLM
    fragile_count = sum(1 for a in assumptions if a.fragility_label == "FRAGILE")
    if worst_case_runway < 12 or fragile_count >= 2:
        verdict = "PAUSE"
    elif worst_case_runway < 24 or fragile_count == 1 or forced_seller_risk:
        verdict = "PROCEED WITH CAUTION"
    else:
        verdict = "PROCEED"

    return PreMortemReport(
        decision                = decision_input.description,
        assumptions             = assumptions,
        worst_case_loss_inr     = worst_case_loss,
        current_runway          = current_runway,
        worst_case_runway       = worst_case_runway,
        forced_seller_risk      = forced_seller_risk,
        critical_question       = critical_question,
        verdict                 = verdict,
        current_runway_trace    = f"(₹{current_value:,.0f} / ₹{monthly_expenses:,.0f} burn)",
        worst_case_runway_trace = f"(₹{post_crash_value:,.0f} / ₹{monthly_expenses:,.0f} burn)",
    )


# ── CLI renderer ──────────────────────────────────────────────────────────────

FRAGILITY_ICON = {"SOLID": "✓", "UNCERTAIN": "~", "FRAGILE": "✗"}
VERDICT_ICON   = {"PROCEED": "✅", "PROCEED WITH CAUTION": "⚠️ ", "PAUSE": "🛑"}

def render_report(report: PreMortemReport) -> None:
    """Render the pre-mortem report to the terminal — clean, no clutter."""
    W = 70  # line width

    print(f"\n{'═' * W}")
    print(f"  PRE-MORTEM REPORT  ·  timecell.ai")
    print(f"  Analysis run: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}")
    print(f"{'═' * W}")
    print(f"\n  Decision: {report.decision}\n")

    # ── Assumptions ───────────────────────────────────────────────────────────
    print(f"  {'─' * (W - 2)}")
    print(f"  HIDDEN ASSUMPTIONS")
    print(f"  {'─' * (W - 2)}")

    for i, assumption in enumerate(report.assumptions, 1):
        icon  = FRAGILITY_ICON[assumption.fragility_label]
        score = assumption.fragility_score
        label = assumption.fragility_label

        print(f"\n  {i}. [{icon} {label} · {score}/100]")

        # Word-wrap assumption text
        wrapped = textwrap.wrap(assumption.text, width=W - 6)
        for line in wrapped:
            print(f"     {line}")

        print(f"\n     At risk:    ₹{assumption.rupee_impact:>12,.0f}")
        print(f"     Formula:    {assumption.traceable_formula}")

        # Word-wrap break-even
        be_lines = textwrap.wrap(f"Break-even: {assumption.break_even_value}", width=W - 6)
        for line in be_lines:
            print(f"     {line}")

    # ── Portfolio math ────────────────────────────────────────────────────────
    print(f"\n  {'─' * (W - 2)}")
    print(f"  PORTFOLIO MATH")
    print(f"  {'─' * (W - 2)}")
    
    # Traceability — strings already computed in build_report
    print(f"  Current runway      : {report.current_runway:.1f} months {report.current_runway_trace}")
    print(f"  Worst-case runway   : {report.worst_case_runway:.1f} months {report.worst_case_runway_trace}")
    print(f"  Worst-case loss     : ₹{report.worst_case_loss_inr:>12,.0f}")
    print(f"  Forced seller risk  : {'YES — liquidity may force a sale at worst time' if report.forced_seller_risk else 'No'}")

    # ── Critical question ─────────────────────────────────────────────────────
    print(f"\n  {'─' * (W - 2)}")
    print(f"  THE QUESTION YOU MUST ANSWER FIRST")
    print(f"  {'─' * (W - 2)}")
    wrapped_q = textwrap.wrap(report.critical_question, width=W - 4)
    for line in wrapped_q:
        print(f"  {line}")

    # ── Verdict ───────────────────────────────────────────────────────────────
    icon = VERDICT_ICON[report.verdict]
    print(f"\n  {'═' * (W - 2)}")
    print(f"  VERDICT  {icon}  {report.verdict}")
    print(f"  {'═' * (W - 2)}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        print("[error] GEMINI_API_KEY environment variable not set.")
        print("        Add GEMINI_API_KEY=your-key-here to your .env file")
        return

    # ── Example decision ──────────────────────────────────────────────────────
    decision_input = DecisionInput(
        description     = "I want to move 20% of my portfolio from NIFTY50 into BTC",
        horizon_months  = 18,
        dependents      = 3,
        reallocated_pct = 20.0,
        source_asset    = "NIFTY50",
        target_asset    = "BTC",
        portfolio = Portfolio(
            total_value_inr      = 10_000_000,
            monthly_expenses_inr =     80_000,
            liquid_assets_pct    =         35,   # 35% accessible within 30 days
            assets = [
                {"name": "BTC",     "allocation_pct": 30, "expected_crash_pct": -80},
                {"name": "NIFTY50", "allocation_pct": 40, "expected_crash_pct": -40},
                {"name": "GOLD",    "allocation_pct": 20, "expected_crash_pct": -15},
                {"name": "CASH",    "allocation_pct": 10, "expected_crash_pct":   0},
            ],
        ),
    )

    print("\nRunning pre-mortem analysis...")
    report = build_report(decision_input)
    render_report(report)

    # ── Interactive Sensitivity Mode ──────────────────────────────────────────
    while True:
        print("\n" + "─" * 70)
        run_sens = input("Run sensitivity on BTC crash assumption? (y/n): ").strip().lower()
        if run_sens != 'y':
            break
            
        try:
            new_crash = float(input("Enter new BTC expected crash percentage (e.g., -90 for a 90% crash): ").strip())

            # Work on a copy — never mutate the original input between sensitivity runs
            sens_input = copy.deepcopy(decision_input)
            for asset in sens_input.portfolio.assets:
                if asset["name"] == "BTC":
                    asset["expected_crash_pct"] = new_crash

            print(f"\nRecalculating with BTC expected crash at {new_crash}%...")
            report_sens = build_report(sens_input)
            render_report(report_sens)
            
        except ValueError:
            print("Invalid input. Please enter a number like -90.")

if __name__ == "__main__":
    main()