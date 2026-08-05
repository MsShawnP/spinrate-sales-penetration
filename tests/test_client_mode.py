"""Client-mode + POS-intake tests for Spin Rate (checklist §6).

Skipped unless the shared ``lailara_engagement`` lib is installed. Fixtures are
generated on the fly — no client identifiers, no committed data. The fixture is
tuned to reproduce the engine golden (13 weeks -> days=91; SPPD 2.0/door-day;
wholesale $10) so the client-mode totals match calculate_expansion_upside.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("lailara_engagement")

import client_mode  # noqa: E402

AS_OF = pd.Timestamp("2025-12-27")                 # Saturday
WEEKS = [AS_OF - timedelta(weeks=(12 - i)) for i in range(13)]   # 13 weeks -> days=91
EARLY = WEEKS[0] - timedelta(weeks=4)
DOORS = {"CHP-AS-001": 3, "CHP-AS-002": 6, "CHP-AS-003": 9}


def _world():
    stores, auth, scans, seen = [], [], [], set()
    for sku, n in DOORS.items():
        for s in range(n):
            sid = f"S{s}"
            if sid not in seen:
                stores.append((sid, "RET-KRG", "Kroger", "Midwest", "OH", "B"))
                seen.add(sid)
            auth.append((sku, sid, EARLY.strftime("%Y-%m-%d"), ""))
            for w in WEEKS:
                # 14 units/week -> 2.0/door-day over days=91; $5 retail scan/unit.
                scans.append((sid, sku, w.strftime("%Y-%m-%d"), 14, 70.0))
    products = pd.DataFrame([(s, "AS", 10.0) for s in DOORS],
                            columns=["sku", "product_line", "wholesale_price"])
    return (pd.DataFrame(stores, columns=["store_id", "retailer_id", "chain_name", "region", "state", "volume_tier"]),
            pd.DataFrame(auth, columns=["sku", "store_id", "authorized_date", "deauthorized_date"]),
            pd.DataFrame(scans, columns=["store_id", "sku", "week_ending", "units_sold", "dollars_sold"]),
            products)


def _write_all(d: Path):
    stores, auth, scans, products = _world()
    sp, ap, stp, pp = d / "scans.csv", d / "auth.csv", d / "stores.csv", d / "products.csv"
    scans.to_csv(sp, index=False); auth.to_csv(ap, index=False)
    stores.to_csv(stp, index=False); products.to_csv(pp, index=False)
    return sp, ap, stp, pp


def _cfg(d: Path, *, columns=None):
    import yaml
    p = d / "engagement.demo.yml"
    p.write_text(yaml.safe_dump({
        "client": {"name": "Cinderhaven Provisions (demo)"}, "engagement": {"id": "T-1"},
        "as_of_date": "2025-12-27", "demo": True,
        "basis": {"week_convention": "week_ending_saturday", "scan_basis": "retail_scan"},
        "columns": columns or {}}), encoding="utf-8")
    return p


def _args(scans=None, auth=None, stores=None, products=None):
    return SimpleNamespace(scans=scans, auth=auth, stores=stores, products=products)


def test_clean_run_reproduces_engine_upside(tmp_path):
    sp, ap, stp, pp = _write_all(tmp_path)
    cfg = _cfg(tmp_path)
    res = client_mode.run(str(cfg), str(tmp_path / "out"), _args(str(sp), str(ap), str(stp), str(pp)))
    assert res["status"] == "ok"
    assert res["total_median_upside"] == 5460.00     # matches the engine golden
    assert res["total_leader_upside"] == 16380.00
    assert Path(res["report"]).is_file() and Path(res["exceptions_csv"]).is_file()


def test_deliverable_separates_wholesale_upside_from_retail_scan_current(tmp_path):
    sp, ap, stp, pp = _write_all(tmp_path)
    cfg = _cfg(tmp_path)
    res = client_mode.run(str(cfg), str(tmp_path / "out"), _args(str(sp), str(ap), str(stp), str(pp)))
    html = Path(res["report"]).read_text(encoding="utf-8")
    assert "upside is valued at WHOLESALE price" in html
    assert "Current $ (retail scan)" in html
    assert "Upside @ median (wholesale)" in html
    assert "Upside basis" in html and "wholesale dollars" in html   # provenance footer
    assert "DRAFT" in html


def test_missing_wholesale_price_blocks(tmp_path):
    sp, ap, stp, pp = _write_all(tmp_path)
    pd.read_csv(pp).drop(columns=["wholesale_price"]).to_csv(pp, index=False)
    cfg = _cfg(tmp_path)
    res = client_mode.run(str(cfg), str(tmp_path / "out"), _args(str(sp), str(ap), str(stp), str(pp)))
    assert res["status"] == "blocked" and res["blocked_files"] == ["products"]


def test_off_convention_week_blocks(tmp_path):
    sp, ap, stp, pp = _write_all(tmp_path)
    df = pd.read_csv(sp); df.loc[0, "week_ending"] = "2025-12-29"  # Monday
    df.to_csv(sp, index=False)
    cfg = _cfg(tmp_path)
    res = client_mode.run(str(cfg), str(tmp_path / "out"), _args(str(sp), str(ap), str(stp), str(pp)))
    assert res["status"] == "blocked"


def test_missing_scan_basis_declaration_errors(tmp_path):
    import yaml
    sp, ap, stp, pp = _write_all(tmp_path)
    cfg = tmp_path / "engagement.demo.yml"
    cfg.write_text(yaml.safe_dump({
        "client": {"name": "Cinderhaven Provisions (demo)"}, "engagement": {"id": "T-1"},
        "as_of_date": "2025-12-27", "demo": True,
        "basis": {"week_convention": "week_ending_saturday"}, "columns": {}}), encoding="utf-8")
    with pytest.raises(Exception):
        client_mode.run(str(cfg), str(tmp_path / "out"), _args(str(sp), str(ap), str(stp), str(pp)))
