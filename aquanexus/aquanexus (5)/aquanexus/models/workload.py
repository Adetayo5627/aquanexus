"""
workload.py

Converts AI workload configuration into IT electrical load and heat load.

ASSUMPTION (explicit, per project instructions):
At first-approximation, all IT electricity consumption is assumed to be
converted to heat that the cooling system must remove:

    Q_IT ≈ P_IT

This is a standard simplifying assumption for early-stage data-centre energy
models. It ignores second-order effects (e.g. some electrical losses radiate
directly to ambient outside the IT room, some energy leaves as network I/O).
For an MVP this approximation is considered acceptable but should be revisited
if greater physical fidelity is required.
"""

from dataclasses import dataclass


@dataclass
class WorkloadConfig:
    """User-defined AI workload scenario. Not a claim about a real facility."""
    it_capacity_mw: float          # nameplate IT capacity, e.g. 50 MW
    utilization_pct: float         # 0-100, average utilization over the period
    operating_hours_per_day: float = 24.0


@dataclass
class WorkloadResult:
    it_power_mw: float             # actual IT electrical draw
    heat_load_mw: float            # heat load presented to the cooling system
    it_energy_mwh_per_day: float


def compute_workload(config: WorkloadConfig) -> WorkloadResult:
    """
    Compute IT power draw, heat load, and daily energy from a workload config.

    Raises:
        ValueError: if inputs are outside physically sensible bounds.
    """
    if config.it_capacity_mw <= 0:
        raise ValueError("it_capacity_mw must be positive.")
    if not (0 <= config.utilization_pct <= 100):
        raise ValueError("utilization_pct must be between 0 and 100.")
    if not (0 < config.operating_hours_per_day <= 24):
        raise ValueError("operating_hours_per_day must be between 0 and 24.")

    it_power_mw = config.it_capacity_mw * (config.utilization_pct / 100.0)
    heat_load_mw = it_power_mw  # Q_IT ≈ P_IT, see module docstring
    it_energy_mwh_per_day = it_power_mw * config.operating_hours_per_day

    return WorkloadResult(
        it_power_mw=it_power_mw,
        heat_load_mw=heat_load_mw,
        it_energy_mwh_per_day=it_energy_mwh_per_day,
    )
