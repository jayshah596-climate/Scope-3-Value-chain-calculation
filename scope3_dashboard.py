import math
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Scope 3 Value Chain Dashboard", layout="wide")

st.title("🌍 Scope 3 Value Chain Emissions Dashboard")

# -----------------------------
# 1. CATEGORY DEFINITIONS
# -----------------------------

CATEGORIES = {
    1: "Purchased Goods and Services",
    2: "Capital Goods",
    3: "Fuel & Energy Related Activities",
    4: "Upstream Transportation & Distribution",
    5: "Waste Generated in Operations",
    6: "Business Travel",
    7: "Employee Commuting",
    8: "Upstream Leased Assets",
    9: "Downstream Transportation & Distribution",
    10: "Processing of Sold Products",
    11: "Use of Sold Products",
    12: "End-of-Life Treatment of Sold Products",
    13: "Downstream Leased Assets",
    14: "Franchises",
    15: "Investments",
}

# -----------------------------
# 2. EMISSION FACTOR DATABASES
# -----------------------------

EMISSION_FACTORS = {
    "EPA": {
        "Business Travel - Air Economy (kgCO2e/pkm)": 0.158,
        "Business Travel - Air Business (kgCO2e/pkm)": 0.244,
        "Business Travel - Hotel (kgCO2e/night)": 14.5,
        "Transport - Road Freight (kgCO2e/tonne-km)": 0.122,
        "Use Phase - US Grid Electricity (kgCO2e/kWh)": 0.387,
    },
    "DEFRA": {
        "Business Travel - Air Economy (kgCO2e/pkm)": 0.146,
        "Business Travel - Air Business (kgCO2e/pkm)": 0.231,
        "Business Travel - Hotel (kgCO2e/night)": 13.8,
        "Transport - HGV Freight (kgCO2e/tonne-km)": 0.096,
        "Use Phase - UK Grid Electricity (kgCO2e/kWh)": 0.193,
    },
}

FACTOR_SOURCES = {
    "EPA": "United States Environmental Protection Agency (EPA) - Emissions Factors Hub",
    "DEFRA": "UK Department for Environment, Food & Rural Affairs (DEFRA) - GHG Conversion Factors",
}

METHOD_HIERARCHY = {
    "Supplier-Specific": 5,
    "Activity-Based": 4,
    "Average-Data": 3,
    "Spend-Based": 2,
    "Proxy Estimate": 1,
}


# -----------------------------
# 3. CALCULATION ENGINE
# -----------------------------


def calculate_emissions(category_name: str, inputs: dict) -> tuple[float, str]:
    if category_name == "Business Travel":
        distance = inputs["distance_km"]
        travel_factor = inputs["travel_factor"]
        hotel_nights = inputs["hotel_nights"]
        hotel_factor = inputs["hotel_factor"]
        emissions = (distance * travel_factor) + (hotel_nights * hotel_factor)
        return emissions, "Activity-Based"

    if "Transportation" in category_name:
        distance = inputs["distance_km"]
        weight = inputs["weight_tonnes"]
        factor = inputs["transport_factor"]
        emissions = distance * weight * factor
        return emissions, "Activity-Based"

    if category_name == "Investments":
        company_emissions = inputs["investee_emissions"]
        outstanding_amount = inputs["outstanding_amount"]
        evic = inputs["evic"]
        attribution_factor = (outstanding_amount / evic) if evic else 0
        emissions = company_emissions * attribution_factor
        return emissions, "PCAF Financed Emissions"

    if category_name == "Use of Sold Products":
        lifetime_years = inputs["lifetime_years"]
        annual_usage = inputs["annual_usage_kwh"]
        grid_factor = inputs["grid_factor"]
        emissions = lifetime_years * annual_usage * grid_factor
        return emissions, "Activity-Based"

    emissions = inputs.get("quantity", 0) * inputs.get("generic_factor", 0)
    return emissions, inputs.get("method", "Average-Data")



def calculate_data_quality(method: str, activity_uncertainty_pct: float, factor_uncertainty_pct: float, coverage_pct: float) -> tuple[float, float]:
    hierarchy_score = METHOD_HIERARCHY.get(method, 1) / 5
    combined_uncertainty = math.sqrt(activity_uncertainty_pct**2 + factor_uncertainty_pct**2)
    uncertainty_score = max(0.0, 1 - (combined_uncertainty / 100))
    coverage_score = min(max(coverage_pct / 100, 0), 1)

    total_score = ((0.4 * hierarchy_score) + (0.3 * uncertainty_score) + (0.3 * coverage_score)) * 100
    return round(total_score, 1), round(combined_uncertainty, 2)


# -----------------------------
# 4. DATA ENTRY SECTION
# -----------------------------

st.sidebar.header("➕ Add Scope 3 Activity")

category = st.sidebar.selectbox("Select Category", list(CATEGORIES.values()))
factor_dataset = st.sidebar.selectbox("Emission Factor Source", list(EMISSION_FACTORS.keys()))
st.sidebar.caption(f"Source: {FACTOR_SOURCES[factor_dataset]}")

inputs = {}

if category == "Business Travel":
    st.sidebar.subheader("Business Travel Inputs")
    inputs["distance_km"] = st.sidebar.number_input("Travel distance (km)", min_value=0.0)
    travel_class = st.sidebar.selectbox("Travel class", ["Air Economy", "Air Business"])
    travel_key = f"Business Travel - {travel_class} (kgCO2e/pkm)"
    inputs["travel_factor"] = EMISSION_FACTORS[factor_dataset].get(travel_key, 0.0)
    if inputs["travel_factor"] == 0.0:
        st.sidebar.warning(f"Travel EF '{travel_key}' not found for source {factor_dataset}; using 0.0")
    st.sidebar.write(f"Travel EF: **{inputs['travel_factor']} kgCO2e/pkm**")

    inputs["hotel_nights"] = st.sidebar.number_input("Hotel nights", min_value=0.0)
    hotel_key = "Business Travel - Hotel (kgCO2e/night)"
    inputs["hotel_factor"] = EMISSION_FACTORS[factor_dataset].get(hotel_key, 0.0)
    if inputs["hotel_factor"] == 0.0:
        st.sidebar.warning(f"Hotel EF '{hotel_key}' not found for source {factor_dataset}; using 0.0")
    st.sidebar.write(f"Hotel EF: **{inputs['hotel_factor']} kgCO2e/night**")

elif "Transportation" in category:
    st.sidebar.subheader("Transport Inputs")
    inputs["distance_km"] = st.sidebar.number_input("Distance (km)", min_value=0.0)
    inputs["weight_tonnes"] = st.sidebar.number_input("Weight transported (tonnes)", min_value=0.0)

    transport_key = next((key for key in EMISSION_FACTORS[factor_dataset] if "Transport -" in key), None)
    if transport_key is None:
        inputs["transport_factor"] = 0.0
        st.sidebar.warning(f"No transport emission factor found for source {factor_dataset}; using 0.0")
        st.sidebar.write(f"Transport EF: **{inputs['transport_factor']} kgCO2e/tonne-km**")
    else:
        inputs["transport_factor"] = EMISSION_FACTORS[factor_dataset].get(transport_key, 0.0)
        st.sidebar.write(f"Transport EF ({transport_key.split(' - ')[1]}): **{inputs['transport_factor']} kgCO2e/tonne-km**")

elif category == "Investments":
    st.sidebar.subheader("Investments Inputs (PCAF)")
    st.sidebar.caption("Financed emissions = Investee emissions × (Outstanding amount / EVIC)")
    inputs["investee_emissions"] = st.sidebar.number_input("Investee emissions (kgCO2e)", min_value=0.0)
    inputs["outstanding_amount"] = st.sidebar.number_input("Outstanding amount invested (£)", min_value=0.0)
    inputs["evic"] = st.sidebar.number_input("Enterprise value including cash (EVIC) (£)", min_value=0.0)

elif category == "Use of Sold Products":
    st.sidebar.subheader("Use Phase Inputs")
    inputs["lifetime_years"] = st.sidebar.number_input("Product lifetime (years)", min_value=0.0)
    inputs["annual_usage_kwh"] = st.sidebar.number_input("Annual usage (kWh/year)", min_value=0.0)

    grid_key = next((key for key in EMISSION_FACTORS[factor_dataset] if "Grid Electricity" in key), None)
    if grid_key is None:
        inputs["grid_factor"] = 0.0
        st.sidebar.warning(f"No grid electricity factor found for source {factor_dataset}; using 0.0")
    else:
        inputs["grid_factor"] = EMISSION_FACTORS[factor_dataset].get(grid_key, 0.0)
    st.sidebar.write(f"Grid EF: **{inputs['grid_factor']} kgCO2e/kWh**")

else:
    st.sidebar.subheader("Generic Inputs")
    inputs["method"] = st.sidebar.selectbox("Calculation Method", list(METHOD_HIERARCHY.keys()))
    inputs["quantity"] = st.sidebar.number_input("Activity quantity", min_value=0.0)
    inputs["generic_factor"] = st.sidebar.number_input("Emission factor (kgCO2e/unit)", min_value=0.0)

st.sidebar.subheader("Data Quality")
quality_method = st.sidebar.selectbox("Method hierarchy", list(METHOD_HIERARCHY.keys()), index=1)
activity_uncertainty = st.sidebar.slider("Activity data uncertainty (%)", 0, 100, 20)
factor_uncertainty = st.sidebar.slider("Emission factor uncertainty (%)", 0, 100, 15)
coverage_pct = st.sidebar.slider("Data coverage (%)", 0, 100, 85)

add_button = st.sidebar.button("Add Entry")

if "data" not in st.session_state:
    st.session_state.data = pd.DataFrame(
        columns=[
            "Date",
            "Category",
            "Source",
            "Method",
            "Emissions (kgCO2e)",
            "Coverage (%)",
            "Combined Uncertainty (%)",
            "Data Quality Score",
            "Details",
        ]
    )

if add_button:
    emissions, calc_method = calculate_emissions(category, inputs)
    data_quality_score, combined_uncertainty = calculate_data_quality(
        quality_method,
        activity_uncertainty,
        factor_uncertainty,
        coverage_pct,
    )

    new_row = {
        "Date": datetime.now(),
        "Category": category,
        "Source": factor_dataset,
        "Method": calc_method,
        "Emissions (kgCO2e)": round(emissions, 2),
        "Coverage (%)": coverage_pct,
        "Combined Uncertainty (%)": combined_uncertainty,
        "Data Quality Score": data_quality_score,
        "Details": str(inputs),
    }
    st.session_state.data = pd.concat([st.session_state.data, pd.DataFrame([new_row])], ignore_index=True)
    st.success("Entry added successfully")

# -----------------------------
# 5. DASHBOARD DISPLAY
# -----------------------------

st.header("📊 Emissions Overview")

if not st.session_state.data.empty:
    total_emissions = st.session_state.data["Emissions (kgCO2e)"].sum()
    avg_quality = st.session_state.data["Data Quality Score"].mean()
    avg_coverage = st.session_state.data["Coverage (%)"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Scope 3 Emissions (kgCO2e)", round(total_emissions, 2))
    col2.metric("Total Scope 3 Emissions (tCO2e)", round(total_emissions / 1000, 2))
    col3.metric("Average Data Quality Score", f"{avg_quality:.1f}/100")

    st.progress(min(max(avg_coverage / 100, 0), 1), text=f"Average coverage: {avg_coverage:.1f}%")

    category_group = st.session_state.data.groupby("Category")["Emissions (kgCO2e)"].sum().reset_index()
    fig = px.pie(category_group, names="Category", values="Emissions (kgCO2e)", title="Emissions by Scope 3 Category")
    st.plotly_chart(fig, use_container_width=True)

    quality_by_category = (
        st.session_state.data.groupby("Category")[["Data Quality Score", "Combined Uncertainty (%)"]]
        .mean()
        .reset_index()
    )
    quality_fig = px.bar(
        quality_by_category,
        x="Category",
        y="Data Quality Score",
        color="Combined Uncertainty (%)",
        title="Data Quality by Category",
    )
    st.plotly_chart(quality_fig, use_container_width=True)

    st.subheader("Detailed Activity Data")
    st.dataframe(st.session_state.data)

    csv = st.session_state.data.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV Report", csv, "scope3_report.csv", "text/csv")
else:
    st.info("No data entered yet. Add entries from the sidebar.")
