#!/usr/bin/env python3
"""Probe whether your MiGO account exposes gas and electricity energy measures.

Run it from the repository root:

    MIGO_USERNAME='you@example.com' MIGO_PASSWORD='...' uv run python probe_energy.py

Credentials are read from the environment and never written anywhere. Nothing is
sent apart from the normal API calls the integration already makes.

The four energy measure types are now used by the integration (see
const.MEASURE_TYPES), and were confirmed against a live NAVaillant gateway: all
six types come back in a single request, and energy is reported in Wh at whole-kWh
resolution.

Keep this script for the next round of reverse engineering. The MiGO backend is
undocumented, so the way to learn what a measure type does is to ask for it and
look. Add candidates to ENERGY_TYPES and run it: an unsupported type returns an
empty series rather than an error, which is why the control types matter.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from custom_components.migo_netatmo.api import MigoApi, MigoApiError

# Note the French spelling "gaz". Getting this wrong returns an empty result
# rather than an error, which would look exactly like "not supported".
ENERGY_TYPES = [
    "sum_energy_gaz_heating",
    "sum_energy_gaz_hot_water",
    "sum_energy_elec_heating",
    "sum_energy_elec_hot_water",
]

# The two the integration already uses, as a control: if these come back empty
# too, the problem is the request or the account, not the energy types.
CONTROL_TYPES = ["sum_boiler_on", "sum_boiler_off"]


def _summarise(body: object) -> str:
    """Describe a getmeasure body without dumping it."""
    if isinstance(body, dict):
        if not body:
            return "empty dict"
        values = [v for v in body.values() if isinstance(v, list) and v]
        sample = values[0] if values else None
        return f"dict, {len(body)} timestamps, first value {sample}"
    if isinstance(body, list):
        if not body:
            return "empty list"
        first = body[0]
        if isinstance(first, dict):
            series = first.get("value") or []
            non_null = [v for v in series if v not in (None, [None])]
            return (
                f"list, {len(body)} series, beg_time={first.get('beg_time')}, "
                f"step_time={first.get('step_time')}, {len(series)} points, "
                f"{len(non_null)} non-null, first {series[:2]}"
            )
        return f"list of {type(first).__name__}, {len(body)} items"
    return f"{type(body).__name__}: {body!r}"


async def main() -> int:
    """Authenticate, find the device pair, and try each measure type."""
    username = os.environ.get("MIGO_USERNAME")
    password = os.environ.get("MIGO_PASSWORD")
    if not username or not password:
        print("Set MIGO_USERNAME and MIGO_PASSWORD in the environment.", file=sys.stderr)
        return 2

    api = MigoApi(username=username, password=password)
    try:
        await api.authenticate()
        print("Authenticated.\n")

        homes = (await api.get_homes_data()).get("body", {}).get("homes") or []
        if not homes:
            print("No homes returned.", file=sys.stderr)
            return 1

        # Find a gateway and the thermostat bridged to it, the same pairing the
        # coordinator does for the boiler runtime sensor.
        gateway_id = thermostat_id = None
        for home in homes:
            modules = home.get("modules") or []
            for module in modules:
                if module.get("type") == "NAVaillant":
                    gateway_id = module.get("id")
            for module in modules:
                if module.get("type") == "NAThermVaillant" and module.get("bridge") == gateway_id:
                    thermostat_id = module.get("id")
            if gateway_id and thermostat_id:
                break

        if not gateway_id or not thermostat_id:
            print(f"Could not find a gateway/thermostat pair (gateway={gateway_id}).", file=sys.stderr)
            return 1

        print(f"Gateway    : {gateway_id}")
        print(f"Thermostat : {thermostat_id}\n")

        # 90 days back, monthly scale: matches what the app's yearly graph needs
        # and is generous enough that an empty result means unsupported, not
        # simply "no data in that window".
        date_begin = int(time.time()) - 90 * 24 * 3600

        for scale in ("1month", "1day"):
            print(f"--- scale={scale} " + "-" * 40)
            for measure_type in CONTROL_TYPES + ENERGY_TYPES:
                label = "control" if measure_type in CONTROL_TYPES else "energy "
                try:
                    response = await api.get_measure(
                        device_id=gateway_id,
                        module_id=thermostat_id,
                        scale=scale,
                        measure_types=[measure_type],
                        date_begin=date_begin,
                    )
                except MigoApiError as err:
                    print(f"  [{label}] {measure_type:26} ERROR: {err}")
                    continue
                print(f"  [{label}] {measure_type:26} {_summarise(response.get('body'))}")
            print()

    finally:
        await api.close()

    print("If the energy rows show data, the integration can expose them as kWh")
    print("sensors that the Energy dashboard accepts directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
