"""
Task 03 — AI-Powered Portfolio Explainer

Uses Google Gemini (gemini-2.5-flash) to generate a plain-English
risk explanation for any portfolio — written in the tone of a friendly but
honest financial advisor.

Usage:
    load you gemini api key in the .env file as GEMINI_API_KEY="your-key-here"
    python task_3.py

"""

import os
import json
import textwrap
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

TONE_INSTRUCTIONS = {
    "beginner": (
        "You are explaining this to someone who has never invested before. "
        "Avoid all jargon. If you must use a financial term, explain it in plain words immediately after. "
        "Be warm, encouraging, and never condescending."
    ),
    "experienced": (
        "You are explaining this to someone who understands basic investing — "
        "they know what stocks, crypto, and diversification mean. "
        "Be direct and specific. Skip the basics."
    ),
    "expert": (
        "You are explaining this to a seasoned investor or wealth manager. "
        "Use precise financial language: drawdown, Sharpe ratio, concentration risk, liquidity runway. "
        "Be analytical and concise. No hand-holding."
    ),
}



def build_prompt(portfolio: dict, tone: str = "experienced") -> str:
    """
    Build the system + user prompt for portfolio risk explanation.

    """
    tone_instruction = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["experienced"])

    total_value = portfolio["total_value_inr"]
    assets      = portfolio["assets"]

    asset_lines = "\n".join(
        f"  - {a['name']}: {a['allocation_pct']}% allocation, "
        f"expected crash: {a['expected_crash_pct']}%"
        for a in assets
    )

    crash_details = []
    post_crash_value = total_value
    for a in assets:
        loss = total_value * (a["allocation_pct"] / 100) * (a["expected_crash_pct"] / 100)
        post_crash_value += loss
        if loss != 0:
            crash_details.append(f"  - {a['name']} loses ₹{abs(loss):,.0f}")

    monthly_expenses = portfolio["monthly_expenses_inr"]
    runway_months    = post_crash_value / monthly_expenses if monthly_expenses > 0 else float("inf")

    crash_summary = "\n".join(crash_details)

    system_prompt = textwrap.dedent(f"""
        You are a financial advisor reviewing an Indian investor's portfolio.
        {tone_instruction}

        Always respond in the following exact JSON structure — nothing before or after it:
        {{
            "summary": "<3-4 sentences on overall risk level>",
            "doing_well": "<one specific thing the investor is doing right>",
            "consider_changing": "<one specific thing to reconsider, with a clear reason why>",
            "verdict": "<exactly one of: Aggressive | Balanced | Conservative>"
        }}

        Rules:
        - Be specific. Reference actual asset names and numbers from the portfolio.
        -You MUST mention the 'Months of expenses covered post-crash' to help the investor understand their actual survival runway
        - Never be vague. 'Consider rebalancing' alone is not acceptable — say what to rebalance and why.
        - The verdict must be exactly one word: Aggressive, Balanced, or Conservative.
        - Do not include any text outside the JSON object.
    """).strip()

    user_prompt = textwrap.dedent(f"""
        Please analyse this portfolio:

        Total value: ₹{total_value:,}
        Monthly expenses: ₹{monthly_expenses:,}

        Asset allocation:
        {asset_lines}

        Pre-computed crash scenario (worst case):
        {crash_summary}
        Post-crash portfolio value: ₹{post_crash_value:,.0f}
        Months of expenses covered post-crash: {runway_months:.1f} months

        Provide your analysis in the required JSON format.
    """).strip()

    return system_prompt, user_prompt



def call_gemini(system_prompt: str, user_prompt: str) -> str:
    """
    Send prompts to Gemini and return the raw text response.
    """
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt
    )
    
    response = model.generate_content(user_prompt)
    return response.text



def parse_output(raw_response: str) -> dict | None:
    """
    Parse the structured JSON from Gemini's response.
    """
    try:
        cleaned = raw_response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed  = json.loads(cleaned)

        required_keys = {"summary", "doing_well", "consider_changing", "verdict"}
        if not required_keys.issubset(parsed.keys()):
            raise ValueError(f"Missing keys: {required_keys - parsed.keys()}")

        valid_verdicts = {"Aggressive", "Balanced", "Conservative"}
        if parsed["verdict"] not in valid_verdicts:
            raise ValueError(f"Invalid verdict '{parsed['verdict']}' — must be one of {valid_verdicts}")

        return parsed

    except (json.JSONDecodeError, ValueError) as e:
        print(f"[parse error] Could not parse Gemini's response: {e}")
        return None



def call_critic(original_explanation: dict, portfolio: dict) -> str:
    """
    Second LLM call: asks Gemini to critique the first explanation for accuracy.
    """
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

    critic_prompt = textwrap.dedent(f"""
        A financial AI assistant produced the following portfolio analysis:

        {json.dumps(original_explanation, indent=2)}

        The actual portfolio data was:
        {json.dumps(portfolio, indent=2)}

        Your job: critique this analysis for accuracy and usefulness.
        - Are the claims grounded in the actual numbers?
        - Is the 'consider_changing' advice specific and actionable?
        - Is the verdict (Aggressive/Balanced/Conservative) justified?
        - What, if anything, is missing or misleading?

        Be brief and direct. 3-5 sentences maximum.
    """).strip()

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(critic_prompt)

    return response.text



def print_section(title: str, content: str) -> None:
    width = 55
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")
    for line in content.splitlines():
        print(textwrap.fill(line, width=width, initial_indent="  ", subsequent_indent="  ") if line.strip() else "")


def print_structured_output(parsed: dict) -> None:
    width = 55
    print(f"\n{'═' * width}")
    print("  STRUCTURED OUTPUT")
    print(f"{'═' * width}")
    print(f"\n  Summary:\n")
    for line in textwrap.wrap(parsed["summary"], width=width - 4):
        print(f"    {line}")
    print(f"\n  ✓ Doing well:\n    {parsed['doing_well']}")
    print(f"\n  ⚠ Consider changing:\n    {parsed['consider_changing']}")
    print(f"\n  Verdict: [ {parsed['verdict'].upper()} ]")
    print(f"\n{'═' * width}")



def explain_portfolio(portfolio: dict, tone: str = "experienced", run_critic: bool = True) -> None:
    """
    Full pipeline: build prompt → call Gemini → parse output → optionally critique.
    Accepts any portfolio dict — not hardcoded to the example.
    """

    print(f"\nAnalysing portfolio  |  tone: {tone}  |  critic: {run_critic}")

    # Step 1: build prompts
    system_prompt, user_prompt = build_prompt(portfolio, tone)

    # Step 2: call Gemini
    print("\nCalling Gemini API...")
    raw_response = call_gemini(system_prompt, user_prompt)

    # Step 3: print raw API response
    print_section("RAW API RESPONSE", raw_response)

    # Step 4: parse structured output
    parsed = parse_output(raw_response)
    if parsed is None:
        print("\n[error] Could not extract structured output. Raw response printed above.")
        return

    # Step 5: print structured output
    print_structured_output(parsed)

    # Step 6: critic call (bonus)
    if run_critic:
        print("\nRunning critic pass...")
        critique = call_critic(parsed, portfolio)
        print_section("CRITIC REVIEW", critique)


EXAMPLE_PORTFOLIO = {
    "total_value_inr":      10_000_000,
    "monthly_expenses_inr":     80_000,
    "assets": [
        {"name": "BTC",     "allocation_pct": 30, "expected_crash_pct": -80},
        {"name": "NIFTY50", "allocation_pct": 40, "expected_crash_pct": -40},
        {"name": "GOLD",    "allocation_pct": 20, "expected_crash_pct": -15},
        {"name": "CASH",    "allocation_pct": 10, "expected_crash_pct":   0},
    ],
}


def collect_portfolio_from_user() -> dict:
    """Interactively collect portfolio details from the terminal."""
    print("\n--- Custom Portfolio Input ---\n")

    total_value      = float(input("  Total portfolio value (INR): "))
    monthly_expenses = float(input("  Monthly expenses (INR):      "))

    assets = []
    print("\n  Add assets one by one. Type 'done' when finished.\n")

    while True:
        name = input("  Asset name (or 'done'): ").strip()
        if name.lower() == "done":
            break

        allocation   = float(input(f"    {name} — allocation %:       "))
        crash_pct    = float(input(f"    {name} — expected crash %:   "))

        assets.append({
            "name": name,
            "allocation_pct": allocation,
            "expected_crash_pct": crash_pct,
        })
        print()

    return {
        "total_value_inr": total_value,
        "monthly_expenses_inr": monthly_expenses,
        "assets": assets,
    }


def select_tone() -> str:
    """Let the user pick an explanation tone."""
    print("\n  Tone options:")
    print("    1. Beginner   — no jargon, warm and simple")
    print("    2. Experienced — direct, skips the basics")
    print("    3. Expert     — precise financial language")

    choice = input("\n  Select tone [1/2/3] (default: 1): ").strip()
    return {"1": "beginner", "2": "experienced", "3": "expert"}.get(choice, "beginner")


def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        print("[error] GEMINI_API_KEY environment variable not set.")
        return

    print("\n=== AI-Powered Portfolio Explainer ===")
    print("\n  1. Use example portfolio (1 Crore INR, 4 assets)")
    print("  2. Enter your own portfolio")

    choice = input("\n  Select [1/2] (default: 1): ").strip()

    if choice == "2":
        portfolio = collect_portfolio_from_user()
    else:
        portfolio = EXAMPLE_PORTFOLIO

    tone = select_tone()

    explain_portfolio(portfolio, tone=tone, run_critic=True)


if __name__ == "__main__":
    main()