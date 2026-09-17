import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from supabase import create_client, Client

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="E-Commerce BI Dashboard", page_icon="📊", layout="wide")

# ---------------------------------------------------------
# SUPABASE CONNECTION
# ---------------------------------------------------------
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# ---------------------------------------------------------
# AUTH: LOGIN SCREEN
# ---------------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "company_id" not in st.session_state:
    st.session_state.company_id = None
if "company_name" not in st.session_state:
    st.session_state.company_name = None

def login_screen():
    st.title("🔒 E-Commerce BI Dashboard — Login")
    st.caption("Please sign in to access your company's dashboard.")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.user = res.user

            # Look up which company this user belongs to
            profile = supabase.table("profiles").select("company_id, companies(name)").eq("id", res.user.id).single().execute()
            if profile.data:
                st.session_state.company_id = profile.data["company_id"]
                st.session_state.company_name = profile.data["companies"]["name"] if profile.data.get("companies") else "Unknown Company"
            else:
                st.error("No company is linked to this account. Contact your administrator.")
                st.session_state.user = None
                return
            st.rerun()
        except Exception as e:
            st.error("Login failed. Check your email/password and try again.")

if st.session_state.user is None:
    login_screen()
    st.stop()

# Sidebar: identity + logout
with st.sidebar:
    st.success(f"Logged in as {st.session_state.user.email}")
    st.info(f"Company: {st.session_state.company_name}")
    if st.button("Log out"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.session_state.company_id = None
        st.session_state.company_name = None
        st.rerun()
    st.divider()

COMPANY_ID = st.session_state.company_id

# ---------------------------------------------------------
# DATA LOADING (scoped to this company only)
# ---------------------------------------------------------
def fetch_all(table_name: str) -> pd.DataFrame:
    all_rows = []
    page_size = 1000
    start = 0
    while True:
        res = (
            supabase.table(table_name)
            .select("*")
            .eq("company_id", COMPANY_ID)
            .range(start, start + page_size - 1)
            .execute()
        )
        rows = res.data
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        start += page_size
    return pd.DataFrame(all_rows)

@st.cache_data(ttl=30)
def load_data(company_id: str):
    orders = fetch_all("orders")
    details = fetch_all("order_details")
    if orders.empty or details.empty:
        return pd.DataFrame()
    df = details.merge(orders, on="order_id", how="left", suffixes=("", "_order"))
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["month_year"] = df["order_date"].dt.to_period("M").astype(str)
    return df

df = load_data(COMPANY_ID)

if df.empty:
    st.warning("No data found for your company yet. Add an order below to get started.")

# ---------------------------------------------------------
# SIDEBAR FILTERS
# ---------------------------------------------------------
st.sidebar.header("Filters")

if not df.empty:
    states = sorted(df["state"].dropna().unique())
    sel_states = st.sidebar.multiselect("State", states)

    cities_pool = df[df["state"].isin(sel_states)] if sel_states else df
    cities = sorted(cities_pool["city"].dropna().unique())
    sel_cities = st.sidebar.multiselect("City", cities)

    categories = sorted(df["category"].dropna().unique())
    sel_categories = st.sidebar.multiselect("Category", categories)

    subcat_pool = df[df["category"].isin(sel_categories)] if sel_categories else df
    subcats = sorted(subcat_pool["sub_category"].dropna().unique())
    sel_subcats = st.sidebar.multiselect("Sub-Category", subcats)

    min_date, max_date = df["order_date"].min(), df["order_date"].max()
    date_range = st.sidebar.date_input("Order Date Range", value=(min_date, max_date))

    filtered = df.copy()
    if sel_states:
        filtered = filtered[filtered["state"].isin(sel_states)]
    if sel_cities:
        filtered = filtered[filtered["city"].isin(sel_cities)]
    if sel_categories:
        filtered = filtered[filtered["category"].isin(sel_categories)]
    if sel_subcats:
        filtered = filtered[filtered["sub_category"].isin(sel_subcats)]
    if len(date_range) == 2:
        start_d, end_d = date_range
        filtered = filtered[(filtered["order_date"] >= pd.to_datetime(start_d)) & (filtered["order_date"] <= pd.to_datetime(end_d))]
else:
    filtered = df.copy()
    categories = []

# ---------------------------------------------------------
# HEADER + KPIs
# ---------------------------------------------------------
st.title(f"📊 {st.session_state.company_name} — BI Dashboard")

if not filtered.empty:
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Sales", f"₹{filtered['amount'].sum():,.0f}")
    k2.metric("Total Profit", f"₹{filtered['profit'].sum():,.0f}")
    k3.metric("Total Orders", f"{filtered['order_id'].nunique():,}")
    k4.metric("Total Quantity", f"{filtered['quantity'].sum():,.0f}")
    k5.metric("Total Customers", f"{filtered['customer_name'].nunique():,}")

    st.divider()

    # -----------------------------------------------------
    # CHARTS
    # -----------------------------------------------------
    c1, c2, c3 = st.columns(3)
    with c1:
        sales_cat = filtered.groupby("category", as_index=False)["amount"].sum()
        st.plotly_chart(px.bar(sales_cat, x="category", y="amount", color="category", title="Sales by Category"), use_container_width=True)
    with c2:
        profit_cat = filtered.groupby("category", as_index=False)["profit"].sum()
        st.plotly_chart(px.bar(profit_cat, x="category", y="profit", color="category", title="Profit by Category"), use_container_width=True)
    with c3:
        qty_cat = filtered.groupby("category", as_index=False)["quantity"].sum()
        st.plotly_chart(px.bar(qty_cat, x="category", y="quantity", color="category", title="Quantity by Category"), use_container_width=True)

    monthly = filtered.groupby("month_year", as_index=False)["amount"].sum().sort_values("month_year")
    st.plotly_chart(px.line(monthly, x="month_year", y="amount", title="Monthly Sales Trend", markers=True), use_container_width=True)

    c4, c5 = st.columns(2)
    with c4:
        state_sales = filtered.groupby("state", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
        st.plotly_chart(px.bar(state_sales, x="state", y="amount", title="State-wise Sales"), use_container_width=True)
    with c5:
        city_sales = filtered.groupby("city", as_index=False)["amount"].sum().sort_values("amount", ascending=False).head(15)
        st.plotly_chart(px.bar(city_sales, x="city", y="amount", title="Top Cities by Sales"), use_container_width=True)

    c6, c7 = st.columns(2)
    with c6:
        top_customers = filtered.groupby("customer_name", as_index=False)["amount"].sum().sort_values("amount", ascending=False).head(10)
        st.plotly_chart(px.bar(top_customers, x="customer_name", y="amount", title="Top 10 Customers"), use_container_width=True)
    with c7:
        top_subcat = filtered.groupby("sub_category", as_index=False)["amount"].sum().sort_values("amount", ascending=False).head(10)
        st.plotly_chart(px.bar(top_subcat, x="sub_category", y="amount", title="Top Sub-Categories"), use_container_width=True)

    st.divider()

    # -----------------------------------------------------
    # AUTO-GENERATED INSIGHTS
    # -----------------------------------------------------
    st.subheader("🔎 Business Insights")
    cat_perf = filtered.groupby("category").agg(sales=("amount", "sum"), profit=("profit", "sum")).reset_index()
    if not cat_perf.empty:
        best_cat = cat_perf.loc[cat_perf["sales"].idxmax(), "category"]
        weak_cat = cat_perf.loc[cat_perf["sales"].idxmin(), "category"]
        most_profitable = cat_perf.loc[cat_perf["profit"].idxmax(), "category"]
        st.write(f"- **Best-performing category (by sales):** {best_cat}")
        st.write(f"- **Weakest category (by sales):** {weak_cat}")
        st.write(f"- **Most profitable category:** {most_profitable}")

    subcat_perf = filtered.groupby("sub_category")["profit"].sum().reset_index()
    loss_making = subcat_perf[subcat_perf["profit"] < 0].sort_values("profit")
    if not loss_making.empty:
        st.write("- **Loss-making sub-categories:**")
        for _, row in loss_making.iterrows():
            st.write(f"   - {row['sub_category']}: ₹{row['profit']:,.0f}")
    else:
        st.write("- No loss-making sub-categories in the current filter selection.")

    st.divider()

# ---------------------------------------------------------
# ADD NEW ORDER (scoped to this company)
# ---------------------------------------------------------
st.subheader("➕ Add New Order")

with st.form("new_order_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        new_order_id = st.text_input("Order ID (e.g. B-99999)")
        new_date = st.date_input("Order Date", value=datetime.today())
        new_customer = st.text_input("Customer Name")
        new_state = st.text_input("State")
        new_city = st.text_input("City")
    with col2:
        new_category = st.text_input("Category")
        new_subcategory = st.text_input("Sub-Category")
        new_amount = st.number_input("Amount", min_value=0.0, step=1.0)
        new_profit = st.number_input("Profit", step=1.0)
        new_quantity = st.number_input("Quantity", min_value=1, step=1)

    submitted_order = st.form_submit_button("Submit Order")

    if submitted_order:
        if not new_order_id or not new_customer:
            st.error("Order ID and Customer Name are required.")
        else:
            try:
                supabase.table("orders").insert({
                    "order_id": new_order_id,
                    "company_id": COMPANY_ID,
                    "order_date": str(new_date),
                    "customer_name": new_customer,
                    "state": new_state,
                    "city": new_city,
                }).execute()

                supabase.table("order_details").insert({
                    "order_id": new_order_id,
                    "company_id": COMPANY_ID,
                    "category": new_category,
                    "sub_category": new_subcategory,
                    "amount": new_amount,
                    "profit": new_profit,
                    "quantity": new_quantity,
                }).execute()

                st.success(f"Order {new_order_id} added successfully!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Failed to add order: {e}")
