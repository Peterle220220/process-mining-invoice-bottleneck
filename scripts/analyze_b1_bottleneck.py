"""
Analyse Part C Problem B1 for the BPI Challenge 2019 data.

Problem B1: Bottleneck from "Record Invoice Receipt" to "Clear Invoice".

The script reads the cleaned CSV, calculates the time between the first
Record Invoice Receipt and the next Clear Invoice for each case, then reports
cases above the chosen threshold and where they concentrate by spend area and
vendor.

If the timestamp column has been damaged during export, for example only
"59:00.0" remains instead of a full date/time, the script stops the duration
calculation and writes a timestamp quality report instead of producing
misleading numbers.
"""

from __future__ import annotations

import argparse
from collections import Counter
import warnings
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_INPUT = (
    Path(__file__).resolve().parents[2]
    / "Final"
    / "BPI_Challenge_2019_final.csv"
)
DOWNLOADS_INPUT = Path.home() / "Downloads" / "BPI_Challenge_2019_final.csv"
DEFAULT_INPUT = DOWNLOADS_INPUT if DOWNLOADS_INPUT.exists() else PROJECT_INPUT

ACTIVITY_RECORD_IR = "Record Invoice Receipt"
ACTIVITY_CLEAR_INVOICE = "Clear Invoice"

REQUIRED_COLUMNS = [
    "Case ID",
    "Activity",
    "Complete Timestamp",
    "case Spend area text",
    "case Company",
    "case Document Type",
    "case Vendor",
    "case Spend classification text",
    "case Name",
    "event Cumulative net worth (EUR)",
]

CHUNK_SIZE = 200_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate B1 bottleneck analysis outputs."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path to cleaned BPI 2019 CSV. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs") / "b1_bottleneck",
        help="Folder where result files will be written.",
    )
    parser.add_argument(
        "--threshold-days",
        type=float,
        default=70.0,
        help="Duration threshold for slow cases.",
    )
    parser.add_argument(
        "--timestamp-format",
        default=None,
        help=(
            "Optional pandas datetime format, for example "
            "'%%Y-%%m-%%d %%H:%%M:%%S'. Leave empty for automatic parsing."
        ),
    )
    return parser.parse_args()


def ensure_columns(df_columns: Iterable[str]) -> None:
    missing = [col for col in REQUIRED_COLUMNS if col not in df_columns]
    if missing:
        raise ValueError(
            "Input file is missing required columns: " + ", ".join(missing)
        )


def read_needed_columns(input_path: Path) -> pd.DataFrame:
    header = pd.read_csv(input_path, nrows=0).columns
    ensure_columns(header)
    return pd.read_csv(input_path, usecols=REQUIRED_COLUMNS, low_memory=False)


def parse_timestamp_series(
    raw: pd.Series, timestamp_format: str | None
) -> pd.Series:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Could not infer format.*",
            category=UserWarning,
        )
        return pd.to_datetime(
            raw,
            format=timestamp_format,
            errors="coerce",
            dayfirst=False,
        )


def parse_timestamps(
    df: pd.DataFrame, timestamp_format: str | None
) -> tuple[pd.DataFrame, dict[str, object]]:
    raw = df["Complete Timestamp"].astype("string")
    parsed = parse_timestamp_series(raw, timestamp_format)

    valid_ratio = float(parsed.notna().mean()) if len(parsed) else 0.0
    unique_dates = int(parsed.dt.date.nunique(dropna=True)) if parsed.notna().any() else 0
    examples = raw.dropna().drop_duplicates().head(20).tolist()

    quality = {
        "row_count": len(df),
        "valid_timestamp_ratio": valid_ratio,
        "unique_dates": unique_dates,
        "min_timestamp": parsed.min(),
        "max_timestamp": parsed.max(),
        "sample_raw_values": examples,
    }

    df = df.copy()
    df["Parsed Timestamp"] = parsed
    return df, quality


def timestamp_is_usable(quality: dict[str, object]) -> bool:
    return (
        quality["valid_timestamp_ratio"] >= 0.95
        and quality["unique_dates"] >= 2
    )


def write_timestamp_quality_report(
    output_dir: Path, quality: dict[str, object], input_path: Path
) -> None:
    sample_values = "\n".join(f"- `{value}`" for value in quality["sample_raw_values"])
    report = f"""# B1 Timestamp Quality Report

Input file: `{input_path}`

The script could not calculate the B1 duration because `Complete Timestamp`
does not look like a full datetime column.

## Quality checks

- Rows checked: {quality["row_count"]:,}
- Parseable timestamp ratio: {quality["valid_timestamp_ratio"]:.2%}
- Unique dates after parsing: {quality["unique_dates"]}
- Minimum parsed timestamp: {quality["min_timestamp"]}
- Maximum parsed timestamp: {quality["max_timestamp"]}

## Sample raw timestamp values

{sample_values}

## What to fix

Export `Complete Timestamp` with the full date and time, such as
`2018-01-31 13:59:00`, then run this script again. B1 needs real dates because
the key evidence is the duration from `Record Invoice Receipt` to
`Clear Invoice`, especially cases longer than 70 days.

Do not repair this by guessing dates. A value like `59:00.0` has already lost
the date component, so the original duration in days cannot be reconstructed
from this CSV alone.
"""
    (output_dir / "b1_timestamp_quality_report.md").write_text(
        report, encoding="utf-8"
    )


def write_basic_outputs(df: pd.DataFrame, output_dir: Path) -> None:
    activity_counts = (
        df["Activity"]
        .value_counts()
        .rename_axis("Activity")
        .reset_index(name="Event count")
    )
    activity_counts.to_csv(output_dir / "b1_activity_counts.csv", index=False)

    presence = (
        df.assign(
            has_record_ir=df["Activity"].eq(ACTIVITY_RECORD_IR),
            has_clear_invoice=df["Activity"].eq(ACTIVITY_CLEAR_INVOICE),
        )
        .groupby("Case ID", as_index=False)
        .agg(
            **{
                "Has Record Invoice Receipt": ("has_record_ir", "max"),
                "Has Clear Invoice": ("has_clear_invoice", "max"),
                "case Spend area text": ("case Spend area text", "first"),
                "case Vendor": ("case Vendor", "first"),
                "case Company": ("case Company", "first"),
                "case Document Type": ("case Document Type", "first"),
            }
        )
    )
    presence.to_csv(output_dir / "b1_case_activity_presence.csv", index=False)


def read_large_input(
    input_path: Path, timestamp_format: str | None, output_dir: Path
) -> tuple[pd.DataFrame, dict[str, object]]:
    header = pd.read_csv(input_path, nrows=0).columns
    ensure_columns(header)

    activity_counts: Counter[str] = Counter()
    presence_parts: list[pd.DataFrame] = []
    relevant_parts: list[pd.DataFrame] = []

    row_count = 0
    valid_timestamp_count = 0
    unique_dates: set[object] = set()
    min_timestamp = pd.NaT
    max_timestamp = pd.NaT
    sample_raw_values: list[str] = []
    sample_seen: set[str] = set()

    for chunk in pd.read_csv(
        input_path,
        usecols=REQUIRED_COLUMNS,
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):
        row_count += len(chunk)
        activity_counts.update(chunk["Activity"].dropna().astype(str))

        raw_timestamps = chunk["Complete Timestamp"].astype("string")
        for value in raw_timestamps.dropna().drop_duplicates().astype(str):
            if value not in sample_seen:
                sample_seen.add(value)
                sample_raw_values.append(value)
            if len(sample_raw_values) >= 20:
                break

        parsed = parse_timestamp_series(raw_timestamps, timestamp_format)
        valid_timestamp_count += int(parsed.notna().sum())
        if parsed.notna().any():
            unique_dates.update(parsed.dropna().dt.date.unique())
            chunk_min = parsed.min()
            chunk_max = parsed.max()
            min_timestamp = (
                chunk_min
                if pd.isna(min_timestamp) or chunk_min < min_timestamp
                else min_timestamp
            )
            max_timestamp = (
                chunk_max
                if pd.isna(max_timestamp) or chunk_max > max_timestamp
                else max_timestamp
            )

        activity_presence = chunk.assign(
            has_record_ir=chunk["Activity"].eq(ACTIVITY_RECORD_IR),
            has_clear_invoice=chunk["Activity"].eq(ACTIVITY_CLEAR_INVOICE),
        )
        presence_parts.append(
            activity_presence.groupby("Case ID", as_index=False).agg(
                **{
                    "Has Record Invoice Receipt": ("has_record_ir", "max"),
                    "Has Clear Invoice": ("has_clear_invoice", "max"),
                    "case Spend area text": ("case Spend area text", "first"),
                    "case Vendor": ("case Vendor", "first"),
                    "case Company": ("case Company", "first"),
                    "case Document Type": ("case Document Type", "first"),
                }
            )
        )

        relevant_mask = chunk["Activity"].isin(
            [ACTIVITY_RECORD_IR, ACTIVITY_CLEAR_INVOICE]
        )
        if relevant_mask.any():
            relevant = chunk.loc[relevant_mask].copy()
            relevant["Parsed Timestamp"] = parsed.loc[relevant.index]
            relevant_parts.append(relevant)

    activity_counts_df = (
        pd.Series(activity_counts, name="Event count")
        .sort_values(ascending=False)
        .rename_axis("Activity")
        .reset_index()
    )
    activity_counts_df.to_csv(output_dir / "b1_activity_counts.csv", index=False)

    presence = pd.concat(presence_parts, ignore_index=True)
    presence = presence.groupby("Case ID", as_index=False).agg(
        **{
            "Has Record Invoice Receipt": ("Has Record Invoice Receipt", "max"),
            "Has Clear Invoice": ("Has Clear Invoice", "max"),
            "case Spend area text": ("case Spend area text", "first"),
            "case Vendor": ("case Vendor", "first"),
            "case Company": ("case Company", "first"),
            "case Document Type": ("case Document Type", "first"),
        }
    )
    presence.to_csv(output_dir / "b1_case_activity_presence.csv", index=False)

    relevant_df = (
        pd.concat(relevant_parts, ignore_index=True)
        if relevant_parts
        else pd.DataFrame(columns=REQUIRED_COLUMNS + ["Parsed Timestamp"])
    )

    quality = {
        "row_count": row_count,
        "valid_timestamp_ratio": valid_timestamp_count / row_count
        if row_count
        else 0.0,
        "unique_dates": len(unique_dates),
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
        "sample_raw_values": sample_raw_values,
    }
    return relevant_df, quality


def calculate_case_durations(df: pd.DataFrame) -> pd.DataFrame:
    relevant = df[
        df["Activity"].isin([ACTIVITY_RECORD_IR, ACTIVITY_CLEAR_INVOICE])
    ].copy()
    relevant = relevant.dropna(subset=["Parsed Timestamp"])
    relevant = relevant.sort_values(["Case ID", "Parsed Timestamp"])

    rows: list[dict[str, object]] = []
    meta_columns = [
        "case Spend area text",
        "case Company",
        "case Document Type",
        "case Vendor",
        "case Spend classification text",
        "case Name",
        "event Cumulative net worth (EUR)",
    ]

    for case_id, group in relevant.groupby("Case ID", sort=False):
        record_times = group.loc[
            group["Activity"].eq(ACTIVITY_RECORD_IR), "Parsed Timestamp"
        ]
        if record_times.empty:
            continue

        start_time = record_times.iloc[0]
        clear_times = group.loc[
            group["Activity"].eq(ACTIVITY_CLEAR_INVOICE), "Parsed Timestamp"
        ]
        clear_after = clear_times[clear_times >= start_time]
        if clear_after.empty:
            continue

        end_time = clear_after.iloc[0]
        duration_days = (end_time - start_time).total_seconds() / 86400
        first_row = group.iloc[0]
        row = {
            "Case ID": case_id,
            "Record Invoice Receipt timestamp": start_time,
            "Clear Invoice timestamp": end_time,
            "Duration days": duration_days,
            "Record IR events in case": int(record_times.shape[0]),
            "Clear Invoice events in case": int(clear_times.shape[0]),
        }
        row.update({col: first_row.get(col) for col in meta_columns})
        rows.append(row)

    return pd.DataFrame(rows)


def summarise_group(
    df: pd.DataFrame, group_columns: list[str], threshold_days: float
) -> pd.DataFrame:
    return (
        df.groupby(group_columns, dropna=False)
        .agg(
            cases=("Case ID", "nunique"),
            slow_cases=("Is over threshold", "sum"),
            mean_duration_days=("Duration days", "mean"),
            median_duration_days=("Duration days", "median"),
            p90_duration_days=("Duration days", lambda s: s.quantile(0.90)),
            max_duration_days=("Duration days", "max"),
        )
        .reset_index()
        .assign(
            slow_case_rate=lambda x: x["slow_cases"] / x["cases"],
            threshold_days=threshold_days,
        )
        .sort_values(
            ["slow_cases", "mean_duration_days", "cases"],
            ascending=[False, False, False],
        )
    )


def write_duration_outputs(
    case_durations: pd.DataFrame, output_dir: Path, threshold_days: float
) -> None:
    case_durations = case_durations.copy()
    case_durations["Is over threshold"] = (
        case_durations["Duration days"] > threshold_days
    )

    case_durations.to_csv(output_dir / "b1_case_durations.csv", index=False)
    case_durations.loc[case_durations["Is over threshold"]].sort_values(
        "Duration days", ascending=False
    ).to_csv(output_dir / "b1_cases_over_threshold.csv", index=False)

    summarise_group(
        case_durations, ["case Spend area text"], threshold_days
    ).to_csv(output_dir / "b1_summary_by_spend_area.csv", index=False)

    summarise_group(case_durations, ["case Vendor"], threshold_days).to_csv(
        output_dir / "b1_summary_by_vendor.csv", index=False
    )

    summarise_group(
        case_durations,
        ["case Spend area text", "case Vendor"],
        threshold_days,
    ).to_csv(output_dir / "b1_summary_by_spend_area_vendor.csv", index=False)

    total_cases = case_durations["Case ID"].nunique()
    slow_cases = int(case_durations["Is over threshold"].sum())
    mean_duration = case_durations["Duration days"].mean()
    median_duration = case_durations["Duration days"].median()
    p90_duration = case_durations["Duration days"].quantile(0.90)

    notes = f"""# B1 Bottleneck Analysis Notes

Problem: Bottleneck from `Record Invoice Receipt` to `Clear Invoice`.

Threshold for slow cases: {threshold_days:g} days.

## Overall results

- Cases with both activities in order: {total_cases:,}
- Cases over threshold: {slow_cases:,}
- Slow case rate: {slow_cases / total_cases:.2%}
- Mean duration: {mean_duration:.2f} days
- Median duration: {median_duration:.2f} days
- 90th percentile duration: {p90_duration:.2f} days

## Output files

- `b1_case_durations.csv`: case-level duration from Record Invoice Receipt to Clear Invoice.
- `b1_cases_over_threshold.csv`: cases above the threshold.
- `b1_summary_by_spend_area.csv`: where slow cases concentrate by spend area.
- `b1_summary_by_vendor.csv`: where slow cases concentrate by vendor.
- `b1_summary_by_spend_area_vendor.csv`: combined spend area/vendor ranking.
- `b1_activity_counts.csv`: activity frequency check.
"""
    (output_dir / "b1_method_notes.md").write_text(notes, encoding="utf-8")


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading required columns from: {input_path}")
    df, quality = read_large_input(input_path, args.timestamp_format, output_dir)
    if not timestamp_is_usable(quality):
        write_timestamp_quality_report(output_dir, quality, input_path)
        print("Timestamp column is not usable for duration analysis.")
        print(f"Quality report written to: {output_dir / 'b1_timestamp_quality_report.md'}")
        print("Basic activity/presence outputs were still created.")
        return

    case_durations = calculate_case_durations(df)
    if case_durations.empty:
        raise ValueError(
            "No cases had Record Invoice Receipt followed by Clear Invoice."
        )

    write_duration_outputs(case_durations, output_dir, args.threshold_days)
    print(f"B1 outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
