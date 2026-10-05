# Scripts

Throwaway diagnostics for reverse engineering the MiGO backend. Nothing here is
shipped to users: the release archive is built from `custom_components/migo_netatmo`
only.

## `probe_energy.py`

Asks `/api/getmeasure` for a list of measure types and reports what comes back,
without dumping payloads.

```bash
MIGO_USERNAME='you@example.com' MIGO_PASSWORD='...' uv run python scripts/probe_energy.py
```

Credentials come from the environment and are never written anywhere.

It exists because the backend is undocumented: the only way to find out what a
measure type does is to ask for it. An unsupported type returns an **empty series
rather than an error**, which is indistinguishable from "your hardware does not
support this" — hence the control types, which prove the request itself works.

This is how the four energy measure types in `const.MEASURE_TYPES` were confirmed,
and how the Wh unit was calibrated against the MiGO app's own figures.
