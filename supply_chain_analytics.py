"""
supply_chain_analytics.py
=========================
Supply Chain Optimisation Capstone — UK Multi-Warehouse Operations
Author : [Your Name]
Date   : March 2025
Stack  : Python · pandas · NumPy · scipy · matplotlib

Key Outputs
-----------
1. Auto-generated 52-week demand dataset (12 warehouses × 15 SKUs)
2. Inventory health classification (Critical / Low / Healthy / Excess)
3. Excess inventory identification and £ quantification
4. EOQ-based reorder point calculation with safety stock
5. Weekly automated reorder recommendation report
6. Visualisations saved to /outputs/
"""

import pandas as pd
import numpy as np
from scipy.stats import norm
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from datetime import datetime, timedelta
import warnings, os

warnings.filterwarnings("ignore")
np.random.seed(42)
os.makedirs("outputs", exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 1. MASTER DATA DEFINITIONS
# ─────────────────────────────────────────────────────────────

WAREHOUSES = {
    "WH01": ("Manchester",    "North"),
    "WH02": ("Birmingham",    "Midlands"),
    "WH03": ("London-E",      "South-East"),
    "WH04": ("London-W",      "South-East"),
    "WH05": ("Bristol",       "South-West"),
    "WH06": ("Leeds",         "North"),
    "WH07": ("Glasgow",       "Scotland"),
    "WH08": ("Edinburgh",     "Scotland"),
    "WH09": ("Cardiff",       "Wales"),
    "WH10": ("Sheffield",     "North"),
    "WH11": ("Nottingham",    "Midlands"),
    "WH12": ("Southampton",   "South"),
}

# product_id: (name, category, unit_cost, base_weekly_demand)
PRODUCTS = {
    "P001": ("Widget A",       "Electronics",   12.50,  150),
    "P002": ("Widget B",       "Electronics",   18.75,  200),
    "P003": ("Gadget Pro",     "Electronics",   45.00,  300),
    "P004": ("Gadget Lite",    "Electronics",   22.00,  250),
    "P005": ("Cable Pack",     "Accessories",    6.00,   80),
    "P006": ("Mounting Kit",   "Accessories",    9.50,  100),
    "P007": ("Power Bank",     "Electronics",   35.00,  275),
    "P008": ("Sensor Unit",    "Industrial",    88.00,  500),
    "P009": ("Control Board",  "Industrial",   120.00,  600),
    "P010": ("Relay Switch",   "Industrial",    55.00,  400),
    "P011": ("LED Panel",      "Lighting",      28.00,  200),
    "P012": ("Driver Module",  "Lighting",      42.00,  280),
    "P013": ("Fuse Box",       "Industrial",    75.00,  450),
    "P014": ("Terminal Block", "Industrial",    18.00,  150),
    "P015": ("Junction Box",   "Industrial",    32.00,  220),
}

TODAY      = datetime(2025, 3, 24)
DATE_RANGE = pd.date_range(end=TODAY, periods=52, freq="W-MON")

# Service level → z-score (for safety stock calculation)
SERVICE_LEVEL   = 0.95
Z_SCORE         = norm.ppf(SERVICE_LEVEL)   # ≈ 1.645
HOLDING_COST_PC = 0.20                      # 20% of unit cost per year
ORDER_COST      = 50.00                     # £50 fixed cost per order

# ─────────────────────────────────────────────────────────────
# 2. GENERATE DEMAND DATASET
# ─────────────────────────────────────────────────────────────

def build_demand_data() -> pd.DataFrame:
    """
    Simulate 52 weeks of weekly demand per warehouse × SKU.
    Incorporates seasonality, upward trend, and random noise.
    """
    rows = []
    for wh_id, (city, region) in WAREHOUSES.items():
        for prod_id, (name, cat, unit_cost, base) in PRODUCTS.items():
            # Seasonal wave (random phase per SKU)
            seasonal = np.sin(
                np.linspace(0, 2 * np.pi, 52) + np.random.uniform(0, np.pi)
            ) * 0.25 + 1.0

            # Mild growth trend over the year
            trend = np.linspace(0.85, 1.15, 52)

            # Gaussian noise
            noise = np.random.normal(1.0, 0.12, 52)

            demand_series = (base * seasonal * trend * noise).clip(0).astype(int)

            for i, week in enumerate(DATE_RANGE):
                rows.append({
                    "week":           week,
                    "warehouse_id":   wh_id,
                    "city":           city,
                    "region":         region,
                    "product_id":     prod_id,
                    "product_name":   name,
                    "category":       cat,
                    "unit_cost":      unit_cost,
                    "weekly_demand":  int(demand_series[i]),
                })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# 3. INVENTORY SNAPSHOT (current stock on hand)
# ─────────────────────────────────────────────────────────────

def build_inventory_snapshot(demand_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-SKU per-warehouse metrics:
    - Reorder point  = lead-time demand + safety stock (z × σ_demand × √lead_time)
    - EOQ            = sqrt(2 × D × S / H)
    - Excess units   = max(0, SOH − 3 × reorder_point)
    """
    # Aggregate mean / std weekly demand
    agg = (
        demand_df.groupby(["warehouse_id", "product_id"])["weekly_demand"]
        .agg(["mean", "std"])
        .reset_index()
        .rename(columns={"mean": "avg_weekly", "std": "std_weekly"})
    )

    rows = []
    for _, row in agg.iterrows():
        wh_id      = row["warehouse_id"]
        prod_id    = row["product_id"]
        name, cat, unit_cost, _ = PRODUCTS[prod_id]
        avg_weekly = row["avg_weekly"]
        std_weekly = row["std_weekly"]

        # Lead time (random per combination, simulating supplier variability)
        lead_time  = np.random.randint(3, 14)

        # Safety stock: z × σ_demand × sqrt(lead_time_weeks)
        lead_time_weeks = lead_time / 7
        safety_stock    = Z_SCORE * std_weekly * np.sqrt(lead_time_weeks)

        # Reorder point = lead-time demand + safety stock
        reorder_point   = int(avg_weekly * lead_time_weeks + safety_stock)

        # Economic Order Quantity: sqrt(2DS/H)
        annual_demand   = avg_weekly * 52
        holding_cost    = unit_cost * HOLDING_COST_PC
        eoq             = int(np.sqrt(2 * annual_demand * ORDER_COST / holding_cost))
        reorder_qty     = max(eoq, int(avg_weekly * 2))  # at least 2 weeks supply

        # Simulate current stock (some deliberately over / under stocked)
        multiplier = np.random.choice(
            [0.5, 1.0, 1.5, 2.5, 4.0, 6.0],
            p=[0.05, 0.25, 0.30, 0.20, 0.12, 0.08]
        )
        stock_on_hand = int(avg_weekly * multiplier * np.random.uniform(0.9, 1.1))

        rows.append({
            "warehouse_id":    wh_id,
            "city":            WAREHOUSES[wh_id][0],
            "region":          WAREHOUSES[wh_id][1],
            "product_id":      prod_id,
            "product_name":    name,
            "category":        cat,
            "unit_cost":       unit_cost,
            "stock_on_hand":   stock_on_hand,
            "avg_weekly":      round(avg_weekly, 2),
            "std_weekly":      round(std_weekly, 2),
            "lead_time_days":  lead_time,
            "safety_stock":    int(safety_stock),
            "reorder_point":   reorder_point,
            "reorder_qty":     reorder_qty,
        })

    df = pd.DataFrame(rows)
    df["stock_value"]    = df["stock_on_hand"] * df["unit_cost"]
    df["weeks_of_stock"] = df["stock_on_hand"] / df["avg_weekly"].replace(0, np.nan)
    df["excess_units"]   = (df["stock_on_hand"] - df["reorder_point"] * 3).clip(0).astype(int)
    df["excess_value"]   = df["excess_units"] * df["unit_cost"]

    df["status"] = pd.cut(
        df["weeks_of_stock"],
        bins=[-np.inf, 1, 2, 6, np.inf],
        labels=["Critical", "Low", "Healthy", "Excess"],
    )
    return df


# ─────────────────────────────────────────────────────────────
# 4. REORDER RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────

def build_reorder_report(inv_df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag all SKU–warehouse combinations where stock ≤ reorder point.
    Output a ranked reorder queue with total cost.
    """
    reorder = inv_df[inv_df["stock_on_hand"] <= inv_df["reorder_point"]].copy()
    reorder["reorder_cost"] = reorder["reorder_qty"] * reorder["unit_cost"]
    reorder["urgency"] = np.where(
        reorder["lead_time_days"] >= 12, "URGENT",
        np.where(reorder["lead_time_days"] >= 9, "High", "Normal")
    )
    return reorder.sort_values("reorder_cost", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# 5. KPI SUMMARY
# ─────────────────────────────────────────────────────────────

def print_kpis(inv_df: pd.DataFrame, reorder_df: pd.DataFrame):
    sep = "─" * 56
    print(f"\n{'═'*56}")
    print(f"  SupplyIQ · UK Operations · Week 12, 2025")
    print(f"{'═'*56}")
    print(f"  Total Stock Value        : £{inv_df['stock_value'].sum():>12,.0f}")
    print(f"  Excess Inventory Value   : £{inv_df['excess_value'].sum():>12,.0f}")
    print(f"  SKU–Sites Critical       :  {(inv_df['status']=='Critical').sum():>12}")
    print(f"  SKU–Sites Excess         :  {(inv_df['status']=='Excess').sum():>12}")
    print(f"  Reorder Lines This Week  :  {len(reorder_df):>12}")
    print(f"  Total Reorder Spend      : £{reorder_df['reorder_cost'].sum():>12,.0f}")
    print(f"{sep}\n")

    print("  Top 5 Excess Positions:")
    top = inv_df.nlargest(5, "excess_value")[
        ["city", "product_name", "excess_units", "excess_value", "weeks_of_stock"]
    ]
    for _, r in top.iterrows():
        print(f"    {r['city']:<14} {r['product_name']:<16} "
              f"{r['excess_units']:>5} units  £{r['excess_value']:>9,.0f}  "
              f"({r['weeks_of_stock']:.1f}w cover)")

    print(f"\n  Top 5 Reorder Lines:")
    for _, r in reorder_df.head(5).iterrows():
        print(f"    {r['city']:<14} {r['product_name']:<16} "
              f"Qty {r['reorder_qty']:>5}  £{r['reorder_cost']:>9,.0f}  "
              f"[{r['urgency']}]")
    print()


# ─────────────────────────────────────────────────────────────
# 6. VISUALISATIONS
# ─────────────────────────────────────────────────────────────

DARK   = "#0a0c0f"
SURF   = "#111418"
BORDER = "#1e2229"
TEXT   = "#e8eaf0"
MUTED  = "#6b7280"
ACCENT = "#f0c040"
TEAL   = "#3ecfb2"
RED    = "#f05252"
ORANGE = "#f0864a"
BLUE   = "#5b9cf0"
GREEN  = "#52c07a"

plt.rcParams.update({
    "figure.facecolor": DARK, "axes.facecolor": SURF,
    "axes.edgecolor": BORDER, "axes.labelcolor": TEXT,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": TEXT, "grid.color": BORDER,
    "grid.linestyle": "--", "grid.linewidth": 0.5,
    "font.family": "monospace", "font.size": 9,
})


def plot_demand_trend(demand_df: pd.DataFrame):
    weekly = (
        demand_df.groupby("week")
        .apply(lambda x: (x["weekly_demand"] * x["unit_cost"]).sum())
        .reset_index(name="revenue")
    )
    weekly["week_label"] = weekly["week"].dt.strftime("%b %d")

    fig, ax = plt.subplots(figsize=(12, 4), facecolor=DARK)
    ax.set_facecolor(SURF)
    ax.plot(weekly["week_label"], weekly["revenue"], color=ACCENT, linewidth=2)
    ax.fill_between(weekly["week_label"], weekly["revenue"],
                    alpha=0.15, color=ACCENT)
    ax.set_title("Weekly Revenue — All Warehouses (52 Weeks)", color=TEXT, fontsize=11, pad=12)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"£{x/1e6:.1f}M"))
    ax.set_xlabel("Week", color=MUTED)
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=45, ha="right", fontsize=7)
    plt.tight_layout()
    plt.savefig("outputs/01_demand_trend.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  ✓ Saved: outputs/01_demand_trend.png")


def plot_excess_by_warehouse(inv_df: pd.DataFrame):
    exc = (
        inv_df.groupby("city")["excess_value"]
        .sum()
        .sort_values(ascending=True)
    )
    colours = [RED if v > 150_000 else ORANGE if v > 50_000 else BLUE for v in exc.values]

    fig, ax = plt.subplots(figsize=(10, 6), facecolor=DARK)
    ax.set_facecolor(SURF)
    bars = ax.barh(exc.index, exc.values, color=colours, height=0.6, edgecolor="none")
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"£{x/1000:.0f}k"))
    ax.set_title("Excess Inventory by Warehouse", color=TEXT, fontsize=11, pad=12)
    ax.set_xlabel("Excess Stock Value (£)", color=MUTED)
    ax.grid(axis="x", alpha=0.3)
    for bar, val in zip(bars, exc.values):
        ax.text(val + 1500, bar.get_y() + bar.get_height() / 2,
                f"£{val:,.0f}", va="center", color=MUTED, fontsize=8)
    plt.tight_layout()
    plt.savefig("outputs/02_excess_by_warehouse.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  ✓ Saved: outputs/02_excess_by_warehouse.png")


def plot_status_breakdown(inv_df: pd.DataFrame):
    counts = inv_df["status"].value_counts()
    colours_map = {"Critical": RED, "Low": ORANGE, "Healthy": GREEN, "Excess": BLUE}
    labels = ["Critical", "Low", "Healthy", "Excess"]
    vals   = [counts.get(l, 0) for l in labels]
    cols   = [colours_map[l] for l in labels]

    fig, ax = plt.subplots(figsize=(5, 5), facecolor=DARK)
    wedges, texts, autotexts = ax.pie(
        vals, labels=labels, colors=cols, autopct="%1.0f%%",
        startangle=90, pctdistance=0.75,
        wedgeprops=dict(width=0.55, edgecolor=DARK, linewidth=2)
    )
    for t in texts:    t.set_color(MUTED);  t.set_fontsize(9)
    for t in autotexts: t.set_color(TEXT);  t.set_fontsize(8)
    ax.set_title("Inventory Health (180 SKU–Sites)", color=TEXT, fontsize=10, pad=12)
    plt.tight_layout()
    plt.savefig("outputs/03_status_donut.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  ✓ Saved: outputs/03_status_donut.png")


def plot_reorder_heatmap(reorder_df: pd.DataFrame):
    pivot = (
        reorder_df.pivot_table(
            index="product_name", columns="city",
            values="reorder_cost", aggfunc="sum", fill_value=0
        )
    )
    fig, ax = plt.subplots(figsize=(14, 6), facecolor=DARK)
    ax.set_facecolor(SURF)
    im = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right", fontsize=8, color=MUTED)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=8, color=MUTED)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if v > 0:
                ax.text(j, i, f"£{v/1000:.0f}k", ha="center", va="center",
                        fontsize=7, color="black" if v > 150_000 else TEXT)
    ax.set_title("Reorder Cost Heatmap — SKU × Warehouse", color=TEXT, fontsize=11, pad=12)
    plt.colorbar(im, ax=ax, format=lambda x, _: f"£{x/1000:.0f}k")
    plt.tight_layout()
    plt.savefig("outputs/04_reorder_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  ✓ Saved: outputs/04_reorder_heatmap.png")


# ─────────────────────────────────────────────────────────────
# 7. EXPORT REPORTS
# ─────────────────────────────────────────────────────────────

def export_reports(inv_df: pd.DataFrame, reorder_df: pd.DataFrame, demand_df: pd.DataFrame):
    inv_df.to_csv("outputs/inventory_snapshot.csv", index=False)
    reorder_df.to_csv("outputs/reorder_recommendations.csv", index=False)
    demand_df.to_csv("outputs/demand_weekly.csv", index=False)

    # Summary Excel
    with pd.ExcelWriter("outputs/supply_chain_report.xlsx", engine="openpyxl") as writer:
        inv_df.to_excel(writer, sheet_name="Inventory Snapshot", index=False)
        reorder_df.to_excel(writer, sheet_name="Reorder Queue", index=False)
        demand_df.tail(12 * len(WAREHOUSES) * len(PRODUCTS)).to_excel(
            writer, sheet_name="12-Week Demand", index=False
        )
    print("  ✓ Saved: outputs/supply_chain_report.xlsx")


# ─────────────────────────────────────────────────────────────
# 8. MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n[1/5] Building 52-week demand dataset …")
    demand_df = build_demand_data()
    print(f"       {len(demand_df):,} rows · {demand_df['warehouse_id'].nunique()} warehouses · "
          f"{demand_df['product_id'].nunique()} SKUs")

    print("[2/5] Computing inventory snapshot & EOQ reorder points …")
    inv_df = build_inventory_snapshot(demand_df)
    print(f"       Total stock value   : £{inv_df['stock_value'].sum():,.0f}")
    print(f"       Total excess value  : £{inv_df['excess_value'].sum():,.0f}")

    print("[3/5] Generating reorder recommendations …")
    reorder_df = build_reorder_report(inv_df)
    print(f"       {len(reorder_df)} reorder lines · £{reorder_df['reorder_cost'].sum():,.0f} total spend")

    print("[4/5] Rendering visualisations …")
    plot_demand_trend(demand_df)
    plot_excess_by_warehouse(inv_df)
    plot_status_breakdown(inv_df)
    plot_reorder_heatmap(reorder_df)

    print("[5/5] Exporting reports …")
    export_reports(inv_df, reorder_df, demand_df)

    print_kpis(inv_df, reorder_df)
    print("  Pipeline complete. All outputs in ./outputs/\n")
