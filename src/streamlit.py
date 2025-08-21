# streamlit.py (or dashboard.py)
# Streamlit dashboard with robust UK heatmap + insights
# Reads DB_TABLE/DB_SCHEMA from .env and uses utils.utils.get_db_engine()

import os
import json
import numpy as np
import pandas as pd
import altair as alt
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv
from utils.utils import get_db_engine

# ---------------------- Config ----------------------
load_dotenv()
DB_TABLE  = os.getenv("DB_TABLE")
DB_SCHEMA = os.getenv("DB_SCHEMA", "public")

PAID_STATUSES = {"processing", "completed"}  # adjust to your workflow
st.set_page_config(page_title="DC Freshwater Fish – Orders", layout="wide")

# ---------------------- Data ------------------------
@st.cache_data(ttl=600, show_spinner=False)
def load_orders() -> pd.DataFrame:
    engine = get_db_engine()
    df = pd.read_sql_table(DB_TABLE, con=engine, schema=DB_SCHEMA)

    # Parse dates safely
    for c in ("date_created", "date_modified", "date_paid"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    # Coerce numerics
    for c in ("order_total", "shipping_total", "total_tax", "discount_total"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Coerce lat/lon to numeric (strings/"None" -> NaN)
    for c in ("latitude", "longitude"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Coerce JSONB to Python objects if some rows returned as strings
    def _coerce_json(x):
        if isinstance(x, (list, dict)) or x is None or (isinstance(x, float) and np.isnan(x)):
            return x
        if isinstance(x, str) and x.strip():
            try:
                return json.loads(x)
            except Exception:
                return None
        return None

    if "item_details" in df.columns:
        df["item_details"] = df["item_details"].apply(_coerce_json)
    if "coupon_details" in df.columns:
        df["coupon_details"] = df["coupon_details"].apply(_coerce_json)

    # Fill device_type if missing
    if "device_type" in df.columns:
        df["device_type"] = df["device_type"].fillna("Unknown")

    return df

df = load_orders()
if df.empty:
    st.info("No orders found.")
    st.stop()

# ---------------------- Filters ---------------------
with st.sidebar:
    st.header("Filters")
    if "date_created" in df.columns:
        min_date = pd.to_datetime(df["date_created"].min())
        max_date = pd.to_datetime(df["date_created"].max())
        date_range = st.date_input(
            "Order date range",
            value=(min_date.date(), max_date.date()),
            min_value=min_date.date(),
            max_value=max_date.date(),
        )
    else:
        date_range = (None, None)

    status_opts = sorted(df.get("status", pd.Series(dtype=object)).dropna().unique().tolist())
    default_status = [s for s in status_opts if s in PAID_STATUSES] or status_opts
    status_sel = st.multiselect("Statuses", options=status_opts, default=default_status)

    device_opts = sorted(df.get("device_type", pd.Series(dtype=object)).fillna("Unknown").unique().tolist())
    device_sel = st.multiselect("Devices", options=device_opts, default=device_opts)

    include_shipping = st.toggle("KPIs include shipping in revenue", value=False)

# Apply filters
mask = pd.Series(True, index=df.index)

if "date_created" in df and date_range[0] and date_range[1]:
    start_dt = pd.to_datetime(pd.Timestamp(date_range[0]).floor("D"))
    end_dt   = pd.to_datetime(pd.Timestamp(date_range[1]).ceil("D"))
    mask &= df["date_created"].between(start_dt, end_dt, inclusive="both")

if status_sel and "status" in df:
    mask &= df["status"].isin(status_sel)

if device_sel and "device_type" in df:
    mask &= df["device_type"].fillna("Unknown").isin(device_sel)

dff = df.loc[mask].copy()

# Convenience fields
dff["revenue_gross"] = dff["order_total"].astype(float)
dff["revenue_net"]   = (dff["order_total"].astype(float) - dff["shipping_total"].astype(float)).fillna(dff["order_total"])
revenue_col = "revenue_gross" if include_shipping else "revenue_net"

# ---------------------- KPIs ------------------------
paid_mask = dff["status"].isin(PAID_STATUSES) if "status" in dff else pd.Series(True, index=dff.index)
paid_df = dff.loc[paid_mask].copy()

total_orders = int(len(paid_df))
total_rev    = float(paid_df[revenue_col].sum())
aov          = float(total_rev / total_orders) if total_orders else 0.0
denom        = float(paid_df["order_total"].replace(0, np.nan).sum()) if total_orders else 0.0
shipping_rate = float(paid_df["shipping_total"].fillna(0).sum() / denom) if denom else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Paid Orders", f"{total_orders:,}")
c2.metric("Revenue" + (" (incl. ship)" if include_shipping else " (excl. ship)"), f"£{total_rev:,.2f}")
c3.metric("AOV", f"£{aov:,.2f}")
c4.metric("Shipping as % of order total", f"{shipping_rate*100:,.1f}%")

# ---------------------- Tabs ------------------------
tab_map, tab_trends, tab_products, tab_customers, tab_marketing = st.tabs(
    ["🗺️ UK Heatmap", "📈 Trends", "🐟 Products", "👤 Customers & Devices", "🎯 Marketing"]
)

# ---------------------- UK Heatmap ------------------
with tab_map:
    st.subheader("Order density map (paid orders)")

    if {"latitude", "longitude"}.issubset(paid_df.columns):
        geo_df = paid_df.dropna(subset=["latitude", "longitude"]).copy()
        st.caption(f"Geocoded orders in selection: {len(geo_df):,} / {len(paid_df):,}")

        if geo_df.empty:
            st.info("No geocoded orders in the selected range.")
        else:
            # Wider bounds, then fallback if all filtered out
            in_uk = (
                geo_df["latitude"].between(48.0, 61.0) &
                geo_df["longitude"].between(-11.0, 4.0)
            )
            map_df = geo_df.loc[in_uk, ["latitude", "longitude"]].copy()
            if map_df.empty:
                map_df = geo_df[["latitude", "longitude"]].copy()

            default_view = pdk.ViewState(
                latitude=float(map_df["latitude"].mean()),
                longitude=float(map_df["longitude"].mean()),
                zoom=5.5, pitch=35
            )

            layer_type = st.radio("Layer", ["HexagonLayer", "HeatmapLayer"], horizontal=True)
            data_for_map = map_df.rename(columns={"longitude": "lon", "latitude": "lat"})
            if layer_type == "HexagonLayer":
                radius = st.slider("Hex radius (meters)", 1000, 15000, 7000, 500)
                elevation_scale = st.slider("Elevation scale", 1, 30, 8)
                layer = pdk.Layer(
                    "HexagonLayer",
                    data=data_for_map,
                    get_position="[lon, lat]",
                    radius=radius,
                    elevation_scale=elevation_scale,
                    elevation_range=[0, 1000],
                    extruded=True,
                    pickable=True,
                )
            else:
                layer = pdk.Layer(
                    "HeatmapLayer",
                    data=data_for_map,
                    get_position="[lon, lat]",
                    aggregation="MEAN",
                    pickable=False,
                )

            r = pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v10",
                initial_view_state=default_view,
                layers=[layer],
                tooltip={"text": "Orders around here"},
            )
            st.pydeck_chart(r, use_container_width=True)
    else:
        st.info("Latitude/Longitude columns not found.")

# ---------------------- Trends ----------------------
with tab_trends:
    st.subheader("Daily revenue & order count")
    if "date_created" in paid_df:
        # FIX: correct typo -> sort_index()
        ts = paid_df.set_index("date_created").sort_index()
        daily = ts.resample("D").agg(
            orders=("order_id", "count"),
            revenue=(revenue_col, "sum")
        ).reset_index()

        left, right = st.columns([2,1], gap="large")
        with left:
            line = alt.Chart(daily).mark_line().encode(
                x=alt.X("date_created:T", title="Date"),
                y=alt.Y("revenue:Q", title="Revenue (£)"),
                tooltip=["date_created:T", alt.Tooltip("revenue:Q", format=",.2f"), "orders:Q"]
            ).properties(height=320)
            st.altair_chart(line, use_container_width=True)
        with right:
            bar = alt.Chart(daily).mark_bar().encode(
                x=alt.X("date_created:T", title=""),
                y=alt.Y("orders:Q", title="Orders"),
                tooltip=["date_created:T", "orders:Q"]
            ).properties(height=320)
            st.altair_chart(bar, use_container_width=True)

        st.subheader("Orders heatmap (weekday × hour)")
        wk = ts.copy()
        wk["weekday"] = wk.index.day_name()
        wk["hour"] = wk.index.hour
        pivot = wk.groupby(["weekday", "hour"]).size().reset_index(name="orders")
        cat_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        pivot["weekday"] = pd.Categorical(pivot["weekday"], categories=cat_order, ordered=True)
        heat = alt.Chart(pivot).mark_rect().encode(
            x=alt.X("hour:O", title="Hour of day"),
            y=alt.Y("weekday:O", sort=cat_order, title="Weekday"),
            color=alt.Color("orders:Q", title="Orders"),
            tooltip=["weekday:O","hour:O","orders:Q"]
        ).properties(height=280)
        st.altair_chart(heat, use_container_width=True)
    else:
        st.info("Missing date_created column.")

# ---------------------- Products --------------------
with tab_products:
    st.subheader("Top products (by quantity & revenue)")
    if "item_details" in paid_df:
        exploded = paid_df[["order_id", "item_details"]].explode("item_details").dropna(subset=["item_details"])
        items = pd.json_normalize(exploded["item_details"])
        items["quantity"] = pd.to_numeric(items.get("quantity", 0), errors="coerce").fillna(0)
        items["total_price"] = pd.to_numeric(items.get("total_price", 0.0), errors="coerce").fillna(0.0)
        items["name"] = items.get("name").fillna("Unknown")

        by_qty = items.groupby(["product_id","name"], dropna=False)["quantity"] \
                      .sum().reset_index().sort_values("quantity", ascending=False).head(15)
        by_rev = items.groupby(["product_id","name"], dropna=False)["total_price"] \
                      .sum().reset_index().sort_values("total_price", ascending=False).head(15)

        c1, c2 = st.columns(2)
        with c1:
            ch1 = alt.Chart(by_qty).mark_bar().encode(
                x=alt.X("quantity:Q", title="Quantity"),
                y=alt.Y("name:N", sort="-x", title="Product"),
                tooltip=["name:N","quantity:Q"]
            ).properties(height=420, title="Top by Quantity")
            st.altair_chart(ch1, use_container_width=True)
        with c2:
            ch2 = alt.Chart(by_rev).mark_bar().encode(
                x=alt.X("total_price:Q", title="Revenue (£)"),
                y=alt.Y("name:N", sort="-x", title="Product"),
                tooltip=["name:N", alt.Tooltip("total_price:Q", format=",.2f")]
            ).properties(height=420, title="Top by Revenue")
            st.altair_chart(ch2, use_container_width=True)
    else:
        st.info("Missing item_details JSON.")

# --------------- Customers & Devices ----------------
with tab_customers:
    st.subheader("Guest vs Registered")
    if "is_guest" in dff:
        agg = dff.groupby("is_guest").agg(
            orders=("order_id", "count"),
            revenue=(revenue_col, "sum")
        ).reset_index()
        agg["label"] = agg["is_guest"].map({True: "Guest", False: "Registered"})
        pie = alt.Chart(agg).mark_arc().encode(
            theta="orders:Q",
            color="label:N",
            tooltip=["label:N","orders:Q", alt.Tooltip("revenue:Q", format=",.2f")]
        ).properties(height=300)
        st.altair_chart(pie, use_container_width=True)

    st.subheader("AOV by device")
    if "device_type" in dff:
        dev = dff.groupby("device_type").agg(
            orders=("order_id","count"),
            revenue=(revenue_col,"sum")
        ).reset_index()
        dev["aov"] = dev["revenue"] / dev["orders"].replace(0, np.nan)
        bar = alt.Chart(dev).mark_bar().encode(
            x=alt.X("aov:Q", title="AOV (£)"),
            y=alt.Y("device_type:N", sort="-x", title="Device"),
            tooltip=[ "device_type:N",
                      alt.Tooltip("aov:Q", format=",.2f"),
                      "orders:Q",
                      alt.Tooltip("revenue:Q", format=",.2f") ]
        ).properties(height=320)
        st.altair_chart(bar, use_container_width=True)

    st.subheader("Weekday performance")
    if "date_created" in dff:
        tmp = dff.copy()
        tmp["weekday"] = tmp["date_created"].dt.day_name()
        wk = tmp.groupby("weekday").agg(
            orders=("order_id","count"),
            revenue=(revenue_col,"sum")
        ).reset_index()
        cat_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        wk["weekday"] = pd.Categorical(wk["weekday"], categories=cat_order, ordered=True)
        bars = alt.Chart(wk).mark_bar().encode(
            x=alt.X("weekday:O", sort=cat_order, title=""),
            y=alt.Y("orders:Q", title="Orders"),
            tooltip=["weekday:O","orders:Q", alt.Tooltip("revenue:Q", format=",.2f")]
        ).properties(height=300)
        st.altair_chart(bars, use_container_width=True)

# ---------------------- Marketing -------------------
with tab_marketing:
    st.subheader("Attribution / Campaigns")
    left, right = st.columns(2)

    if "attribution_source" in dff:
        src = dff.copy()
        src["attribution_source"] = src["attribution_source"].fillna("Unknown")
        by_src = src.groupby("attribution_source").agg(
            orders=("order_id","count"),
            revenue=(revenue_col,"sum")
        ).reset_index().sort_values("orders", ascending=False).head(12)
        with left:
            ch = alt.Chart(by_src).mark_bar().encode(
                x=alt.X("orders:Q", title="Orders"),
                y=alt.Y("attribution_source:N", sort="-x", title="Source"),
                tooltip=["attribution_source:N","orders:Q", alt.Tooltip("revenue:Q", format=",.2f")]
            ).properties(height=320, title="Orders by Source")
            st.altair_chart(ch, use_container_width=True)

    if "campaign_source" in dff or "campaign_medium" in dff:
        camp = dff.copy()
        camp["campaign_source"] = camp.get("campaign_source", pd.Series(index=camp.index)).fillna("Unknown")
        camp["campaign_medium"] = camp.get("campaign_medium", pd.Series(index=camp.index)).fillna("Unknown")
        by_camp = camp.groupby(["campaign_source","campaign_medium"]).agg(
            orders=("order_id","count"),
            revenue=(revenue_col,"sum")
        ).reset_index().sort_values("orders", ascending=False).head(20)
        with right:
            ch = alt.Chart(by_camp).mark_bar().encode(
                x=alt.X("orders:Q", title="Orders"),
                y=alt.Y("campaign_source:N", sort="-x", title="UTM Source"),
                color=alt.Color("campaign_medium:N", title="UTM Medium"),
                tooltip=["campaign_source:N","campaign_medium:N","orders:Q", alt.Tooltip("revenue:Q", format=",.2f")]
            ).properties(height=320, title="Top Campaigns")
            st.altair_chart(ch, use_container_width=True)

    st.subheader("Coupons")
    if "coupon_details" in paid_df:
        coup = paid_df[["order_id","coupon_details", revenue_col]].explode("coupon_details")
        coup["has_coupon"] = coup["coupon_details"].notna()

        by_use = coup.groupby("has_coupon").agg(
            orders=("order_id","nunique"),
            revenue=(revenue_col,"sum")
        ).reset_index()
        by_use["label"] = by_use["has_coupon"].map({True:"With coupon", False:"No coupon"})

        c1, c2 = st.columns([1,1])
        with c1:
            ch = alt.Chart(by_use).mark_bar().encode(
                x=alt.X("label:N", title=""),
                y=alt.Y("orders:Q", title="Orders"),
                tooltip=["label:N","orders:Q", alt.Tooltip("revenue:Q", format=",.2f")]
            ).properties(height=300, title="Coupon usage impact")
            st.altair_chart(ch, use_container_width=True)

        cc = coup.dropna(subset=["coupon_details"]).copy()
        if not cc.empty:
            codes = pd.json_normalize(cc["coupon_details"])
            codes = pd.concat([codes, cc[[revenue_col, "order_id"]].reset_index(drop=True)], axis=1)
            top_codes = codes.groupby("code").agg(
                orders=("order_id","nunique"),
                discount=("discount_amount","sum"),
                revenue=(revenue_col,"sum")
            ).reset_index().sort_values("orders", ascending=False).head(12)
            with c2:
                ch2 = alt.Chart(top_codes).mark_bar().encode(
                    x=alt.X("orders:Q", title="Orders"),
                    y=alt.Y("code:N", sort="-x", title="Coupon"),
                    tooltip=["code:N","orders:Q",
                             alt.Tooltip("discount:Q", format=",.2f"),
                             alt.Tooltip("revenue:Q", format=",.2f")]
                ).properties(height=300, title="Top coupon codes")
                st.altair_chart(ch2, use_container_width=True)

# ---------------------- Raw Data (optional) ---------
with st.expander("Show filtered data"):
    st.dataframe(dff, use_container_width=True)

if __name__ == "__main__":
    pass
