"""Task-aware scripted evidence reference for the original vending domain.

This policy sees only a public task description and a tool-call callback. It can
run unchanged against a Session wrapper or a remote HTTP client. It does not
submit, access evaluator objects, or use hidden state. Its score is a scripted
reference result, never an LLM result or a measure of general reasoning.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


def _integer(value: Any, name: str, low: int = 0, high: int = 1_000_000) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid observed {name}")
    return value


def solve_vending(public: dict, call: Callable[[str, dict], dict]) -> dict:
    """Operate using observed quotes/status, then return the recovered fields.

    The callback takes ``(tool_name, arguments)`` and returns its response object.
    Extra tracing fields such as event_id and cost_used are harmless. A tool
    error or an incompatible public contract raises ValueError immediately.
    """
    if not isinstance(public, dict) or public.get("family") != "vending":
        raise ValueError("the evidence reference requires a vending episode")

    def observe(name: str, args: dict) -> dict:
        response = call(name, args)
        if not isinstance(response, dict):
            raise ValueError(f"{name} returned a non-object response")
        if "error" in response:
            raise ValueError(f"{name} failed: {str(response['error'])[:240]}")
        return response

    listed = public.get("files", [])
    if not isinstance(listed, list) or any(
        path not in listed for path in ("/docs/accounting.txt", "/skills/procurement.txt")
    ):
        raise ValueError("the required public procurement documents are absent")
    accounting = observe("read_file", {"path": "/docs/accounting.txt"}).get("content")
    procedure = observe("read_file", {"path": "/skills/procurement.txt"}).get("content")
    if not isinstance(accounting, str) or not isinstance(procedure, str):
        raise ValueError("public procurement documents must contain text")
    cap_match = re.search(r"Warehouse capacity:\s*(\d+)\s+units", accounting)
    receipt_match = re.search(r"records a separate physical receipt on ([a-z]+)", accounting)
    if cap_match is None or receipt_match is None:
        raise ValueError("the documented capacity or receipt event is missing")
    capacity = _integer(int(cap_match.group(1)), "warehouse capacity", 1)
    receipt_event = receipt_match.group(1)
    if receipt_event not in {"order", "invoice", "delivery"}:
        raise ValueError("the documented receipt event is outside the public schema")
    if "order_day % 7 in (5, 6)" not in procedure:
        raise ValueError("the supported weekday convention is absent")

    market = observe("market", {})
    demand_cycle = market.get("base_demand_by_weekday")
    if not isinstance(demand_cycle, list) or len(demand_cycle) != 7:
        raise ValueError("the public recurring demand forecast must have seven days")
    demand_cycle = [_integer(value, "weekday demand", 0, 10000) for value in demand_cycle]
    state = observe("status", {})
    horizon = _integer(state.get("horizon_days"), "horizon", 6, 10000)
    start_day = _integer(state.get("day"), "current day", 0, horizon)
    if start_day >= horizon:
        raise ValueError("the business episode has already ended")

    first = observe("quote", {"supplier": "cedar", "cases": 1, "order_day": 0})
    second = observe("quote", {"supplier": "cedar", "cases": 2, "order_day": 0})
    weekend = observe("quote", {"supplier": "cedar", "cases": 1, "order_day": 5})
    first_shipping = _integer(first.get("shipping_cents"), "one-case shipping")
    second_shipping = _integer(second.get("shipping_cents"), "two-case shipping")
    base_lead = _integer(first.get("arrival_day"), "weekday arrival", 1, 30)
    weekend_arrival = _integer(weekend.get("arrival_day"), "weekend arrival", 6, 65)
    case_fee = second_shipping - first_shipping
    fixed_fee = first_shipping - case_fee
    weekend_extra = weekend_arrival - 5 - base_lead
    if min(case_fee, fixed_fee, weekend_extra) < 0:
        raise ValueError("observed quotes conflict with the documented nonnegative coefficients")
    case_size = _integer(first.get("units_per_case"), "case size", 1, capacity)
    unit_cost = _integer(first.get("unit_cost_cents"), "unit acquisition cost", 1)
    if (second.get("units_per_case") != case_size or second.get("unit_cost_cents") != unit_cost
            or second.get("arrival_day") != base_lead
            or weekend.get("shipping_cents") != first_shipping):
        raise ValueError("quotes are incompatible with the documented stable supplier model")
    fill = {
        "lead_base_days": base_lead,
        "weekend_extra_days": weekend_extra,
        "fixed_fee_cents": fixed_fee,
        "case_fee_cents": case_fee,
        "receipt_event": receipt_event,
    }
    if set(public.get("slots", {})) != set(fill):
        raise ValueError("the public completion schema has changed")

    # This known-domain policy chooses a price in the zero-offset demand band.
    # Read the public response rather than assuming that 280 retains this meaning.
    price = 280
    price_bands = market.get("price_bands_cents", [])
    if not isinstance(price_bands, list) or not any(
        isinstance(band, dict) and type(band.get("from")) is int
        and type(band.get("to")) is int and band["from"] <= price <= band["to"]
        and band.get("demand_offset") == 0 for band in price_bands
    ):
        raise ValueError("the documented zero-offset price band has changed")
    observe("set_price", {"price_cents": price})
    day = start_day
    while day < horizon:
        if _integer(state.get("day"), "current day", 0, horizon) != day:
            raise ValueError("observed day progression is inconsistent")
        available = _integer(state.get("available_units"), "available inventory", 0, capacity)
        pending = _integer(state.get("pending_units"), "pending inventory", 0, capacity)
        cash = _integer(state.get("cash_cents"), "available cash", 0, 1_000_000_000)
        position = available + pending
        if position > capacity:
            raise ValueError("observed inventory exceeds documented capacity")
        lead = base_lead + (weekend_extra if day % 7 in (5, 6) else 0)
        arrival = day + lead
        desired = sum(demand_cycle[future % 7] + 1
                      for future in range(day + 1, min(horizon, day + lead + 2) + 1))
        shortage = max(0, desired - position)
        cases = min((shortage + case_size - 1) // case_size, (capacity - position) // case_size)
        per_case_debit = unit_cost * case_size + case_fee
        affordable = max(0, (cash - fixed_fee) // per_case_debit)
        cases = min(cases, affordable)
        if cases and arrival <= horizon:
            observe("order", {"supplier": "cedar", "cases": cases})
        advanced = observe("advance", {"days": 1})
        state = advanced.get("status")
        if not isinstance(state, dict):
            raise ValueError("advance did not return a public business status")
        day += 1
    if _integer(state.get("day"), "final day", 0, horizon) != horizon:
        raise ValueError("the observed business did not reach its horizon")
    return fill
