import os
import json
import pandas as pd
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv
from utils.utils import get_db_engine
import plotly.express as px
import plotly.graph_objects as go

#our colours
logo_green = "#0A8F60" 
darker_green = "#045539"  
lighter_green = "#74D6B2"  

#load credentials
load_dotenv()
db_table = os.getenv("DB_TABLE")
db_schema = os.getenv("DB_SCHEMA", "public")

title = "DC Freshwater Fish - Orders"
logo = "https://dcfreshwaterfish.co.uk/wp-content/uploads/2016/12/dc-freshwater-fish.png"

st.set_page_config(page_title=title, page_icon=logo, layout="wide")



def main():
    @st.cache_data(show_spinner="Loading orders from database...")
    def load_orders_from_database():

        # logo and title
        logo_column, title_column = st.columns([1, 12])
        with logo_column:
            st.image(logo)
        with title_column:
            st.markdown(f"<h1 style='text-align: center'>{title}</h1>", unsafe_allow_html=True)

        st.markdown("---")
        
        # map, space and bar columns
        map_column, space, performance_column = st.columns([1, 0.05, 2])

##################################################################   map  ##################################################################
    with map_column:
        st.markdown("### Areas with most orders")
        coords_df = all_orders.dropna(subset=["latitude", "longitude"]).copy()

        #start map over uk
        map_initial_view = pdk.ViewState(latitude=53.6, longitude=-2.8, zoom=4.85, pitch=35)

        map_hex_layer = pdk.Layer(
            "HexagonLayer",
            data=coords_df,
            get_position="[longitude, latitude]",
            radius=4000,
            elevation_scale=30,
            elevation_range=[0, 2500],
            extruded=True,
            pickable=True,
        )
    
        pydeck_map = pdk.Deck(
            map_style="dark",
            initial_view_state=map_initial_view,
            layers=[map_hex_layer],
            height=360,
            tooltip={"text": "Orders: {elevationValue}"},
        )
        st.pydeck_chart(pydeck_map, use_container_width=True)

    # Space between map and graph
    with space:
        st.write("")

##################################################################   performance graph  ##################################################################
    with performance_column:
        st.markdown("### Company performance over time")
        
        # selector
        selected_metric = st.radio("", ["Orders per day", "Average spend per order"])
        
        orders_with_dates = all_orders.dropna(subset=["date_created"]).copy()
        orders_with_dates["date_created"] = pd.to_datetime(orders_with_dates["date_created"], errors="coerce")
        orders_with_dates["date_only"] = orders_with_dates["date_created"].dt.normalize()

        daily = (
            orders_with_dates
            .groupby("date_only")
            .agg(num_orders=("order_id", "count"),
                 revenue=("revenue_net", "sum"))
            .reset_index()
            .fillna(0)
        )
        daily["average_spend"] = daily.apply(
            lambda r: (r["revenue"] / r["num_orders"]) if r["num_orders"] else 0.0, axis=1
        )

        years = sorted(daily["date_only"].dt.year.unique())
        mid_year_dates = pd.to_datetime(pd.Series(years).astype(str) + "-07-01")

        if selected_metric == "Orders per day":
            y_axis_title = "Number of orders"
            series = daily.rename(columns={"date_only": "Date", "num_orders": "Value"})[["Date", "Value"]]
            yearly_averages_df = (
                daily.assign(year=daily["date_only"].dt.year)
                    .groupby("year", as_index=False)
                    .agg(yearly_avg=("num_orders", "mean"))
            )

        else:
            y_axis_title = "Average order amount (£)"
            series = daily.rename(columns={"date_only": "Date", "average_spend": "Value"})[["Date", "Value"]]
            yearly_avg = (
                daily.assign(year=daily["date_only"].dt.year)
                    .groupby("year", as_index=False)
                    .agg(revenue_sum=("revenue", "sum"), orders_sum=("num_orders", "sum"))
            )
            yearly_avg["yearly_avg"] = (yearly_avg["revenue_sum"] / yearly_avg["orders_sum"].replace(0, pd.NA)).fillna(0)
            yearly_averages_df = yearly_avg[["year", "yearly_avg"]]

        yearly_averages_df["plot_date"] = pd.to_datetime(yearly_averages_df["year"].astype(str) + "-07-01")

        fig_perf = go.Figure()

        # background alternating year bands
        for y in years:
            if y % 2 == 1:
                fig_perf.add_vrect(
                    x0=pd.Timestamp(f"{y}-01-01"),
                    x1=pd.Timestamp(f"{y}-12-31"),
                    fillcolor="rgba(229,231,235,0.45)",
                    line_width=0,
                    layer="below",
                )

        # plot daily bars
        fig_perf.add_trace(go.Bar(
            x=series["Date"],
            y=series["Value"],
            marker_color=logo_green,
            name="Daily",
            hovertemplate="Date=%{x|%Y-%m-%d}<br>Value=%{y}<extra></extra>"
        ))

        # plot yearly average trend line
        fig_perf.add_trace(go.Scatter(
            x=yearly_averages_df["plot_date"],
            y=yearly_averages_df["yearly_avg"],
            mode="lines+markers",
            line=dict(width=3, color=darker_green),
            marker=dict(size=8),
            name="Yearly average",
            hovertemplate="Year=%{x|%Y}<br>Avg=%{y:.2f}<extra></extra>"
        ))

        fig_perf.update_layout(
            height=460,
            margin=dict(l=24, r=8, t=40, b=8),
            xaxis=dict(
                title="Date",
                tickvals=mid_year_dates,
                tickformat="%Y",
                showgrid=False
            ),
            yaxis=dict(title=y_axis_title),
            showlegend=False,
        )

        st.plotly_chart(fig_perf, use_container_width=True)


##################################################################   Best & Worst Products  ##################################################################
    st.markdown("---")
    st.markdown("#### Best & worst products")

    # filter columns
    date_column, metric_column, number_column = st.columns([1, 1, 1])
    
    date_created_series = pd.to_datetime(all_orders["date_created"], errors="coerce").dropna()
    min_date, max_date = date_created_series.min().date(), date_created_series.max().date()

    with date_column:
        selected_date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    with metric_column:
        rank_by = st.selectbox("Rank by", ["Revenue", "Quantity", "Revenue per unit"], index=0)
    with number_column:
        num_to_show = st.number_input("How many to show", min_value=1, max_value=50, value=10, step=1)

    product_data_df = all_orders.copy()
    
    if all(selected_date_range):
        start_date = pd.to_datetime(pd.Timestamp(selected_date_range[0]).floor("D"))
        end_date = pd.to_datetime(pd.Timestamp(selected_date_range[1]).ceil("D"))
        date_filter = pd.to_datetime(product_data_df["date_created"], errors="coerce").between(start_date, end_date, inclusive="both")
        product_data_df = product_data_df[date_filter]

    exploded_items_df = product_data_df[["order_id", "item_details"]].explode("item_details").dropna(subset=["item_details"])
    item_details_df = pd.json_normalize(exploded_items_df["item_details"])

    item_details_df["name"] = item_details_df.get("name").fillna("Unknown")
    item_details_df["quantity"] = pd.to_numeric(item_details_df.get("quantity", 0), errors="coerce").fillna(0)
    item_details_df["total_price"] = pd.to_numeric(item_details_df.get("total_price", 0.0), errors="coerce").fillna(0.0)
    item_details_df["order_id"] = exploded_items_df["order_id"].values

    product_agg_df = (
        item_details_df
        .groupby(["product_id", "name"], dropna=False)
        .agg(orders=("order_id", "nunique"),
             quantity=("quantity", "sum"),
             revenue=("total_price", "sum"))
        .reset_index()
    )
    product_agg_df["name"] = product_agg_df["name"].str.replace("&ndash;", "–").str.replace("&amp;", "&")

    #to hide the demo products
    product_agg_df = product_agg_df[product_agg_df["orders"] >= 7].copy()

    if product_agg_df.empty:
        st.info("No products match the current filters")
    else:
        product_agg_df["price_per_item"] = product_agg_df.apply(
            lambda r: (r["revenue"] / r["quantity"]) if r["quantity"] else 0.0, axis=1
        )
        sort_column = {"Revenue": "revenue", "Quantity": "quantity", "Revenue per unit": "price_per_item"}[rank_by]
        num_to_show = int(max(1, min(num_to_show, len(product_agg_df))))
        top_products = product_agg_df.nlargest(num_to_show, sort_column)
        bottom_products = product_agg_df.nsmallest(num_to_show, sort_column)

        def product_table(df):
            t = df.copy()
            t["Revenue (£)"] = t["revenue"].map(lambda v: f"£{v:,.2f}")
            t["Quantity"] = t["quantity"].astype(int).map("{:,}".format)
            t["Orders"] = t["orders"].astype(int).map("{:,}".format)
            t["Price per item"] = t["price_per_item"].map(lambda v: f"£{v:,.2f}")
            t.rename(columns={"name": "Product"}, inplace=True)
            return t[["Product", "Orders", "Quantity", "Revenue (£)", "Price per item"]]

        col_top, col_bottom = st.columns(2)
        with col_top:
            st.markdown(f"**Top {num_to_show} by {rank_by.lower()}**")
            st.dataframe(product_table(top_products), use_container_width=True, hide_index=True)
        with col_bottom:
            st.markdown(f"**Bottom {num_to_show} by {rank_by.lower()}**")
            st.dataframe(product_table(bottom_products), use_container_width=True, hide_index=True)

##################################################################   Logged-in vs Guest  ##################################################################
    st.markdown("---")
    st.markdown("#### Logged-in vs guests")

    for col in ("order_total", "shipping_total"):
        if col in all_orders.columns:
            all_orders[col] = pd.to_numeric(all_orders[col], errors="coerce")
            
    if "revenue_net" not in all_orders.columns and "order_total" in all_orders.columns:
        if "shipping_total" in all_orders.columns:
            all_orders["revenue_net"] = (all_orders["order_total"] - all_orders["shipping_total"]).fillna(all_orders["order_total"])
        else:
            all_orders["revenue_net"] = all_orders["order_total"]

    metric_choice = st.selectbox(
        "Metric",
        ["Average items per order", "Average spend per order", "Average orders per customer"],
        index=0,
    )
    
    df = all_orders.copy()
    

    df["customer_type"] = df["is_guest"].map({True: "Guest", False: "Logged-in"})


    df = df[df["customer_type"].notna()]

    if metric_choice == "Average items per order":
        avg_items_df = df.groupby("customer_type")["total_items"].mean().reset_index(name="value")
        
        fig_customer_type = px.bar(
            avg_items_df, x="customer_type", y="value",
            labels={"customer_type": "", "value": "Avg items per order"},
            color="customer_type",
            color_discrete_map={"Guest": lighter_green, "Logged-in": logo_green}
        )
        
        fig_customer_type.update_traces(texttemplate="%{y:.2f}", textposition="outside", cliponaxis=False, showlegend=False)
        fig_customer_type.update_layout(height=300, margin=dict(t=40))
        
        st.plotly_chart(fig_customer_type, use_container_width=True)

    elif metric_choice == "Average spend per order":
        
        avg_spend_df = df.groupby("customer_type")["revenue_net"].mean().reset_index(name="value")
        
        fig_customer_type = px.bar(
            avg_spend_df, x="customer_type", y="value",
            labels={"customer_type": "", "value": "Average spend per order (£)"},
            color="customer_type",
            color_discrete_map={"Guest": lighter_green, "Logged-in": logo_green}
        )
        
        fig_customer_type.update_traces(texttemplate="£%{y:.2f}", textposition="outside", cliponaxis=False, showlegend=False)
        fig_customer_type.update_layout(height=300, margin=dict(t=40))
        
        st.plotly_chart(fig_customer_type, use_container_width=True)

    elif metric_choice == "Average orders per customer":
    
            per_customer = (
                df.dropna(subset=["customer_identifier"])
                .groupby(["customer_type", "customer_identifier"])["order_id"]
                .nunique()
                .reset_index(name="orders_per_customer")
            )

            avg_df = per_customer.groupby("customer_type", as_index=False)["orders_per_customer"].mean().rename(columns={"orders_per_customer": "avg"})
            
            mode_df = per_customer.groupby("customer_type")["orders_per_customer"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None).reset_index(name="mode")
            
            out = avg_df.merge(mode_df, on="customer_type", how="left")
            
            out["label"] = out.apply(lambda r: f"{r['avg']:.2f} avg • {('—' if pd.isna(r['mode']) else int(r['mode']))} most common", axis=1)

            fig_seg = px.bar(
                out, x="customer_type", y="avg",
                labels={"customer_type": "", "avg": "Avg orders per customer"},
                color="customer_type",
                color_discrete_map={"Guest": lighter_green, "Logged-in": logo_green}
            )
            fig_seg.update_traces(text=out["label"], textposition="outside", cliponaxis=False, showlegend=False)
            fig_seg.update_layout(height=300, margin=dict(t=40))
            
            st.plotly_chart(fig_seg, use_container_width=True)
        
##################################################################   Mobile vs Desktop  ##################################################################
    st.markdown("---")
    st.markdown("#### Mobile vs Desktop")

    device_df = all_orders.copy()
    
    if "device_type" in device_df.columns:
        device_df["device_type"] = device_df["device_type"].astype(str).str.strip()
        device_df = device_df[device_df["device_type"].str.lower().isin(["mobile", "desktop"])]

        if not device_df.empty:
            order_by_device = device_df.groupby("device_type", as_index=False)["order_id"].count()
            total = order_by_device["order_id"].sum()
            order_by_device["percent_orders"] = (order_by_device["order_id"] / total) * 100

            avg_spend_by_device = (
                device_df.groupby("device_type", as_index=False)["order_total"].mean()
                if "order_total" in device_df.columns else
                pd.DataFrame(columns=["device_type", "order_total"])
            )
            avg_items_by_device = (
                device_df.groupby("device_type", as_index=False)["total_items"].mean()
                if "total_items" in device_df.columns else
                pd.DataFrame(columns=["device_type", "total_items"])
            )

            spend_column, order_column, items_column = st.columns(3)

            with spend_column:
                st.markdown("**Average Spend (£)**")
                if not avg_spend_by_device.empty:
                    fig_spend = px.bar(
                        avg_spend_by_device, x="device_type", y="order_total",
                        labels={"device_type": "Device", "order_total": "Avg Spend (£)"},
                        color="device_type",
                        color_discrete_map={"Mobile": lighter_green, "Desktop": logo_green}
                    )
                    
                    fig_spend.update_traces(texttemplate="£%{y:.2f}", textposition="outside", cliponaxis=False, showlegend=False)
                    fig_spend.update_layout(height=300, margin=dict(l=0, r=0, t=40, b=0), xaxis_title="Device")
                    st.plotly_chart(fig_spend, use_container_width=True)
                else:
                    st.info("No data for device types.")

            with order_column:
                st.markdown("**% of Orders**")
                if not order_by_device.empty:
                    fig_pie = px.pie(
                        order_by_device,
                        values="percent_orders",
                        names="device_type",
                        color="device_type",
                        color_discrete_map={"Mobile": lighter_green, "Desktop": logo_green},
                        hole=0
                    )
                    fig_pie.update_traces(texttemplate="%{percent:.1%}")
                    fig_pie.update_layout(height=300, margin=dict(l=0, r=0, t=40, b=0), legend_title="Device")
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("No data for device types.")

            with items_column:
                st.markdown("**Average Items**")
                if not avg_items_by_device.empty:
                    fig_items = px.bar(
                        avg_items_by_device, x="device_type", y="total_items",
                        labels={"device_type": "Device", "total_items": "Avg Items"},
                        color="device_type",
                        color_discrete_map={"Mobile": lighter_green, "Desktop": logo_green}
                    )
                    # keep labels visible
                    fig_items.update_traces(texttemplate="%{y:.1f}", textposition="outside", cliponaxis=False, showlegend=False)
                    fig_items.update_layout(height=300, margin=dict(l=0, r=0, t=40, b=0), xaxis_title="Device")
                    st.plotly_chart(fig_items, use_container_width=True)
                else:
                    st.info("No data for device types.")
        else:
            st.info("No data for device types.")
    else:
        st.info("Missing the 'device_type' column. Cannot create these charts.")


##################################################################   LOAD DATA  ##################################################################
def load_orders_from_database():
    db_engine = get_db_engine()
    orders_df = pd.read_sql_table(db_table, con=db_engine, schema=db_schema)

    for col in ("date_created", "date_modified", "date_paid"):
        if col in orders_df.columns:
            orders_df[col] = pd.to_datetime(orders_df[col], errors="coerce")


    for col in ("order_total", "shipping_total", "total_items", "latitude", "longitude"):
        if col in orders_df.columns:
            orders_df[col] = pd.to_numeric(orders_df[col], errors="coerce")

    # JSON (possibly serialized)
    def _parse_json(v):
        if isinstance(v, (list, dict)) or v is None or (isinstance(v, float) and pd.isna(v)):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except Exception:
                return None
        return None

    if "item_details" in orders_df.columns:
        orders_df["item_details"] = orders_df["item_details"].apply(_parse_json)

    if "order_total" in orders_df.columns:
        if "shipping_total" in orders_df.columns:
            orders_df["revenue_net"] = (orders_df["order_total"] - orders_df["shipping_total"]).fillna(orders_df["order_total"])
        else:
            orders_df["revenue_net"] = orders_df["order_total"]

    if "total_items" not in orders_df.columns and "item_details" in orders_df.columns:
        def _sum_qty(items):
            try:
                if isinstance(items, list):
                    return sum(int(d.get("quantity", 0)) for d in items if isinstance(d, dict))
            except Exception:
                pass
            return pd.NA
        orders_df["total_items"] = orders_df["item_details"].apply(_sum_qty)

    return orders_df


if __name__ == "__main__":
    main()
