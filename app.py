"""Streamlit dashboard — scan and act on the best UAE property deals fast.

Run:  streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dealfinder.config import Config
from dealfinder.pipeline import find_deals

st.set_page_config(page_title="UAE Property Deal Finder", page_icon="🏙️", layout="wide")


@st.cache_data(ttl=300)
def load_deals() -> pd.DataFrame:
    return find_deals(Config.load())


st.title("🏙️ UAE Property Deal Finder")
st.caption(
    "Listings priced against **recorded transactions** (DLD · ADRE · DXBconnect) and "
    "ranked on undervaluation + net rental yield. Highest scores = act first."
)

try:
    deals = load_deals()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

if deals.empty:
    st.warning("No listings scored. Seed sample data: `python -m scripts.seed_sample_data`")
    st.stop()

# ── Sidebar filters ─────────────────────────────────────────────────────────
sb = st.sidebar
sb.header("Filters")
cities = sb.multiselect("City", sorted(deals["city"].dropna().unique()))
types = sb.multiselect("Property type", sorted(deals["property_type"].dropna().unique()))
sources = sb.multiselect("Source", sorted(deals["source"].dropna().unique()))
beds = sb.multiselect("Bedrooms", sorted(deals["bedrooms"].dropna().unique()))

price_cap = int(deals["price"].max())
max_price = sb.slider("Max price (AED)", 0, price_cap, price_cap, step=100_000)
min_score = sb.slider("Min deal score", 0, 100, 25)
min_yield = sb.slider("Min net yield (%)", 0.0, 12.0, 0.0, step=0.5)
min_discount = sb.slider("Min discount to comps (%)", 0.0, 40.0, 0.0, step=1.0)
hide_suspicious = sb.checkbox("Hide too-good-to-be-true (>40% off)", value=True)

f = deals.copy()
if cities:
    f = f[f["city"].isin(cities)]
if types:
    f = f[f["property_type"].isin(types)]
if sources:
    f = f[f["source"].isin(sources)]
if beds:
    f = f[f["bedrooms"].isin(beds)]
f = f[(f["price"] <= max_price) & (f["deal_score"] >= min_score)]
f = f[(f["net_yield_pct"].fillna(0) >= min_yield)]
f = f[(f["discount_pct"].fillna(-99) >= min_discount)]
if hide_suspicious:
    f = f[~f["flags"].str.contains("suspicious-discount", na=False)]

# ── Headline metrics ────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Matching deals", len(f))
c2.metric("Best score", f"{f['deal_score'].max():.0f}" if len(f) else "—")
c3.metric("Median discount", f"{f['discount_pct'].median():.1f}%" if len(f) else "—")
c4.metric("Median net yield", f"{f['net_yield_pct'].median():.1f}%" if len(f) else "—")

if f.empty:
    st.info("No deals match these filters — loosen them in the sidebar.")
    st.stop()

# ── Opportunity map ─────────────────────────────────────────────────────────
st.subheader("Opportunity map — discount vs net yield")
fig = px.scatter(
    f, x="discount_pct", y="net_yield_pct", size="deal_score", color="city",
    hover_data=["area", "property_type", "bedrooms", "price", "deal_score", "source"],
    labels={"discount_pct": "Discount to comps (%)", "net_yield_pct": "Net yield (%)"},
)
fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig, use_container_width=True)

# ── Ranked table ────────────────────────────────────────────────────────────
st.subheader(f"Ranked deals ({len(f)})")
show = f[[
    "deal_score", "city", "area", "building", "property_type", "bedrooms",
    "size_sqft", "price", "listing_ppsf", "benchmark_ppsf", "discount_pct",
    "net_yield_pct", "est_annual_rent", "confidence", "comp_samples", "source",
    "flags", "listed_date", "url",
]].rename(columns={
    "deal_score": "Score", "city": "City", "area": "Area", "building": "Building",
    "property_type": "Type", "bedrooms": "Bed", "size_sqft": "Sqft", "price": "Price",
    "listing_ppsf": "Ask/sqft", "benchmark_ppsf": "Comp/sqft", "discount_pct": "Disc %",
    "net_yield_pct": "Net Yld %", "est_annual_rent": "Est rent", "confidence": "Conf",
    "comp_samples": "Comps", "source": "Source", "flags": "Flags",
    "listed_date": "Listed", "url": "Link",
})
st.dataframe(
    show, use_container_width=True, hide_index=True, height=520,
    column_config={
        "Price": st.column_config.NumberColumn(format="%d"),
        "Est rent": st.column_config.NumberColumn(format="%d"),
        "Link": st.column_config.LinkColumn("Link", display_text="open"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
    },
)

st.download_button(
    "⬇ Download these deals (CSV)",
    f.to_csv(index=False).encode(),
    file_name="uae_deals.csv",
    mime="text/csv",
)
st.caption(
    "Score = 55% undervaluation + 45% net yield, scaled by how many recent comps "
    "back the benchmark. Always verify title, service charges and any flags before acting."
)
