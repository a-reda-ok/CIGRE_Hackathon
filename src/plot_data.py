"""Create diagnostic plots from the 6 April 2025 electricity CSV.

Run from the repository root:
    python src/plot_data.py

The generated PNG files are written to ``figures/``. The balance used here is
explicitly a partial balance of the variables present in the CSV; it is not a
physical grid imbalance because hydro, thermal generation, storage, and
cross-border exchanges are not included.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "figures"
CSV_PATH = ROOT / "donnees_6_avril_2025.xlsx - 6 avril 2025.csv"


def load_data(path: Path) -> pd.DataFrame:
    """Load and normalize the French-formatted CSV."""
    frame = pd.read_csv(
        path,
        skiprows=2,
        sep=",",
        decimal=",",
        encoding="utf-8-sig",
    )
    frame.columns = [
        "time",
        "price_eur_mwh",
        "solar_mw",
        "wind_mw",
        "consumption_mw",
        "nuclear_mw",
    ]
    frame["time"] = pd.to_datetime(
        "2025-04-06 " + frame["time"], format="%Y-%m-%d %H:%M"
    ).dt.tz_localize("Europe/Paris")
    numeric_columns = [column for column in frame.columns if column != "time"]
    frame[numeric_columns] = frame[numeric_columns].apply(
        pd.to_numeric, errors="raise"
    )
    frame["partial_balance_mw"] = (
        frame["solar_mw"]
        + frame["wind_mw"]
        + frame["nuclear_mw"]
        - frame["consumption_mw"]
    )
    frame["renewable_mw"] = frame["solar_mw"] + frame["wind_mw"]
    frame["renewable_share_pct"] = (
        frame["renewable_mw"] / frame["consumption_mw"] * 100
    )
    return frame


def save_figure(figure: plt.Figure, name: str) -> None:
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / name, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_price_and_power(data: pd.DataFrame) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(data["time"], data["price_eur_mwh"], color="#b2182b", linewidth=2)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].fill_between(
        data["time"],
        data["price_eur_mwh"],
        0,
        where=data["price_eur_mwh"] < 0,
        color="#f4a582",
        alpha=0.45,
        label="Negative price",
    )
    axes[0].set_ylabel("Price (EUR/MWh)")
    axes[0].set_title("France spot price and power trajectories — 6 April 2025")
    axes[0].legend()

    for column, label, color in [
        ("consumption_mw", "Consumption", "#2166ac"),
        ("nuclear_mw", "Nuclear", "#762a83"),
        ("wind_mw", "Wind", "#1b7837"),
        ("solar_mw", "Solar", "#e08214"),
    ]:
        axes[1].plot(data["time"], data[column], label=label, linewidth=2, color=color)
    axes[1].set_ylabel("Power (MW)")
    axes[1].set_xlabel("Time (Europe/Paris)")
    axes[1].legend(ncol=4)
    save_figure(figure, "01_price_and_power.png")


def plot_generation_composition(data: pd.DataFrame) -> None:
    figure, axis = plt.subplots(figsize=(12, 6))
    axis.stackplot(
        data["time"],
        data["nuclear_mw"],
        data["wind_mw"],
        data["solar_mw"],
        labels=["Nuclear", "Wind", "Solar"],
        colors=["#762a83", "#1b7837", "#e08214"],
        alpha=0.8,
    )
    axis.plot(
        data["time"],
        data["consumption_mw"],
        color="#2166ac",
        linewidth=2.5,
        label="Consumption",
    )
    axis.set_title("Observed generation composition versus consumption")
    axis.set_ylabel("Power (MW)")
    axis.set_xlabel("Time (Europe/Paris)")
    axis.legend(loc="upper left", ncol=4)
    save_figure(figure, "02_generation_composition.png")


def plot_price_vs_partial_balance(data: pd.DataFrame) -> None:
    figure, axis = plt.subplots(figsize=(8, 6))
    points = axis.scatter(
        data["partial_balance_mw"],
        data["price_eur_mwh"],
        c=data["solar_mw"],
        cmap="YlOrBr",
        s=70,
        edgecolor="black",
        linewidth=0.4,
    )
    for _, row in data.iterrows():
        if row["price_eur_mwh"] < 0 or row["partial_balance_mw"] > 10000:
            axis.annotate(
                row["time"].strftime("%H:%M"),
                (row["partial_balance_mw"], row["price_eur_mwh"]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
            )
    axis.axhline(0, color="black", linewidth=0.8)
    axis.axvline(0, color="black", linewidth=0.8)
    axis.set_title("Spot price versus observed partial balance")
    axis.set_xlabel(
        "Partial balance (MW): nuclear + wind + solar − consumption"
    )
    axis.set_ylabel("Price (EUR/MWh)")
    figure.colorbar(points, ax=axis, label="Solar output (MW)")
    save_figure(figure, "03_price_vs_partial_balance.png")


def plot_ramps(data: pd.DataFrame) -> None:
    ramp_data = data.set_index("time")[
        ["solar_mw", "wind_mw", "nuclear_mw", "consumption_mw"]
    ].diff()
    figure, axis = plt.subplots(figsize=(12, 6))
    for column, label, color in [
        ("solar_mw", "Solar", "#e08214"),
        ("wind_mw", "Wind", "#1b7837"),
        ("nuclear_mw", "Nuclear", "#762a83"),
        ("consumption_mw", "Consumption", "#2166ac"),
    ]:
        axis.plot(
            ramp_data.index,
            ramp_data[column],
            marker="o",
            label=label,
            color=color,
        )
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_title("Observed hour-to-hour changes (MW per hour)")
    axis.set_ylabel("Change in power (MW/h)")
    axis.set_xlabel("Time (Europe/Paris)")
    axis.legend(ncol=4)
    save_figure(figure, "04_hourly_ramps.png")


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    data = load_data(CSV_PATH)
    plot_price_and_power(data)
    plot_generation_composition(data)
    plot_price_vs_partial_balance(data)
    plot_ramps(data)
    negative_prices = data.loc[data["price_eur_mwh"] < 0, "price_eur_mwh"]
    print(f"Loaded {len(data)} hourly rows from {CSV_PATH.name}")
    print(
        f"Negative-price hours: {len(negative_prices)}; "
        f"minimum price: {negative_prices.min():.2f} EUR/MWh"
    )
    print(f"Saved plots to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
