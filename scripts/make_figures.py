"""Draw the README figures from the summary tables of the case-study report.

The numbers below are copied from the report's Tables 3-5 (computed by
analyze_b1_bottleneck.py on the BPI Challenge 2019 log). No raw data is needed
or shipped: run `python scripts/make_figures.py` to regenerate `figures/`.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

OUT = Path(__file__).resolve().parent.parent / "figures"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3de"
ACCENT = "#2a78d6"
NEUTRAL = "#b9b8b1"

OVERALL_SLOW_RATE = 25.37  # 46,465 of 183,161 valid cases exceed 70 days
NO_EXCEPTION_RATE = 22.57  # cases without exception or rework activities

# Table 4: spend area -> (slow cases, slow-case rate %)
SPEND_AREAS = {
    "Packaging": (37_435, 48.87),
    "Additives": (2_847, 23.01),
    "Sales": (2_158, 3.89),
    "Trading & End Products": (1_573, 9.39),
    "Latex & Monomers": (645, 20.96),
}
# Table 5: top five vendors by slow-case volume -> (slow cases, slow-case rate %)
VENDORS = {
    "vendorID_0136": (9_895, 93.37),
    "vendorID_0120": (8_481, 80.73),
    "vendorID_0103": (3_809, 98.81),
    "vendorID_0182": (3_600, 74.35),
    "vendorID_0104": (3_189, 44.59),
}
# Table 3: exception / rework activity -> slow-case rate %
EXCEPTIONS = {
    "Remove Payment Block": 33.24,
    "Change Quantity": 28.69,
    "Change Price": 22.40,
    "Cancel Invoice Receipt": 22.40,
    "Vendor Creates Debit Memo": 20.37,
}


def _axes(title: str, subtitle: str, height: float):
    fig, ax = plt.subplots(figsize=(8, height), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, length=0, labelsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.text(0.02, 0.97, title, fontsize=12, fontweight="bold", color=INK, va="top")
    fig.text(0.02, 0.97 - 0.33 / height, subtitle, fontsize=9, color=INK_2, va="top")
    return fig, ax


def _save(fig, name: str) -> None:
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.75 / fig.get_figheight()))
    fig.savefig(OUT / name, facecolor=SURFACE)
    plt.close(fig)
    print("wrote", OUT / name)


def spend_area() -> None:
    names = list(SPEND_AREAS)[::-1]
    slow = [SPEND_AREAS[n][0] for n in names]
    fig, ax = _axes(
        "80.6% of slow invoices sit in one spend area",
        "Cases taking > 70 days from Record Invoice Receipt to Clear Invoice, by spend area",
        3.4,
    )
    colors = [ACCENT if n == "Packaging" else NEUTRAL for n in names]
    ax.barh(names, slow, color=colors, height=0.6, edgecolor=SURFACE, linewidth=2)
    for y, v in enumerate(slow):
        ax.text(v + 400, y, f"{v:,}  ({v / 46_465:.1%})", va="center", fontsize=9, color=INK_2)
    ax.set_xlim(0, max(slow) * 1.3)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xlabel("Slow cases", color=INK_2, fontsize=9)
    ax.tick_params(axis="y", colors=INK)
    _save(fig, "slow_cases_by_spend_area.png")


def vendors() -> None:
    names = list(VENDORS)[::-1]
    rate = [VENDORS[n][1] for n in names]
    fig, ax = _axes(
        "Top vendors clear most invoices late",
        "Slow-case rate of the five vendors with the most slow cases (all in Packaging)",
        3.4,
    )
    top3 = {"vendorID_0136", "vendorID_0120", "vendorID_0103"}
    colors = [ACCENT if n in top3 else NEUTRAL for n in names]
    ax.barh(names, rate, color=colors, height=0.6, edgecolor=SURFACE, linewidth=2)
    for y, (n, v) in enumerate(zip(names, rate)):
        ax.text(v + 1, y, f"{v:.1f}%  ({VENDORS[n][0]:,} slow)", va="center", fontsize=9, color=INK_2)
    ax.axvline(OVERALL_SLOW_RATE, color=INK_2, linewidth=1, linestyle="--")
    ax.text(OVERALL_SLOW_RATE + 1, len(names) - 0.45, "all cases 25.4%", fontsize=8, color=INK_2)
    ax.set_xlim(0, 130)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("Slow-case rate (%)  ·  highlighted: top 3 = 47.8% of all slow cases", color=INK_2, fontsize=9)
    ax.tick_params(axis="y", colors=INK)
    _save(fig, "slow_rate_top_vendors.png")


def exceptions() -> None:
    names = list(EXCEPTIONS)[::-1]
    rate = [EXCEPTIONS[n] for n in names]
    fig, ax = _axes(
        "Payment blocks go with slower clearing",
        "Slow-case rate of cases containing each exception activity (association, not cause)",
        3.4,
    )
    colors = [ACCENT if n == "Remove Payment Block" else NEUTRAL for n in names]
    ax.barh(names, rate, color=colors, height=0.6, edgecolor=SURFACE, linewidth=2)
    for y, v in enumerate(rate):
        ax.text(v + 0.5, y, f"{v:.1f}%", va="center", fontsize=9, color=INK_2,
                bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1})
    ax.axvline(NO_EXCEPTION_RATE, color=INK_2, linewidth=1, linestyle="--")
    ax.text(NO_EXCEPTION_RATE + 0.5, len(names) - 0.45, "no exceptions 22.6%", fontsize=8, color=INK_2)
    ax.set_xlim(0, 42)
    ax.set_xlabel("Slow-case rate (%)", color=INK_2, fontsize=9)
    ax.tick_params(axis="y", colors=INK)
    _save(fig, "slow_rate_by_exception.png")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    spend_area()
    vendors()
    exceptions()
