# Hackathon CIGRE NGN 2026 - Project Context for Copilot

> Purpose of this file: give an AI coding assistant (GitHub Copilot, etc.) the full context of the hackathon so its suggestions are relevant, correct and aligned with the brief. Treat this as the source of truth for project goals and constraints.

## 1. Project in one paragraph

We are a team in a two-day hackathon (CNF-CIGRE, 8-9 October) on the **French electricity system and spot market on 6 April 2025**, a day with **negative spot prices** (abundant supply vs. low demand and limited export/flexibility). We must (1) diagnose what happened from the provided CSV, then (2) design, prototype and quantify an original solution around flexibility. Evaluation: **~30% understanding of the real situation, ~70% relevance, boldness and implementation of the solution.**

## 2. Data

- Official data source: `donnees_6_avril_2025.csv` (provided separately, shared by all teams). Put it in `data/` (adjust the path in code if different).
- Expected content (verify by inspecting the file, do not assume column names): spot price, nuclear, wind and solar production, consumption, at hourly resolution or finer.
- **Important limitation:** the dataset does NOT contain the full electricity balance (no hydro, thermal, storage, cross-border exchanges). A sum such as `nuclear + wind + solar - consumption` is a **partial balance of the dataset**, NOT the true physical imbalance of the grid. Code, plots and comments must never present it as the real imbalance.
- Note: the brief says "Friday 6 April 2025", but 6 April 2025 was a **Sunday**. Mention this when relevant (low weekend demand).
- Time handling: check time zone (Europe/Paris, DST change occurs at the end of March, so 6 April is CEST, UTC+2), time step (15 min vs hourly), missing values and units (MW vs MWh, EUR/MWh).

## 3. Domain concepts

- Supply and demand must balance at every instant; grid frequency (50 Hz) is the physical indicator. RTE balances the whole system close to real time; balance responsible parties balance their own perimeters.
- **Flexibility** = ability to change an injection or withdrawal (production, consumption or exchange).
- Flexibility levers: reserves/balancing means, nuclear and hydro modulation, solar/wind curtailment, demand response (shedding, shifting, piloted increase), storage (batteries/BESS, pumped hydro/STEP), interconnections.
- **Negative spot prices** are a market signal of oversupply relative to demand, export capacity and flexibility. They are NOT a direct measure of physical imbalance. Support mechanisms, contracts, technical constraints and market rules can change incentives.
- Reserve layers (for context): FCR (primary), aFRR (secondary), mFRR (tertiary).

## 4. Stage 1 - The foundation (diagnosis, ~30%)

Every result must be a number, a chart or a falsifiable conclusion that the jury can challenge.

**Proof 1 - Read the market signal**
- Plot spot price over the day; identify and quantify remarkable periods (hours with negative price, minimum price, duration, cumulated negative-price hours).
- Compute the hourly **partial balance** = nuclear + wind + solar - consumption. Report cumulated energy (MWh) over periods where it is positive and the most critical hour.
- Cross price and partial balance; find at least one moment where they disagree and propose explanations (market coupling, missing components, bidding behaviour, ramps...).
- List the missing balance components and assumptions preventing a physical-imbalance interpretation.

**Proof 2 - Physical constraints**
- For nuclear, solar and wind: what limits increasing/decreasing output (nuclear: minimum stable power, ramp rates, fuel/operating constraints; solar/wind: weather, controllability, curtailment mechanisms).
- Compute observed ramp rates (MW/h) from the series and discuss what they do and do not prove.
- Identify 2-3 flexibilities absent from the CSV (STEP, interconnections, batteries, demand flexibility) with sourced or clearly argued orders of magnitude.

**Proof 3 - Visible actions and blind spots**
- Analyse nuclear and other trajectories for notable modulation or reaction; quantify it.
- State what the data can attribute to a control action and what it cannot prove.
- Give 2-3 ranked hypotheses on flexibilities or exchanges that may have acted, each with the extra data needed to confirm.

**Required synthesis:** one sentence stating the main problem revealed by 6 April 2025 (it opens the final pitch).

## 5. Stage 2 - The challenge (~70%)

The team picks ONE challenge (or a clearly motivated variant). Depth beats breadth.

- **Challenge A - Define your own "best":** better management of negative-price episodes with a self-chosen objective. Angles: limit producer losses; value negative prices for consumers; optimize storage (arbitrage + system contribution); reduce system balancing costs/needs. Required: explicit objective function (what, for whom, why), prototype on 6 April, quantified gain (EUR, MWh, negative-price hours, emissions, comfort, risk), and the **loser / hidden cost**.
- **Challenge B - Build your lever stack:** activation strategy of flexibilities (which lever, how much power, in which order, when). Required: technical sheet per lever (power, response time, duration/energy, constraints, actors, economic order of magnitude) for nuclear modulation, solar/wind curtailment, STEP, BESS, demand flexibility, interconnections; explicit and reproducible merit order / decision logic; activation plan on 6 April with quantified balance (treated vs. untreated, trade-offs). Bonus: a lever not listed in the brief.
- **Challenge C - Flip the problem:** turn surplus/negative-price hours into an opportunity (new business model, usage, actor, coordination or market). Required: prototype applied to 6 April (what new demand, when, at what power); economic logic (who invests, gains, pays; does it still work when prices are positive?); a reality test (a real technical, regulatory, economic or behavioural barrier and how to address it).

### Deliverables
1. Functional prototype (any format: script, notebook, app, spreadsheet).
2. Visualizations / dashboard telling the reasoning.
3. Quantified evaluation with a defensible indicator.

## 6. Hard rules for all code and analysis

1. **Traceability ("golden rule"):** every number must come from the provided data, a public source (cite it) or an explicit, documented assumption. If data is insufficient, say so and state what is missing.
2. **Every assumption is documented** (capacity, efficiency, cost, user behaviour) in a central place, e.g. `assumptions.md` or a `config` file, with a source or an "uncertain" tag. Do not hard-code magic numbers silently.
3. **Never present the partial balance as the true physical imbalance.**
4. **Always compare against a baseline** (no flexibility / do-nothing) when quantifying a gain.
5. **Identify the loser or hidden cost** of any proposed solution.
6. **Reproducibility:** the main results must be reproducible by running a single script or notebook from the raw CSV.
7. Do not invent data, sources, URLs or figures. If unsure, leave a `TODO: source needed` comment.
8. AI output is a draft, not a source: verify formulas and numbers. The team must be able to explain every kept number.
9. Code quality is not a grading criterion. Prefer simple, readable, working code over sophisticated code. A clear idea with a simple prototype wins.

## 7. Suggested technical stack and conventions

- Language: Python (pandas, numpy, matplotlib/plotly). Any other tool is allowed by the brief.
- Optimization (storage, load shifting, dispatch): `PuLP`, `cvxpy`, `Pyomo` or `OR-Tools`; a simple rule-based baseline first, then an LP/MILP.
- Dashboard: Plotly, Streamlit or static figures; screenshots must be saved as plan B for the demo.
- Units: be explicit in variable names and axis labels (`price_eur_mwh`, `power_mw`, `energy_mwh`). Convert MW to MWh using the real time step (`MWh = MW * dt_hours`).
- Time index: use timezone-aware `DatetimeIndex` (Europe/Paris).
- Suggested layout:

```
.
├── COPILOT_CONTEXT.md        # this file
├── README.md
├── assumptions.md            # all hypotheses with sources
├── data/
│   └── donnees_6_avril_2025.csv
├── notebooks/                # exploration
├── src/
│   ├── load_data.py          # loading, cleaning, time handling
│   ├── stage1_diagnosis.py   # price stats, partial balance, ramp rates
│   ├── model.py              # chosen challenge (A/B/C) prototype
│   └── evaluate.py           # baseline vs. solution, quantified gain
├── figures/                  # exported charts and plan-B screenshots
└── pitch/                    # slides
```

## 8. Final pitch (10 minutes) - keep outputs aligned

| Time | Segment | Question to answer |
|---|---|---|
| ~2 min | The problem | What did we really understand about 6 April? |
| ~2 min | The idea | What is the proposal and its objective function? |
| ~3 min | The demo | What does the prototype do on real data? |
| ~2 min | The numbers | What gain, under which conditions and assumptions? |
| ~1 min | The limits | What remains to be tested or improved? |

Prepare a plan B for the demo (screenshots / pre-computed results). The team must be able to answer: "Where does this number come from?", "Who pays?", "What if your main assumption is wrong?", and name at least one serious limit.

## 9. How Copilot should help

- Prioritize: data loading and cleaning, Stage 1 statistics (negative-price hours, partial balance, ramp rates), plots, then a minimal prototype for the chosen challenge and its baseline comparison.
- When generating code, add short comments stating units and assumptions, and flag any assumption that needs a source.
- Keep suggestions simple and runnable; avoid heavy frameworks and over-engineering.
- When asked about numbers (capacities, costs, efficiencies), propose ranges and mark them as assumptions to verify, never as facts.
- Write deliverable text (slides, notes) in the language the team uses (French or English); the original brief is in French.

## 10. Submission checklist

- [ ] Pitch support (slides)
- [ ] Prototype / code reproducing the main results from the raw CSV
- [ ] Additional files needed for the demo
- [ ] Dashboard / visualizations and quantified evaluation
- [ ] Plan B for the demo (screenshots, pre-computed results)
- [ ] Every figure traceable (data, source or documented assumption)
- [ ] At least one serious limitation named
