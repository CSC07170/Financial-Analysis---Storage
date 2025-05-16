import streamlit as st
import pandas as pd
import openai
import numpy as np

# --- SETUP ---
st.set_page_config(page_title="Financial AI Analysis", layout="wide")
st.title("📈 Monthly Real Estate Financial Analysis with AI")

# OpenAI API Key (optional: use secrets or env vars)
openai.api_key = st.secrets["openai_api_key"] if "openai_api_key" in st.secrets else "YOUR_API_KEY"

# --- FILE UPLOAD ---
uploaded_file = st.file_uploader("Upload your Excel financials (.xlsx)", type="xlsx")

if uploaded_file:
    xls = pd.ExcelFile(uploaded_file)

    # --- Load Sheets ---
    rolling_is = xls.parse("Rolling IS 7988", header=None)
    bva = xls.parse("BvA 7988", header=None)
    cash_flow = xls.parse("Cash Flow 7988", header=None)
    balance_sheet = xls.parse("Balance Sheet 7988", header=None)

    # --- Extract Revenue, Occupancy, Rent, Interest ---
    months = rolling_is.iloc[3, 3:].tolist()
    rental_income = rolling_is[rolling_is[2] == "Rental Income (4000)"].iloc[0, 3:].astype(float).values
    projected_rent = rolling_is[rolling_is[2] == "Projected Rent (9975)"].iloc[0, 3:].astype(float).values
    occupied_sf = rolling_is[rolling_is[2] == "Occupied Sq. Ft. (9955)"].iloc[0, 3:].astype(float).values
    sq_ft = rolling_is[rolling_is[2] == "Net Rentable Square Feet (9951)"].iloc[0, 3:].astype(float).values
    occupancy_pct = rolling_is[rolling_is[2] == "Sq. Ft. Occupancy (9960)"].iloc[0, 3:].astype(float).values
    interest_expense = rolling_is[rolling_is[2] == "Interest Expense (6015)"].iloc[0, 3:].astype(float).values if any(rolling_is[2] == "Interest Expense (6015)") else np.full(len(months), 10000)  # fallback

    # --- DSCR and Cash Flow from Ops ---
    op_cash_flow = cash_flow[cash_flow[2] == "Cash Provided By / (Used In) Operating Activities"].iloc[0, 3:].astype(float).values
    dscr = np.round(op_cash_flow / interest_expense, 2)

    # --- Reserves ---
    cash = balance_sheet[balance_sheet[2] == "Cash"].iloc[0, -1]
    escrow = balance_sheet[balance_sheet[2] == "Escrow/Earnest Money Deposits"].iloc[0, -1]
    reserves = float(cash) + float(escrow)

    # --- Time to Positive DSCR ---
    positive_dscr_idx = np.argmax(dscr > 1.0)
    months_to_dscr = positive_dscr_idx if dscr[positive_dscr_idx] > 1.0 else None
    cum_deficit = -np.cumsum(np.where(op_cash_flow < 0, op_cash_flow, 0))
    deficit_to_positive = cum_deficit[months_to_dscr] if months_to_dscr is not None else cum_deficit[-1]

    # --- GPT Narrative ---
    gpt_prompt = f"""
    Analyze this real estate financial performance:
    - Current month rental income: ${rental_income[-1]:,.0f}
    - MoM income change: {rental_income[-1] - rental_income[-2]:,.0f}
    - Current occupancy: {occupancy_pct[-1]:.1%}
    - MoM occupancy change: {(occupancy_pct[-1] - occupancy_pct[-2]):.1%}
    - DSCR this month: {dscr[-1]}
    - Cash reserves: ${reserves:,.0f}
    - Projected months to positive DSCR: {months_to_dscr if months_to_dscr is not None else 'Not within range'}
    - Total deficit before break-even: ${deficit_to_positive:,.0f}
    Do we have enough reserves to make it to break-even? What are the risks and recommendations?
    """

    with st.spinner("Generating AI Insights..."):
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": gpt_prompt}],
            temperature=0.5
        )
        insights = response['choices'][0]['message']['content']

    # --- Display Outputs ---
    st.subheader("📋 Summary KPIs")
    st.metric("Rental Income (latest)", f"${rental_income[-1]:,.0f}")
    st.metric("Occupancy (latest)", f"{occupancy_pct[-1]*100:.1f}%")
    st.metric("DSCR", f"{dscr[-1]}")
    st.metric("Cash Reserves", f"${reserves:,.0f}")
    st.metric("Months to Break-Even", months_to_dscr if months_to_dscr is not None else "> Range")
    st.metric("Funding Gap", f"${max(0, deficit_to_positive - reserves):,.0f}")

    st.subheader("🧠 AI Analysis")
    st.write(insights)

    st.subheader("📉 DSCR Over Time")
    st.line_chart(pd.DataFrame({"DSCR": dscr}, index=months))
