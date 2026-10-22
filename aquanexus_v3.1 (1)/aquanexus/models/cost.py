"""
cost.py

Cost model covering electricity (grid and renewable, priced separately),
water, and annualized capital expenditure.

Previous version charged only grid electricity and treated renewable energy
and capex as zero cost, which made the lowest-water/lowest-PUE option always
win on cost as well, collapsing the Pareto frontier to a single point
(identified in external review). This version:

  1. Prices renewable electricity at its levelized cost of energy (LCOE),
     not zero. Gulf utility-scale solar LCOE has been publicly reported as
     low as ~1.32 US cents/kWh (Abu Dhabi's Al Dhafra solar project PPA,
     widely reported as a world-record tariff at the time), so a small but
     nonzero LCOE is used rather than treating solar as free.
  2. Annualizes capital expenditure using a capital recovery factor (CRF),
     so a technology's higher upfront cost is reflected in its daily cost,
     not ignored.

CRF = r(1+r)^n / ((1+r)^n - 1)

Both baseline_capex_usd_per_mw and the discount rate/lifetime are ENGINEERING
ASSUMPTIONS, not sourced procurement figures. No public, facility-specific
cost breakdown for cooling-system capex alone was located for this project;
these are explicitly labeled placeholders, editable, pending better data.
"""

from dataclasses import dataclass


@dataclass
class CostResult:
    electricity_cost_usd_per_day: float       # grid electricity only
    renewable_cost_usd_per_day: float          # renewable electricity at LCOE
    water_cost_usd_per_day: float
    annualized_capex_usd_per_day: float
    battery_cost_usd_per_day: float            # annualized battery capex
    total_opex_usd_per_day: float              # electricity + renewable + water (no capex)
    total_cost_usd_per_day: float              # opex + annualized capex


def capital_recovery_factor(discount_rate: float, lifetime_years: float) -> float:
    if discount_rate <= 0:
        return 1.0 / lifetime_years
    r = discount_rate
    n = lifetime_years
    return (r * (1 + r) ** n) / (((1 + r) ** n) - 1)


def compute_operational_cost(
    grid_energy_mwh_per_day: float,
    electricity_price_usd_per_kwh: float,
    renewable_energy_mwh_per_day: float,   # solar GENERATED (incl. curtailed), all of it is paid for
    renewable_lcoe_usd_per_kwh: float,
    total_water_m3_per_day: float,
    water_cost_usd_per_m3: float,
    capex_relative: float,
    it_capacity_mw: float,
    baseline_capex_usd_per_mw: float = 1_500_000.0,
    discount_rate: float = 0.08,
    lifetime_years: float = 10.0,
    battery_capacity_mwh: float = 0.0,
    battery_capex_usd_per_kwh: float = 300.0,
) -> CostResult:
    for name, val in [
        ("grid_energy_mwh_per_day", grid_energy_mwh_per_day),
        ("renewable_energy_mwh_per_day", renewable_energy_mwh_per_day),
        ("total_water_m3_per_day", total_water_m3_per_day),
        ("capex_relative", capex_relative),
        ("it_capacity_mw", it_capacity_mw),
    ]:
        if val < 0:
            raise ValueError(f"{name} cannot be negative.")
    for name, val in [
        ("electricity_price_usd_per_kwh", electricity_price_usd_per_kwh),
        ("renewable_lcoe_usd_per_kwh", renewable_lcoe_usd_per_kwh),
        ("water_cost_usd_per_m3", water_cost_usd_per_m3),
    ]:
        if val < 0:
            raise ValueError(f"{name} cannot be negative.")

    electricity_cost = grid_energy_mwh_per_day * 1000.0 * electricity_price_usd_per_kwh
    renewable_cost = renewable_energy_mwh_per_day * 1000.0 * renewable_lcoe_usd_per_kwh
    water_cost = total_water_m3_per_day * water_cost_usd_per_m3

    crf = capital_recovery_factor(discount_rate, lifetime_years)
    annual_capex = capex_relative * baseline_capex_usd_per_mw * it_capacity_mw * crf
    daily_capex = annual_capex / 365.0

    # Battery: annualized installed cost. ENGINEERING ASSUMPTION ($300/kWh,
    # editable); not a sourced procurement price.
    battery_cost = battery_capacity_mwh * 1000.0 * battery_capex_usd_per_kwh * crf / 365.0

    total_opex = electricity_cost + renewable_cost + water_cost
    total_cost = total_opex + daily_capex + battery_cost

    return CostResult(
        electricity_cost_usd_per_day=round(electricity_cost, 2),
        renewable_cost_usd_per_day=round(renewable_cost, 2),
        water_cost_usd_per_day=round(water_cost, 2),
        annualized_capex_usd_per_day=round(daily_capex, 2),
        battery_cost_usd_per_day=round(battery_cost, 2),
        total_opex_usd_per_day=round(total_opex, 2),
        total_cost_usd_per_day=round(total_cost, 2),
    )
