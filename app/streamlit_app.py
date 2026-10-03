"""
Northwind People Analytics - Streamlit front end.

Run it with:   streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.views import dashboard, data_entry
from src.db_manager import DatabaseConnection, DatabaseError
from src.managers import EtlManager

st.set_page_config(page_title="People Analytics", page_icon="📊", layout="wide")

if not DatabaseConnection().ping():
    st.error("I can't reach the MySQL server. Check your .env file (local) or the app's Secrets (cloud), "
             "then reload this page.")
    st.stop()

st.sidebar.title("People Analytics")
page = st.sidebar.radio("Go to", ["Analytics dashboard", "Data entry"], label_visibility="collapsed")

with st.sidebar.expander("Warehouse tools"):
    st.caption("Changes made in Data entry are pushed to the warehouse automatically. "
               "Use this only after bulk-loading data outside the app.")
    if st.button("Rebuild warehouse from OLTP"):
        try:
            with st.spinner("Running the full ETL... this takes about 10-20 seconds."):
                EtlManager().run_full_etl()
            st.cache_data.clear()
            st.success("Warehouse refreshed.")
        except DatabaseError as err:
            st.error(str(err))

if page == "Analytics dashboard":
    dashboard.render()
else:
    data_entry.render()
