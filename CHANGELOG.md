# Changelog

## 2026-07-02

Correctness, polish, and hygiene pass. 161 tests passing.

### Fixed
- **Quadrant dividing lines are now filter-independent.** Star/gem/dead/question splits use full-dataset SPPD & ACV% medians (`db.get_global_medians()`) instead of the current selection's median, so quadrants no longer reshuffle when filters change.
- **Indexed SPPD benchmarks against a fixed full-dataset category median** (`calculate_category_median_sppd` / `db.get_category_median_sppd`) rather than whatever is currently filtered. A SKU's indexed value is now stable across retailer/region/date filters, and lone-SKU product lines can be flagged at-risk correctly.
- **Quadrant legend no longer clips at the viewport/field boundary.** Removed the forced fixed entry width and folded low-door markers into their product line's legend entry so rows wrap cleanly.
- **ACV% clamped to 100%.** Carrying stores absent from `dim_stores` no longer default to weight 1 (inner join), with a `.clip(upper=1.0)` backstop.
- **Quarter-string validation** in `days_in_quarter_range` now rejects malformed quarters (e.g. `Q9`).

### Changed
- **At-risk Level vs Trend windows disclosed** in the UI: Level uses the active date filter; Trend uses a fixed trailing 8 quarters. Added a window note and column tooltips. No scoring math changed.
- Pinned all dependencies to exact verified versions for reproducible builds.

### Tests
- Removed vacuous `if sku in view:` skip guards and replaced `<=` monotonicity checks with real expected-value assertions.
- Added filter-independence and no-benchmark-is-NaN regression tests.
