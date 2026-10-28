"""
chart_generator.py - Matplotlib Visualization Engine
Generates publication-quality line and bar charts, encoded as Base64 PNGs
for seamless web embedding and reporting.
"""

import io
import base64
from typing import Dict, Any, List
import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend safe for servers
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


# Modern aesthetic styling
CHART_THEME = {
    "bg_color": "#ffffff",
    "text_color": "#1e293b",
    "grid_color": "#f1f5f9",
    "primary": "#3b82f6",     # Blue
    "secondary": "#10b981",   # Emerald
    "accent": "#8b5cf6",      # Purple
    "warning": "#f59e0b",     # Amber
    "palette": ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899", "#06b6d4", "#f97316", "#64748b"]
}


def _fig_to_base64(fig: plt.Figure) -> str:
    """Converts a Matplotlib figure into a base64 encoded PNG data URI string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=160, facecolor=CHART_THEME["bg_color"])
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{img_b64}"


def generate_monthly_trend_chart(monthly_trends: List[Dict[str, Any]]) -> str:
    """Generates dual-axis Monthly Trend Chart (Revenue Line & Units Sold Bar)."""
    if not monthly_trends:
        return ""

    months = [m["month"] for m in monthly_trends]
    revenues = [m["total_revenue"] for m in monthly_trends]
    units = [m["units_sold"] for m in monthly_trends]

    fig, ax1 = plt.subplots(figsize=(9, 4.2), facecolor=CHART_THEME["bg_color"])
    ax1.set_facecolor(CHART_THEME["bg_color"])

    x = np.arange(len(months))
    width = 0.38

    # Primary axis: Revenue (Bar or Line)
    color_bar = CHART_THEME["primary"]
    bars = ax1.bar(x, revenues, width=width, color=color_bar, alpha=0.85, label="Revenue ($)", zorder=2)
    ax1.set_xlabel("Sales Month", fontsize=11, fontweight="600", color=CHART_THEME["text_color"], labelpad=10)
    ax1.set_ylabel("Total Revenue ($)", fontsize=11, fontweight="600", color=color_bar, labelpad=10)
    ax1.tick_params(axis="y", labelcolor=color_bar)
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"${y:,.0f}"))
    ax1.grid(axis="y", linestyle="--", alpha=0.6, color=CHART_THEME["grid_color"], zorder=1)

    # Secondary axis: Units Sold (Line with markers)
    ax2 = ax1.twinx()
    color_line = CHART_THEME["secondary"]
    ax2.plot(x, units, color=color_line, marker="o", linewidth=2.5, markersize=7, label="Units Sold", zorder=3)
    ax2.set_ylabel("Units Sold", fontsize=11, fontweight="600", color=color_line, labelpad=10)
    ax2.tick_params(axis="y", labelcolor=color_line)
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{int(y):,}"))

    # X-Ticks
    ax1.set_xticks(x)
    ax1.set_xticklabels(months, rotation=35, ha="right", fontsize=9, color=CHART_THEME["text_color"])

    # Spine styling
    for spine in ax1.spines.values():
        spine.set_color("#cbd5e1")
    ax2.spines["top"].set_visible(False)
    ax1.spines["top"].set_visible(False)

    plt.title("Monthly Revenue & Volume Sales Trends", fontsize=13, fontweight="bold", pad=15, color=CHART_THEME["text_color"])
    
    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", framealpha=0.9, fontsize=9)

    fig.tight_layout()
    return _fig_to_base64(fig)


def generate_top_products_chart(product_rankings: List[Dict[str, Any]], top_n: int = 7) -> str:
    """Generates Horizontal Bar Chart of top-performing products by revenue."""
    if not product_rankings:
        return ""

    top_items = product_rankings[:top_n]
    # Reverse order so #1 product is at top of vertical axis
    top_items = top_items[::-1]

    names = [p["product_name"][:20] + ("..." if len(p["product_name"]) > 20 else "") for p in top_items]
    revenues = [p["total_revenue"] for p in top_items]

    fig, ax = plt.subplots(figsize=(8.5, 4.2), facecolor=CHART_THEME["bg_color"])
    ax.set_facecolor(CHART_THEME["bg_color"])

    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, revenues, color=CHART_THEME["accent"], height=0.55, alpha=0.9, zorder=2)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=10, color=CHART_THEME["text_color"], fontweight="500")
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.set_xlabel("Total Revenue ($)", fontsize=11, fontweight="600", color=CHART_THEME["text_color"], labelpad=8)
    ax.grid(axis="x", linestyle="--", alpha=0.6, color=CHART_THEME["grid_color"], zorder=1)

    # Value labels at end of bars
    for bar in bars:
        w = bar.get_width()
        ax.text(w + (max(revenues) * 0.015), bar.get_y() + bar.get_height() / 2,
                f"${w:,.2f}", va="center", ha="left", fontsize=9, fontweight="bold", color="#334155")

    for spine in ax.spines.values():
        spine.set_color("#cbd5e1")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.title(f"Top {len(top_items)} Products by Revenue Performance", fontsize=13, fontweight="bold", pad=15, color=CHART_THEME["text_color"])
    fig.tight_layout()
    return _fig_to_base64(fig)


def generate_category_donut_chart(category_breakdown: List[Dict[str, Any]]) -> str:
    """Generates Donut Chart of revenue market share by product category."""
    if not category_breakdown:
        return ""

    cats = [c["category"] for c in category_breakdown]
    revs = [c["total_revenue"] for c in category_breakdown]

    fig, ax = plt.subplots(figsize=(6, 4.2), facecolor=CHART_THEME["bg_color"])
    ax.set_facecolor(CHART_THEME["bg_color"])

    colors = CHART_THEME["palette"][:len(cats)]
    wedges, texts, autotexts = ax.pie(
        revs,
        labels=cats,
        autopct="%1.1f%%",
        startangle=140,
        colors=colors,
        wedgeprops=dict(width=0.45, edgecolor="w", linewidth=2),
        pctdistance=0.75
    )

    for text in texts:
        text.set_color(CHART_THEME["text_color"])
        text.set_fontsize(9)
        text.set_fontweight("500")
    for autotext in autotexts:
        autotext.set_color("#ffffff")
        autotext.set_fontsize(8.5)
        autotext.set_fontweight("bold")

    plt.title("Revenue Share by Category", fontsize=13, fontweight="bold", pad=15, color=CHART_THEME["text_color"])
    fig.tight_layout()
    return _fig_to_base64(fig)


def generate_regional_bar_chart(regional_breakdown: List[Dict[str, Any]]) -> str:
    """Generates Vertical Bar Chart of regional sales distribution."""
    if not regional_breakdown:
        return ""

    regions = [r["region"] for r in regional_breakdown]
    revs = [r["total_revenue"] for r in regional_breakdown]

    fig, ax = plt.subplots(figsize=(7, 4.2), facecolor=CHART_THEME["bg_color"])
    ax.set_facecolor(CHART_THEME["bg_color"])

    x = np.arange(len(regions))
    bars = ax.bar(x, revs, width=0.48, color=CHART_THEME["warning"], alpha=0.9, zorder=2)

    ax.set_xticks(x)
    ax.set_xticklabels(regions, fontsize=10, color=CHART_THEME["text_color"], fontweight="500")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"${y:,.0f}"))
    ax.set_ylabel("Revenue ($)", fontsize=11, fontweight="600", color=CHART_THEME["text_color"], labelpad=8)
    ax.grid(axis="y", linestyle="--", alpha=0.6, color=CHART_THEME["grid_color"], zorder=1)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + (max(revs) * 0.02),
                f"${h:,.0f}", ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#334155")

    for spine in ax.spines.values():
        spine.set_color("#cbd5e1")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.title("Sales by Geographic Region", fontsize=13, fontweight="bold", pad=15, color=CHART_THEME["text_color"])
    fig.tight_layout()
    return _fig_to_base64(fig)


def render_all_charts(analytics_data: Dict[str, Any]) -> Dict[str, str]:
    """Renders all Matplotlib charts and returns dictionary of base64 data URIs."""
    return {
        "monthly_trend": generate_monthly_trend_chart(analytics_data.get("monthly_trends", [])),
        "top_products": generate_top_products_chart(analytics_data.get("product_rankings", [])),
        "category_donut": generate_category_donut_chart(analytics_data.get("category_breakdown", [])),
        "regional_sales": generate_regional_bar_chart(analytics_data.get("regional_breakdown", []))
    }
