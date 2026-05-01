import os

import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    try:
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY", "")
    except Exception:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")

    if not url or not key:
        raise ValueError(
            "SUPABASE_URL et SUPABASE_KEY sont requis.\n"
            "Configure-les dans le dashboard Streamlit Cloud (Secrets) ou dans ton .env local."
        )

    return create_client(url, key)
