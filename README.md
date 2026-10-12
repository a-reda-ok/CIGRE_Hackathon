# CIGRE GridFlex

Prototype developed for the **CIGRE NGN 2026 hackathon** (CNF-CIGRE, 8–9
October). The project studies the French electricity system and spot market on
**6 April 2025**, a day when abundant low-carbon generation, low Sunday
demand, and limited flexibility coincided with strongly negative spot prices.

The repository combines a short diagnosis of that day with a prototype
flexibility solution for an industrial process-heat site. The proposed lever is
a hybrid gas/electric boiler, optionally coupled to thermal storage. The model
uses the observed spot-price signal to decide when electricity should replace
gas while respecting boiler, storage, and heat-demand constraints.

> **Important:** 6 April 2025 was a Sunday, not a Friday. The weekend demand
> profile is relevant when interpreting the results.

## Hackathon context

The challenge is not simply to identify negative prices. The electricity system
must remain balanced at all times, but the provided dataset contains only a
subset of the quantities needed to reconstruct the physical balance. The
hackathon therefore asks teams to:

1. **Diagnose the situation** using the price, consumption, and generation
   data.
2. **Design and quantify a flexibility solution** with a reproducible
   prototype.
3. **Explain the trade-offs**, including assumptions, technical limits, and
   who bears any hidden cost.

This repository focuses on Challenge A: using negative and low-price periods
to reduce the cost of industrial heat while testing whether the solution
remains valuable under less favourable price conditions.

## What is in this repository?

```text
.
├── COPILOT_CONTEXT.md
├── Optimization model full formulation.md
├── donnees_6_avril_2025.xlsx - 6 avril 2025.csv
├── figures/
│   ├── 01_price_and_power.png
│   ├── 02_generation_composition.png
│   ├── 03_price_vs_partial_balance.png
│   ├── 04_hourly_ramps.png
│   └── boiler_*.{png,csv}
└── src/
    ├── Industrial_heat_model.py
    └── plot_data.py
```

### Main files

- **`donnees_6_avril_2025.xlsx - 6 avril 2025.csv`** — provided French
  electricity data. It contains hourly price, solar, wind, consumption, and
  nuclear values. The first two rows are metadata.
- **`src/plot_data.py`** — loads and normalizes the data, then recreates the
  four diagnostic figures in `figures/`.
- **`src/Industrial_heat_model.py`** — solves the industrial heat dispatch
  problem as a linear program using `scipy.optimize.linprog`. It compares an
  electric boiler without storage with the same boiler combined with thermal
  storage, and reports costs, savings, emissions, stress tests, and sizing
  results.
- **`Optimization model full formulation.md`** — equations, variable
  definitions, cost coefficients, KPIs, and simplifications used by the model.
- **`COPILOT_CONTEXT.md`** — the detailed hackathon brief, data limitations,
  analysis rules, and submission checklist.

## Data and interpretation

The CSV has one hourly row for each hour from 00:00 to 23:00. Its columns are:

| Column | Unit | Meaning |
| --- | --- | --- |
| `Heure` | local time | Time in Europe/Paris |
| `Prix (€/MWh)` | EUR/MWh | Spot price |
| `Solaire (MW)` | MW | Solar generation |
| `Éolien (MW)` | MW | Wind generation |
| `Consommation (MW)` | MW | Electricity consumption |
| `Nucléaire (MW)` | MW | Nuclear generation |

The scripts calculate:

```text
partial balance = nuclear + wind + solar - consumption
```

This is an **observed partial balance**, not the physical imbalance of the
French grid. The dataset omits, among other things, hydro and thermal
generation, storage, curtailment, and cross-border exchanges. Results must not
be presented as proof of a physical grid surplus or deficit.

All model parameters other than the spot price are assumptions. They include
heat demand, boiler efficiencies and capacities, gas price, carbon price,
network adders, storage losses, investment costs, and grid emissions. They are
declared in `Params` and should be sourced or labelled as uncertain before
being used as factual claims.

## Getting started

### Requirements

- Python 3.10 or newer
- `pandas`
- `numpy`
- `scipy`
- `matplotlib` (needed for plots; the optimization can otherwise still run)

Create and activate a virtual environment, then install the dependencies:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
python -m pip install pandas numpy scipy matplotlib
```

### Recreate the diagnostic figures

Run from the repository root:

```bash
python src/plot_data.py
```

The script writes the four diagnostic PNG files to `figures/` and prints the
number of rows and negative-price hours. Existing files with the same names
are replaced.

### Run the industrial heat model

Run the default parameter set:

```bash
python src/Industrial_heat_model.py "donnees_6_avril_2025.xlsx - 6 avril 2025.csv"
```

Run the hackathon steel-plant preset:

```bash
python src/Industrial_heat_model.py "donnees_6_avril_2025.xlsx - 6 avril 2025.csv" --preset steel
```

The steel preset uses a 50 MWth heat demand, a 50 MWe electric boiler, a
10 MWth minimum gas output, and the parameters documented in
`Optimization model full formulation.md`. The command produces:

- console summaries for the no-storage and storage scenarios;
- stress tests and a gas-price/adders sensitivity table;
- dispatch CSV files alongside the output figure;
- dispatch figures in `figures/` by default.

Useful variations include:

```bash
# Add a carbon price and use an 8% discount rate.
python src/Industrial_heat_model.py "donnees_6_avril_2025.xlsx - 6 avril 2025.csv" `
  --preset steel --co2-price 80 --discount 0.08

# Run the boiler-size and storage-size sweep.
python src/Industrial_heat_model.py "donnees_6_avril_2025.xlsx - 6 avril 2025.csv" `
  --preset steel --sweep
```

On Windows PowerShell, the backtick joins a command across lines; the command
can also be entered on one line. Use `--help` to see all available options,
including custom demand, boiler size, storage, price-column, and time-column
settings.

## Model overview

For each time step, the linear program chooses:

- heat supplied directly by the electric boiler;
- heat supplied by the gas boiler;
- electric or gas heat sent to storage;
- heat discharged from storage;
- the storage state of charge.

The objective minimizes the daily heat-supply cost:

```text
electricity cost + gas cost + carbon cost
```

The model enforces heat balance, boiler limits, minimum gas output, storage
capacity and losses, charge/discharge limits, and a daily cycle condition. It
then compares the optimized dispatch with a gas-only baseline. Reported gains
are therefore scenario results for one day, not a forecast of annual savings.

The formulation currently simplifies several operational details: hourly
steps, perfect day-ahead price knowledge, no boiler ramp limits, and no
explicit market or network constraints. These limitations should be stated in
any presentation of the results.

## Reproducibility and responsible use

Before presenting a number, identify whether it comes from:

1. the provided CSV;
2. a cited public source; or
3. an explicit model assumption.

In particular:

- Always compare flexibility with a clearly defined do-nothing baseline.
- Keep units explicit: MW is power, MWh is energy, MWth is thermal power, and
  MWhth is thermal energy.
- Do not interpret negative spot prices as a direct measurement of physical
  imbalance.
- Report the main loser or hidden cost of the proposed flexibility.
- Treat one-day economics and “days to cover” as illustrative scenario
  indicators, not investment advice.

## Further documentation

See [COPILOT_CONTEXT.md](COPILOT_CONTEXT.md) for the complete hackathon brief,
diagnostic requirements, data caveats, and final-pitch checklist. See
[Optimization model full formulation.md](Optimization%20model%20full%20formulation.md)
for the mathematical formulation and KPI definitions.
