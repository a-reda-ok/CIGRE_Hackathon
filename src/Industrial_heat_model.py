#!/usr/bin/env python3
#!/usr/bin/env python3
"""Challenge A prototype - industrial site with a hybrid gas + electric boiler, 6 April 2025.

Objective (minimise): daily cost of supplying the site's process heat
    = gas + CO2 cost of the gas boiler + (spot price + non-energy adders) paid for the
      electricity of the electric boiler.
The electric boiler (optionally fed into a thermal storage) takes over from the gas boiler
whenever the spot price is low or negative. The gas boiler stays as backup and keeps a
minimum stable load (`gas_min_mw_th`) on its TOTAL output (heat to the process + heat to storage).
Storage has a charge and a discharge efficiency, so charging and discharging in the same hour
is never free, and forbidden outright (binary) so negative prices cannot be farmed through losses.

DATA vs ASSUMPTIONS
  * Only the spot price comes from the provided CSV.
  * EVERYTHING in `Params` is an assumption: source it or flag it as uncertain
    (see the assumptions register in the study document).

Usage
  python src/Industrial_heat_model.py "donnees_6_avril_2025.xlsx - 6 avril 2025.csv" --price-col <name> --time-col <name>
  # teammate's steel-plant parameters (50 MW_th, 40 EUR/MWh gas, 15 EUR/MWh fee, 10 MW gas minimum):
  python src/Industrial_heat_model.py "donnees_6_avril_2025.xlsx - 6 avril 2025.csv" --preset steel
  # add a CO2 cost on gas and a cost of capital:
  python src/Industrial_heat_model.py "donnees_6_avril_2025.xlsx - 6 avril 2025.csv" --preset steel --co2-price <EUR/t> --discount 0.08

  # boiler size x storage size sweep (finds the sizing with the shortest payback):
  python src/Industrial_heat_model.py "donnees_6_avril_2025.xlsx - 6 avril 2025.csv" --preset steel --sweep

Requires: pandas, numpy, scipy (matplotlib optional, for the figures).
"""
from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog


# --------------------------------------------------------------------------------------
# Assumptions (all to be sourced / flagged uncertain)
# --------------------------------------------------------------------------------------
@dataclass
class Params:
    demand_mw_th: float = 20.0          # ASSUMPTION: flat process-heat demand (continuous process)
    p_elec_mw: float = 20.0             # ASSUMPTION: electric boiler electrical capacity (MW_e)
    eta_e: float = 0.99                 # ASSUMPTION: electrode boiler efficiency
    eta_gas: float = 0.90               # ASSUMPTION: existing gas boiler efficiency
    gas_min_mw_th: float = 0.0          # ASSUMPTION: minimum stable gas boiler output (MW_th)
    gas_price: float = 35.0             # ASSUMPTION: EUR/MWh_gas (check PCI vs PCS, TTF/PEG April 2025)
    co2_price: float = 68.0             # ASSUMPTION: EUR/tCO2 (only if the site pays EU ETS / carbon tax)
    gas_ef: float = 0.20                # ASSUMPTION: tCO2/MWh_gas (PCI basis)
    adders: float = 10.0                # ASSUMPTION: EUR/MWh_e non-energy variable cost (TURPE energy part,
                                        #   accise, supplier margin) -> must be verified for the site
    grid_ef: float = 0.03               # ASSUMPTION: tCO2/MWh_e (midday French mix; use eCO2mix if possible)
    storage_mwh_th: float = 0.0         # ASSUMPTION: thermal storage capacity (MWh_th)
    storage_loss: float = 0.005         # ASSUMPTION: heat loss per hour
    storage_eta_in: float = 0.95        # ASSUMPTION: charge efficiency (1.0 = lossless, but then LP is degenerate)
    storage_eta_out: float = 0.95       # ASSUMPTION: discharge efficiency
    capex_eur_per_mw: float = 100_000.0     # ASSUMPTION: EUR/MW_e installed (boiler + connection + integration)
    storage_capex_eur_per_mwh: float = 15_000.0  # ASSUMPTION: EUR/MWh_th
    fixed_cost_eur_per_mw_yr: float = 25_000.0   # ASSUMPTION: O&M + grid subscribed power, EUR/MW_e/yr
    lifetime_yr: int = 15               # ASSUMPTION
    discount: float = 0.08              # ASSUMPTION (0 = straight-line amortisation)

    @property
    def gas_heat_cost(self) -> float:
        """EUR per MWh_th produced by the gas boiler (gas + CO2)."""
        return (self.gas_price + self.co2_price * self.gas_ef) / self.eta_gas

    @property
    def breakeven_price(self) -> float:
        """Spot price (EUR/MWh_e) below which electric heat is cheaper than gas heat."""
        return self.gas_heat_cost * self.eta_e - self.adders


# Parameters of the teammate's model (Steel_Plant_Dual_Thermal_System_Optimization_Model.docx).
# No CO2 cost, no fixed costs, straight-line capex: same simplifications as the original.
STEEL_PRESET = dict(
    demand_mw_th=50.0, p_elec_mw=50.0, eta_e=0.98, eta_gas=0.90, gas_min_mw_th=10.0,
    gas_price=40.0, co2_price=0.0, adders=15.0, capex_eur_per_mw=100_000.0,
    fixed_cost_eur_per_mw_yr=0.0, lifetime_yr=15, discount=0.0,
)


# --------------------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------------------
def _find_col(columns, keys):
    for key in keys:
        for col in columns:
            if key in str(col).lower():
                return col
    return None


def load_prices(path, price_col=None, time_col=None, sep=",", decimal=",", skiprows=2,
                study_date="2025-04-06"):
    """Return (price Series in EUR/MWh, dt in hours)."""
    df = pd.read_csv(
        path,
        sep=sep,
        decimal=decimal,
        skiprows=skiprows,
        encoding="utf-8-sig",
        engine="python",
    )
    price_col = price_col or _find_col(df.columns, ("prix", "price", "spot"))
    if price_col is None or price_col not in df.columns:
        raise SystemExit(f"Price column not found. Columns: {list(df.columns)}. Use --price-col.")
    time_col = time_col or _find_col(df.columns, ("date", "heure", "time", "hour", "timestamp"))

    price = pd.to_numeric(df[price_col], errors="coerce")
    dt, index = 1.0, pd.RangeIndex(len(df))
    if time_col is not None and time_col in df.columns:
        if pd.api.types.is_numeric_dtype(df[time_col]):
            index = pd.Index(df[time_col])  # e.g. hour numbers; assume hourly
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")   # pandas "could not infer format" notice
                ts = pd.to_datetime(df[time_col], errors="coerce")
            if ts.notna().all() and ts.dt.normalize().nunique() == 1 \
                    and ts.dt.normalize().iloc[0] == pd.Timestamp.today().normalize():
                # A time-of-day-only column ("00:00") is parsed by pandas with TODAY's date:
                # anchor it on the study day so axes and exports show 6 April 2025.
                ts = pd.Timestamp(study_date) + (ts - ts.dt.normalize())
                print(f"[info] time column has no date: anchored on {study_date}")
            if ts.notna().all() and len(ts) > 1:
                step = float(ts.diff().dropna().median().total_seconds() / 3600)
                if 0.05 <= step <= 2:
                    dt, index = step, pd.Index(ts)
                else:
                    print(f"[warn] odd time step ({step} h) -> assuming hourly")
    s = pd.Series(price.to_numpy(), index=index).dropna()
    return s, dt


# --------------------------------------------------------------------------------------
# Optimisation (LP)
# --------------------------------------------------------------------------------------
def optimise(price: np.ndarray, dt: float, p: Params) -> pd.DataFrame:
    """Minimise heat-supply cost. Variables per step (MW_th unless stated):
      q_e, q_g       heat sent directly to the process by the electric / gas boiler
      e_store, g_store  heat sent to the storage by the electric / gas boiler
      s_out          heat delivered to the process by the storage
      soc            stored heat (MWh_th), T+1 values
    Process balance: q_e + q_g + s_out = D.
    Storage: soc[t+1] = keep*soc[t] + dt*(eta_in*(e_store+g_store) - s_out/eta_out).
    Charging and discharging in the same step is forbidden (binary u_t -> small MILP). Without it, with
    efficiency < 1 and negative prices the LP is paid to burn electricity by cycling heat through the
    storage's losses, which overstates the gain.
    """
    T = len(price)
    D = p.demand_mw_th
    qe, qg, es, gs, so = (slice(k * T, (k + 1) * T) for k in range(5))
    soc0 = 5 * T
    u0 = 6 * T + 1                    # binary per step: 1 = storage may charge, 0 = may discharge
    n = 7 * T + 1

    c = np.zeros(n)
    c[qe] = dt * (price + p.adders) / p.eta_e
    c[es] = dt * (price + p.adders) / p.eta_e
    c[qg] = dt * p.gas_heat_cost
    c[gs] = dt * p.gas_heat_cost

    A, b = [], []
    for t in range(T):  # process heat balance: q_e + q_g + s_out = D
        row = np.zeros(n)
        row[t] = 1
        row[T + t] = 1
        row[4 * T + t] = 1
        A.append(row)
        b.append(D)
    keep = (1 - p.storage_loss) ** dt
    for t in range(T):  # storage dynamics with charge / discharge efficiencies
        row = np.zeros(n)
        row[soc0 + t + 1] = 1
        row[soc0 + t] = -keep
        row[2 * T + t] = -dt * p.storage_eta_in
        row[3 * T + t] = -dt * p.storage_eta_in
        row[4 * T + t] = dt / p.storage_eta_out
        A.append(row)
        b.append(0.0)
    row = np.zeros(n)  # cyclic: end-of-day state of charge = start-of-day
    row[soc0 + T], row[soc0] = 1, -1
    A.append(row)
    b.append(0.0)

    cap = p.storage_mwh_th
    cap_e = p.eta_e * p.p_elec_mw
    A_ub, b_ub = [], []
    for t in range(T):  # gas minimum stable load on TOTAL gas output (process + storage)
        row = np.zeros(n)
        row[T + t] = -1
        row[3 * T + t] = -1
        A_ub.append(row)
        b_ub.append(-p.gas_min_mw_th)
    for t in range(T):  # no charging and discharging in the same step (binary u_t)
        row = np.zeros(n)
        row[2 * T + t] = 1
        row[3 * T + t] = 1
        row[u0 + t] = -cap_e if cap > 0 else 0.0
        A_ub.append(row)
        b_ub.append(0.0)
        row = np.zeros(n)
        row[4 * T + t] = 1
        row[u0 + t] = D
        A_ub.append(row)
        b_ub.append(D)
    if cap > 0:
        for t in range(T):
            row = np.zeros(n)  # electric boiler capacity shared by process + storage charging
            row[t] = 1
            row[2 * T + t] = 1
            A_ub.append(row)
            b_ub.append(cap_e)
            row = np.zeros(n)  # total charge rate limited by the electric boiler size (as before)
            row[2 * T + t] = 1
            row[3 * T + t] = 1
            A_ub.append(row)
            b_ub.append(cap_e)
    bounds = (
        [(0, cap_e)] * T                          # q_e
        + [(0, None)] * T                         # q_g (minimum load enforced on q_g + g_store above)
        + [(0, cap_e if cap > 0 else 0)] * T      # e_store
        + [(0, None if cap > 0 else 0)] * T       # g_store
        + [(0, D if cap > 0 else 0)] * T          # s_out
        + [(0, cap)] * (T + 1)                    # soc
        + [(0, 1)] * T                            # u (binary)
    )
    integrality = np.zeros(n)
    integrality[u0:] = 1
    res = linprog(
        c, A_ub=np.array(A_ub), b_ub=np.array(b_ub),
        A_eq=np.array(A), b_eq=np.array(b), bounds=bounds, method="highs",
        integrality=integrality,
    )
    if not res.success:
        raise RuntimeError(f"LP failed: {res.message}")
    x = res.x
    return pd.DataFrame(
        {
            "price": price,
            "q_e_th": x[qe],
            "q_g_th": x[qg],
            "e_store_th": x[es],
            "g_store_th": x[gs],
            "s_out": x[so],
            "net_store_th": x[es] + x[gs] - x[so],   # charge minus discharge (MW_th, boiler side)
            "soc": x[soc0:soc0 + T],
            "p_elec_mw": (x[qe] + x[es]) / p.eta_e,
        }
    )


# --------------------------------------------------------------------------------------
# KPIs
# --------------------------------------------------------------------------------------
def summarise(res: pd.DataFrame, dt: float, p: Params) -> dict:
    price = res["price"].to_numpy()
    T = len(res)
    elec_mwh = res["p_elec_mw"].to_numpy() * dt
    gas_heat_mwh = (res["q_g_th"] + res["g_store_th"]).to_numpy() * dt
    heat_mwh = p.demand_mw_th * dt * T

    baseline = heat_mwh * p.gas_heat_cost
    step_cost = (price + p.adders) * elec_mwh + gas_heat_mwh * p.gas_heat_cost
    step_gain = p.demand_mw_th * dt * p.gas_heat_cost - step_cost   # accounting split by time step
    cost = float(step_cost.sum())
    neg = price < 0
    gas_avoided = float((heat_mwh - gas_heat_mwh.sum()) / p.eta_gas)
    return {
        "baseline_cost_eur": baseline,
        "optimised_cost_eur": cost,
        "gain_eur": baseline - cost,
        "gain_in_negative_hours_eur": float(step_gain[neg].sum()),
        "gain_in_nonnegative_hours_eur": float(step_gain[~neg].sum()),
        "electricity_mwh": float(elec_mwh.sum()),
        "electricity_in_negative_hours_mwh": float(elec_mwh[neg].sum()),
        "income_from_negative_prices_eur": float(-(price[neg] * elec_mwh[neg]).sum()),
        "negative_hours": float(neg.sum() * dt),
        "negative_hours_with_boiler_on": float(((elec_mwh > 1e-6) & neg).sum() * dt),
        "hours_below_breakeven_price": float((price < p.breakeven_price).sum() * dt),
        "hours_boiler_on": float((elec_mwh > 1e-6).sum() * dt),
        "gas_avoided_mwh": gas_avoided,
        "co2_avoided_t": gas_avoided * p.gas_ef - float(elec_mwh.sum()) * p.grid_ef,
        "peak_electric_mw": float(res["p_elec_mw"].max()),
        "storage_discharged_mwh_th": float(res["s_out"].sum() * dt),
    }


def economics(gain_day: float, p: Params) -> dict:
    n, r = p.lifetime_yr, p.discount
    crf = 1 / n if r == 0 else r * (1 + r) ** n / ((1 + r) ** n - 1)
    capex = p.capex_eur_per_mw * p.p_elec_mw + p.storage_capex_eur_per_mwh * p.storage_mwh_th
    annual_cost = capex * crf + p.fixed_cost_eur_per_mw_yr * p.p_elec_mw
    return {
        "capex_eur": capex,
        "annualised_cost_eur": annual_cost,
        "daily_cost_eur": annual_cost / 365,
        "net_daily_gain_eur": gain_day - annual_cost / 365,
        "breakeven_equivalent_days": annual_cost / gain_day if gain_day > 0 else float("inf"),
    }


def sensitivity(price, dt, p: Params) -> pd.DataFrame:
    rows = []
    for gas in (0.8 * p.gas_price, p.gas_price, 1.2 * p.gas_price):
        for add in (0.5 * p.adders, p.adders, 1.5 * p.adders):
            q = replace(p, gas_price=gas, adders=add)
            g = summarise(optimise(price, dt, q), dt, q)["gain_eur"]
            rows.append({"gas_price": round(gas, 1), "adders": round(add, 1),
                         "breakeven_price": round(q.breakeven_price, 1), "gain_day_eur": round(g),
                         "days_to_cover_annual_cost": round(economics(g, q)["breakeven_equivalent_days"], 1)})
    return pd.DataFrame(rows)


def stress_tests(price, dt, p: Params) -> pd.DataFrame:
    """Does the case survive if the price signal weakens or is not passed through?"""
    cases = {
        "6 April prices as given": price,
        "negative prices floored at 0 (not passed through)": np.maximum(price, 0.0),
        "spot +10 EUR/MWh (flexibility fills the valley)": price + 10.0,
        "spot +20 EUR/MWh": price + 20.0,
    }
    rows = []
    for name, pr in cases.items():
        res = optimise(pr, dt, p)
        k = summarise(res, dt, p)
        rows.append({"case": name, "gain_day_eur": round(k["gain_eur"]),
                     "hours_boiler_on": k["hours_boiler_on"],
                     "days_to_cover_annual_cost": round(economics(k["gain_eur"], p)["breakeven_equivalent_days"], 1)})
    return pd.DataFrame(rows)


def size_sweep(price, dt, p: Params, boiler_factors=(1.0, 1.2, 1.4, 1.65, 2.0),
               storages=(0.0, 20.0, 40.0, 80.0, 120.0)) -> pd.DataFrame:
    """Boiler size x storage size. `peak_electric_mw` below `boiler_mw_e` = installed power never used."""
    rows = []
    for f in boiler_factors:
        for E in storages:
            q = replace(p, p_elec_mw=p.p_elec_mw * f, storage_mwh_th=E)
            k = summarise(optimise(price, dt, q), dt, q)
            e = economics(k["gain_eur"], q)
            rows.append({"boiler_mw_e": round(q.p_elec_mw, 1), "storage_mwh_th": E,
                         "gain_day_eur": round(k["gain_eur"]),
                         "peak_electric_mw": round(k["peak_electric_mw"], 1),
                         "capex_meur": round(e["capex_eur"] / 1e6, 2),
                         "net_daily_gain_eur": round(e["net_daily_gain_eur"]),
                         "days_to_cover": round(e["breakeven_equivalent_days"], 1)})
    return pd.DataFrame(rows)


def plot(res: pd.DataFrame, p: Params, out: Path):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[info] matplotlib missing: figure skipped")
        return
    has_storage = p.storage_mwh_th > 0
    fig, axes = plt.subplots(
        2, 1, figsize=(10, 7.2), sharex=True,
        gridspec_kw={"height_ratios": [1, 1.4]},
    )
    a1, a2 = axes
    x = res.index
    a1.plot(x, res["price"], color="tab:red", label="Spot price (EUR/MWh)")
    a1.axhline(0, color="k", lw=0.6)
    a1.axhline(p.breakeven_price, color="tab:gray", ls="--", label=f"Break-even vs gas ({p.breakeven_price:.0f})")
    a1.set_ylabel("EUR/MWh"); a1.legend(loc="upper right")
    width = 0.8 * (1 if not isinstance(x, pd.DatetimeIndex) else 0.03)
    electric = a2.bar(
        x, res["q_e_th"], color="tab:blue", width=width,
        label="Electric heat for consumption (MW_th)",
    )
    storage_heat = a2.bar(
        x, res["s_out"], bottom=res["q_e_th"], color="tab:green", width=width,
        label="Storage discharge (MW_th)",
    )
    gas_heat = a2.bar(
        x, res["q_g_th"], bottom=res["q_e_th"] + res["s_out"],
        color="tab:orange", width=width, label="Gas heat (MW_th)",
    )
    handles = [electric, storage_heat, gas_heat]
    if has_storage:
        electric_storage = a2.bar(
            x, -res["e_store_th"], color="tab:purple", width=width,
            label="Electric heat sent to storage (MW_th)",
        )
        gas_storage = a2.bar(
            x, -res["g_store_th"], bottom=-res["e_store_th"],
            color="tab:brown", width=width,
            label="Gas heat sent to storage (MW_th)",
        )
        handles += [electric_storage, gas_storage]
    a2.axhline(0, color="k", linewidth=0.6)
    demand = a2.axhline(
        p.demand_mw_th, color="tab:gray", ls=":", linewidth=1.2,
        label="Heat demand (MW_th)",
    )
    handles.append(demand)
    a2.set_ylabel("Heat supplied / stored (MW_th)")
    a2.legend(handles=handles, loc="upper left", fontsize=8)
    a2.set_title("Heat consumption supplied by electricity, storage, and gas")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"[info] figure saved: {out}")

    if has_storage:
        storage_out = out.with_name(f"{out.stem}_storage{out.suffix}")
        fig_storage, a3 = plt.subplots(figsize=(10, 3.6))
        net = a3.bar(x, res["net_store_th"], color="tab:gray", width=width,
                     label="Net charge (+) / discharge (-) (MW_th)")
        a3.axhline(0, color="k", linewidth=0.6)
        a3.set_ylabel("Net storage flow (MW_th)")
        b = a3.twinx()
        soc = b.plot(x, res["soc"], color="tab:green", linewidth=2,
                     label="State of charge (MWh_th)")
        b.set_ylabel("Stored heat (MWh_th)")
        b.set_ylim(0, p.storage_mwh_th * 1.05)
        a3.legend(handles=[net, soc[0]], loc="upper left", fontsize=8)
        a3.set_title("Net storage charge and state of charge")
        fig_storage.tight_layout()
        fig_storage.savefig(storage_out, dpi=150, bbox_inches="tight")
        print(f"[info] figure saved: {storage_out}")


# --------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--preset", choices=["steel"], help="load the teammate's steel-plant parameters")
    ap.add_argument("--price-col"); ap.add_argument("--time-col")
    ap.add_argument("--sep", default=","); ap.add_argument("--decimal", default=",")
    ap.add_argument("--skiprows", type=int, default=2,
                    help="number of metadata rows before the CSV header")
    ap.add_argument("--demand", type=float, default=None, help="MW_th flat heat demand")
    ap.add_argument("--p-elec", type=float, default=None, help="MW_e electric boiler")
    ap.add_argument("--gas-min", type=float, default=None, help="MW_th minimum gas boiler output")
    ap.add_argument("--co2-price", type=float, default=None, help="EUR/tCO2 applied to gas burned")
    ap.add_argument("--discount", type=float, default=None, help="discount rate for the capex annuity (0 = straight line)")
    ap.add_argument("--storage", type=float, default=40.0, help="MWh_th thermal storage for the 2nd scenario")
    ap.add_argument("--oversize", type=float, default=1.0,
                    help="boiler size factor in the storage scenario (default 1.0 = the SAME boiler as scenario A; "
                         ">1 adds electric boiler capacity on top of the storage)")
    ap.add_argument("--gas-price", type=float, default=None); ap.add_argument("--adders", type=float, default=None)
    ap.add_argument("--date", default="2025-04-06", help="study day, used if the time column has no date")
    ap.add_argument("--storage-eff", type=float, default=None,
                    help="storage charge AND discharge efficiency (default 0.95 each; 1.0 = lossless)")
    ap.add_argument("--sweep", action="store_true", help="also run the boiler size x storage size sweep")
    ap.add_argument("--out", default="figures/boiler_6avril.png")
    a = ap.parse_args()

    p = Params(**STEEL_PRESET) if a.preset == "steel" else Params()
    overrides = {"demand_mw_th": a.demand, "p_elec_mw": a.p_elec, "gas_min_mw_th": a.gas_min,
                 "co2_price": a.co2_price, "discount": a.discount, "gas_price": a.gas_price, "adders": a.adders,
                 "storage_eta_in": a.storage_eff, "storage_eta_out": a.storage_eff}
    p = replace(p, **{k: v for k, v in overrides.items() if v is not None})

    s, dt = load_prices(a.csv, a.price_col, a.time_col, a.sep, a.decimal, a.skiprows, a.date)
    price = s.to_numpy()
    print(f"{len(s)} steps, dt={dt} h, price min/mean/max = {price.min():.1f}/{price.mean():.1f}/{price.max():.1f} EUR/MWh")
    print(f"Gas heat cost = {p.gas_heat_cost:.1f} EUR/MWh_th | break-even spot price = {p.breakeven_price:.1f} EUR/MWh_e")
    print(f"Steps below break-even: {(price < p.breakeven_price).sum()} / {len(price)}\n")

    scenarios = (
        ("A", "A. Electric boiler, no storage", 0.0, p.p_elec_mw),
        ("B", (f"B. Same boiler ({p.p_elec_mw:.0f} MW_e) + {a.storage:.0f} MWh_th storage" if a.oversize == 1.0
         else f"B. Boiler x{a.oversize:g} ({p.p_elec_mw * a.oversize:.0f} MW_e) + {a.storage:.0f} MWh_th storage"),
         a.storage, p.p_elec_mw * a.oversize),
    )
    runs = []
    for tag, label, cap, size in scenarios:
        q = replace(p, storage_mwh_th=cap, p_elec_mw=size)
        res = optimise(price, dt, q); res.index = s.index
        k = summarise(res, dt, q)
        e = economics(k["gain_eur"], q)
        print(f"== {label} ==")
        for key, val in {**k, **e}.items():
            print(f"  {key:38s} {val:12,.1f}")
        print()
        runs.append((tag, res, q))

    base_q = runs[0][2]
    print("== Stress tests (scenario A) ==")
    print(stress_tests(price, dt, base_q).to_string(index=False))
    print("\n== Sensitivity: gas price x adders (scenario A) ==")
    print(sensitivity(price, dt, base_q).to_string(index=False))

    if a.sweep:
        sw = size_sweep(price, dt, p)
        print("\n== Sizing sweep: boiler MW_e x storage MWh_th (days_to_cover = 6 April-like days per year) ==")
        print(sw.to_string(index=False))
        print("lowest days_to_cover :", sw.loc[sw["days_to_cover"].idxmin()].to_dict())
        print("highest net daily gain:", sw.loc[sw["net_daily_gain_eur"].idxmax()].to_dict())
        sw_path = Path(a.out).with_name("sizing_sweep.csv")
        sw_path.parent.mkdir(parents=True, exist_ok=True)
        sw.to_csv(sw_path, index=False)

    for tag, res, q in runs:
        out = Path(a.out)
        out = out.with_name(f"{out.stem}_{tag}{out.suffix}")
        plot(res, q, out)
        res.to_csv(out.with_suffix(".csv"))


if __name__ == "__main__":
    main()