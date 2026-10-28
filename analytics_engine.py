"""
analytics_engine.py - High-Performance Sales Data Analysis using Pandas & NumPy
Computes revenue, quantities sold, product performance rankings,
month-wise trend aggregations, and NumPy-powered growth calculations.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class SalesAnalyticsEngine:
    def __init__(self, sales_df: pd.DataFrame):
        self.raw_df = sales_df.copy() if sales_df is not None else pd.DataFrame()
        self.df = self._clean_and_prepare(self.raw_df)

    def _clean_and_prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cleans and standardizes the DataFrame for analysis."""
        if df.empty:
            return pd.DataFrame(columns=[
                "sale_id", "product_id", "product_name", "category",
                "sale_date", "quantity", "unit_price", "total_revenue", "region"
            ])

        # Type conversion & fill missing
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
        df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0.0)
        
        # Calculate/recalculate total_revenue using NumPy vectorization if missing or 0
        computed_revenue = np.round(df["quantity"].to_numpy() * df["unit_price"].to_numpy(), 2)
        if "total_revenue" not in df.columns or df["total_revenue"].isnull().all():
            df["total_revenue"] = computed_revenue
        else:
            rev_series = pd.to_numeric(df["total_revenue"], errors="coerce")
            df["total_revenue"] = rev_series.fillna(pd.Series(computed_revenue, index=df.index))

        # Datetime processing
        df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
        # Filter out rows with invalid dates if any
        df = df.dropna(subset=["sale_date"]).copy()
        
        df["year_month"] = df["sale_date"].dt.strftime("%Y-%m")
        df["month_name"] = df["sale_date"].dt.strftime("%b %Y")
        df["day_name"] = df["sale_date"].dt.day_name()
        df["quarter"] = df["sale_date"].dt.to_period("Q").astype(str)

        # Standardize strings
        df["product_name"] = df["product_name"].fillna("Unknown Product").astype(str)
        df["category"] = df["category"].fillna("General").astype(str)
        df["region"] = df["region"].fillna("Unknown Region").astype(str)

        return df

    def get_summary_kpis(self) -> Dict[str, Any]:
        """Calculates executive summary KPIs using NumPy & Pandas."""
        if self.df.empty:
            return {
                "total_revenue": 0.0,
                "total_units_sold": 0,
                "total_transactions": 0,
                "average_order_value": 0.0,
                "average_unit_price": 0.0,
                "unique_products": 0,
                "unique_categories": 0,
                "unique_regions": 0,
                "date_range": {"start": None, "end": None},
                "best_month": None,
                "best_product": None
            }

        rev_array = self.df["total_revenue"].to_numpy()
        qty_array = self.df["quantity"].to_numpy()

        total_rev = float(np.sum(rev_array))
        total_qty = int(np.sum(qty_array))
        total_trans = int(len(self.df))
        aov = round(total_rev / total_trans, 2) if total_trans > 0 else 0.0
        avg_price = round(float(np.mean(self.df["unit_price"].to_numpy())), 2)

        min_date = self.df["sale_date"].min().strftime("%Y-%m-%d")
        max_date = self.df["sale_date"].max().strftime("%Y-%m-%d")

        # Peak sales month
        monthly = self.df.groupby("year_month")["total_revenue"].sum()
        best_month_key = monthly.idxmax() if not monthly.empty else "N/A"
        best_month_val = round(float(monthly.max()), 2) if not monthly.empty else 0.0

        # Best product
        prod_perf = self.df.groupby("product_name")["total_revenue"].sum()
        best_prod_name = prod_perf.idxmax() if not prod_perf.empty else "N/A"
        best_prod_rev = round(float(prod_perf.max()), 2) if not prod_perf.empty else 0.0

        return {
            "total_revenue": round(total_rev, 2),
            "total_units_sold": total_qty,
            "total_transactions": total_trans,
            "average_order_value": aov,
            "average_unit_price": avg_price,
            "unique_products": int(self.df["product_id"].nunique()),
            "unique_categories": int(self.df["category"].nunique()),
            "unique_regions": int(self.df["region"].nunique()),
            "date_range": {"start": min_date, "end": max_date},
            "best_month": {"period": best_month_key, "revenue": best_month_val},
            "best_product": {"name": best_prod_name, "revenue": best_prod_rev}
        }

    def get_product_rankings(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Returns top products ranked by revenue, including unit sales and percentage share."""
        if self.df.empty:
            return []

        total_rev = float(np.sum(self.df["total_revenue"].to_numpy()))
        grouped = self.df.groupby(["product_id", "product_name", "category"]).agg(
            total_revenue=("total_revenue", "sum"),
            units_sold=("quantity", "sum"),
            transaction_count=("sale_id", "count"),
            avg_price=("unit_price", "mean")
        ).reset_index()

        grouped = grouped.sort_values(by="total_revenue", ascending=False).head(top_n)

        rankings = []
        for rank, (_, row) in enumerate(grouped.iterrows(), start=1):
            rev = round(float(row["total_revenue"]), 2)
            share = round((rev / total_rev * 100), 2) if total_rev > 0 else 0.0
            rankings.append({
                "rank": rank,
                "product_id": str(row["product_id"]),
                "product_name": str(row["product_name"]),
                "category": str(row["category"]),
                "total_revenue": rev,
                "units_sold": int(row["units_sold"]),
                "transaction_count": int(row["transaction_count"]),
                "avg_price": round(float(row["avg_price"]), 2),
                "revenue_share_pct": share
            })
        return rankings

    def get_monthly_trends(self) -> List[Dict[str, Any]]:
        """
        Returns month-by-month aggregated sales trends with
        NumPy-calculated Month-over-Month (MoM) revenue growth rates.
        """
        if self.df.empty:
            return []

        monthly = self.df.groupby("year_month").agg(
            total_revenue=("total_revenue", "sum"),
            units_sold=("quantity", "sum"),
            order_count=("sale_id", "count")
        ).reset_index().sort_values(by="year_month")

        # Calculate MoM growth percentage using NumPy
        rev_vals = monthly["total_revenue"].to_numpy()
        mom_growth = np.zeros(len(rev_vals))
        if len(rev_vals) > 1:
            # growth = (current - prev) / prev * 100
            prev_vals = rev_vals[:-1]
            curr_vals = rev_vals[1:]
            with np.errstate(divide='ignore', invalid='ignore'):
                growth_rates = np.where(prev_vals != 0, ((curr_vals - prev_vals) / prev_vals) * 100, 0.0)
            mom_growth[1:] = np.nan_to_num(growth_rates, nan=0.0, posinf=0.0, neginf=0.0)

        monthly["mom_growth_pct"] = np.round(mom_growth, 2)

        results = []
        for _, row in monthly.iterrows():
            results.append({
                "month": str(row["year_month"]),
                "total_revenue": round(float(row["total_revenue"]), 2),
                "units_sold": int(row["units_sold"]),
                "order_count": int(row["order_count"]),
                "mom_growth_pct": float(row["mom_growth_pct"])
            })
        return results

    def get_category_breakdown(self) -> List[Dict[str, Any]]:
        """Returns revenue and units sold grouped by product category."""
        if self.df.empty:
            return []

        total_rev = float(np.sum(self.df["total_revenue"].to_numpy()))
        cat_group = self.df.groupby("category").agg(
            total_revenue=("total_revenue", "sum"),
            units_sold=("quantity", "sum"),
            product_count=("product_id", "nunique")
        ).reset_index().sort_values(by="total_revenue", ascending=False)

        results = []
        for _, row in cat_group.iterrows():
            rev = round(float(row["total_revenue"]), 2)
            share = round((rev / total_rev * 100), 2) if total_rev > 0 else 0.0
            results.append({
                "category": str(row["category"]),
                "total_revenue": rev,
                "units_sold": int(row["units_sold"]),
                "product_count": int(row["product_count"]),
                "market_share_pct": share
            })
        return results

    def get_regional_breakdown(self) -> List[Dict[str, Any]]:
        """Returns sales distribution across geographic regions."""
        if self.df.empty:
            return []

        total_rev = float(np.sum(self.df["total_revenue"].to_numpy()))
        reg_group = self.df.groupby("region").agg(
            total_revenue=("total_revenue", "sum"),
            units_sold=("quantity", "sum"),
            order_count=("sale_id", "count")
        ).reset_index().sort_values(by="total_revenue", ascending=False)

        results = []
        for _, row in reg_group.iterrows():
            rev = round(float(row["total_revenue"]), 2)
            share = round((rev / total_rev * 100), 2) if total_rev > 0 else 0.0
            results.append({
                "region": str(row["region"]),
                "total_revenue": rev,
                "units_sold": int(row["units_sold"]),
                "order_count": int(row["order_count"]),
                "share_pct": share
            })
        return results

    def get_day_of_week_trends(self) -> List[Dict[str, Any]]:
        """Returns sales trends by day of the week to identify peak sales periods."""
        if self.df.empty:
            return []

        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        dow_group = self.df.groupby("day_name").agg(
            total_revenue=("total_revenue", "sum"),
            units_sold=("quantity", "sum"),
            order_count=("sale_id", "count")
        ).reindex(days_order).fillna(0).reset_index()

        results = []
        for _, row in dow_group.iterrows():
            results.append({
                "day_name": str(row["day_name"]),
                "total_revenue": round(float(row["total_revenue"]), 2),
                "units_sold": int(row["units_sold"]),
                "order_count": int(row["order_count"])
            })
        return results

    def get_complete_analytics_report(self) -> Dict[str, Any]:
        """Bundles all analytics into a single comprehensive dictionary."""
        return {
            "summary_kpis": self.get_summary_kpis(),
            "product_rankings": self.get_product_rankings(top_n=10),
            "monthly_trends": self.get_monthly_trends(),
            "category_breakdown": self.get_category_breakdown(),
            "regional_breakdown": self.get_regional_breakdown(),
            "day_of_week_trends": self.get_day_of_week_trends()
        }
