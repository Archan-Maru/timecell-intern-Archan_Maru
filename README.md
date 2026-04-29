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
