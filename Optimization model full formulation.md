# Optimization model: full formulation

Oct 9, 2026 · @RED

The whole model is one linear program: for each hour of 6 April 2025 it splits a constant 50 MW\_th heat demand between an electric boiler, a gas boiler and a thermal storage at least cost. Every equation is grouped below in presentation order: the problem, its coefficients, then the results computed from its solution.

## The optimization problem

The model minimises one daily cost under seven constraints; storage belongs to the same program and switches off when its capacity is 0.

```latex
\begin{aligned}
\min_{Q_e,\,Q_g,\,S^{in},\,S^{out},\,E} \quad & \sum_{t=1}^{T} \Delta t \left( c_{e,t}\, Q_{e,t} + c_g\, Q_{g,t} \right) & \text{(O)} \\
\text{s.t.} \quad & Q_{e,t} + Q_{g,t} + S^{out}_t = D + S^{in}_t & \text{(C1)} \\
& 0 \le Q_{e,t} \le \eta_e P_{e,max} & \text{(C2)} \\
& Q_{g,t} \ge Q_{g,min} & \text{(C3)} \\
& E_{t+1} = (1-\lambda)^{\Delta t} E_t + \Delta t \left( S^{in}_t - S^{out}_t \right) & \text{(C4)} \\
& 0 \le E_t \le E_{max} & \text{(C5)} \\
& 0 \le S^{in}_t \le \eta_e P_{e,max}, \quad 0 \le S^{out}_t \le D & \text{(C6)} \\
& E_{T+1} = E_1 & \text{(C7)}
\end{aligned}
```

- **(O) Objective.** Daily heat cost: electricity bought at the spot price plus fees, and gas burned. The coefficients c\_e,t and c\_g are defined below.
- **(C1) Heat balance.** The boilers plus the storage discharge cover the demand plus the storage charge, every hour.
- **(C2) Electric boiler capacity.** At most η\_e × P\_e,max = 49 MW\_th in the preset; with C1 and C3 the usable limit without storage is 40 MW\_th.
- **(C3) Gas minimum load.** The gas boiler never drops below 10 MW\_th.
- **(C4) Storage balance.** Stored heat carries over from hour to hour, minus a loss of 0.5% per hour.
- **(C5) Storage capacity.** Between 0 and E\_max, which is 40 MWh\_th in the storage scenario.
- **(C6) Charge and discharge limits.** Charging is limited by the electric boiler, discharging by the demand.
- **(C7) Daily cycle.** The day ends with the storage at the level it started.

The variables are Q\_e,t, Q\_g,t, S\_in,t, S\_out,t and E\_t: five per hour, 5T + 1 in total. The program is solved exactly with the HiGHS solver through scipy's `linprog`. With E\_max = 0, constraints C4 to C7 drop out and both storage flows are 0.

Simplifications to state on the slide: hourly steps, day-ahead prices known in advance, flat demand, no ramp limits and no charge or discharge loss.

## Notation

Heat flows are thermal (MW\_th) and the electric draw is the heat output divided by the efficiency. Values are those of the steel preset, which reproduces your teammate's model.

| Symbol | Meaning | Unit | Type | Value |
| --- | --- | --- | --- | --- |
| π\_t | Spot price in hour t | €/MWh\_e | Data | From the CSV |
| Δt, T | Time step, number of steps | h, count | Data | 1, 24 |
| D | Process heat demand | MW\_th | Parameter | 50, flat |
| η\_e, η\_g | Electric and gas boiler efficiency | none | Parameter | 0.98, 0.90 |
| c\_gas, c\_CO2, ε\_gas | Gas price, CO2 price, gas emission factor | €/MWh\_gas, €/t, t/MWh\_gas | Parameter | 40, 0, 0.2 |
| c\_adders | Grid fee, taxes and margin per MWh drawn | €/MWh\_e | Parameter | 15 |
| Q\_g,min | Gas boiler minimum output | MW\_th | Parameter | 10 |
| P\_e,max | Electric boiler capacity | MW\_e | Parameter | 50 |
| E\_max, λ | Storage capacity, heat loss per hour | MWh\_th, 1/h | Parameter | 40 in the storage scenario, 0.005 |
| k\_e, k\_s, f | Capex per MW\_e, capex per MWh\_th, fixed cost | €/MW\_e, €/MWh\_th, €/MW\_e/yr | Parameter | 100,000; 15,000; 0 |
| r, n | Discount rate, lifetime | none, years | Parameter | 0, 15 |
| ε\_grid | Grid emission factor | t/MWh\_e | Parameter | 0.03 |
| Q\_e,t, Q\_g,t | Heat from the electric and the gas boiler | MW\_th | Variable | Solved |
| S\_in,t, S\_out,t | Heat into and out of storage | MW\_th | Variable | Solved, 0 without storage |
| E\_t | Stored heat | MWh\_th | Variable | Solved, 0 to E\_max |
| P\_e,t | Electric power drawn, Q\_e,t / η\_e | MW\_e | Derived | From Q\_e,t |
| c\_g, c\_e,t | Marginal heat cost of gas and of electricity | €/MWh\_th | Derived | 44.44; (π\_t + 15) / 0.98 |

## Cost coefficients and the no-storage shortcut

The two coefficients in the objective come from fuel prices, efficiencies and fees; comparing them gives the break-even spot price.

**K1. Marginal heat cost of each boiler.** In the preset, gas heat costs 44.44 €/MWh\_th and electric heat costs (π\_t + 15) / 0.98.

```latex
c_g = \frac{c_{gas} + c_{CO_2}\,\varepsilon_{gas}}{\eta_g}, \qquad c_{e,t} = \frac{\pi_t + c_{adders}}{\eta_e}
```

**K2. Break-even price and dispatch rule without storage.** Electric heat is cheaper below π\* = 28.56 €/MWh\_e in the preset. The rule holds when the boiler is large enough.

```latex
\pi^{*} = \eta_e\, c_g - c_{adders}, \qquad Q_{e,t} = \begin{cases} D - Q_{g,min} & \text{if } \pi_t < \pi^{*} \\ 0 & \text{otherwise} \end{cases}
```

Without storage no constraint links one hour to the next, so this threshold rule is the exact optimum of the program above.

## Equations used after the optimization

Once the program is solved, these formulas turn its solution into the numbers on the results slides.

### Results

**R1. Baseline and gain:** the gas-only cost and the daily saving.

```latex
C_{base} = \sum_t \Delta t\, D\, c_g, \qquad G = C_{base} - C_{opt}
```

**R2. Where the gain comes from:** the saving split between negative-price hours and the others.

```latex
G = \sum_{t:\,\pi_t<0} g_t + \sum_{t:\,\pi_t \ge 0} g_t, \qquad g_t = \Delta t \left( D\, c_g - c_{e,t} Q_{e,t} - c_g Q_{g,t} \right)
```

**R3. Electricity absorbed in negative-price hours, and the income from negative prices.**

```latex
W_{-} = \sum_{t:\,\pi_t<0} \Delta t\, P_{e,t}, \qquad I_{-} = -\sum_{t:\,\pi_t<0} \pi_t\, \Delta t\, P_{e,t}, \qquad P_{e,t} = \frac{Q_{e,t}}{\eta_e}
```

**R4. Gas and CO2 avoided.** The CO2 term subtracts the emissions of the electricity the boiler draws.

```latex
\Delta G = \frac{D\,T\,\Delta t - \sum_t \Delta t\, Q_{g,t}}{\eta_g}, \qquad \Delta CO_2 = \varepsilon_{gas}\, \Delta G - \varepsilon_{grid} \sum_t \Delta t\, P_{e,t}
```

### Investment

**I1. Capex.**

```latex
K = k_e\, P_{e,max} + k_s\, E_{max}
```

**I2. Annualised cost** with a capital recovery factor. With a zero discount rate it is straight-line.

```latex
A = K \cdot \frac{r\,(1+r)^n}{(1+r)^n - 1} + f\, P_{e,max} \qquad \left( r = 0:\; A = K/n + f\, P_{e,max} \right)
```

**I3. Break-even days and net daily gain.** N\* is the number of days per year like 6 April needed for the gain to cover the annualised cost. It is not a forecast of how many such days occur.

```latex
N^{*} = \frac{A}{G}, \qquad \text{net daily gain} = G - \frac{A}{365}
```

### Stress tests

**S1. Price scenarios:** negative prices not passed through, or a flatter market.

```latex
\pi'_t = \max(\pi_t, 0) \qquad \text{or} \qquad \pi'_t = \pi_t + \delta, \quad \delta \in \{10, 20\}\ \text{€/MWh}
```

In `Industrial_heat_model.py` the problem is `optimise`, the coefficients are the properties of `Params`, the results are `summarise`, the investment is `economics`, the price scenarios are `stress_tests` and the sizing sweep is `size_sweep`.
