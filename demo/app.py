"""Research dashboard: enrollment, Reddit, H-1B filings, and economy."""
from pathlib import Path
import sys
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DEMO_ROOT))
st.set_page_config(page_title="International Student Research", page_icon="🎓", layout="wide")
page = st.navigation([
    st.Page(str(DEMO_ROOT / "pages/1_enrollment.py"), title="Enrollment", icon="🎓", default=True),
    st.Page(str(DEMO_ROOT / "pages/2_discourse.py"), title="Reddit", icon="💬"),
    st.Page(str(DEMO_ROOT / "pages/3_h1b.py"), title="H-1B", icon="💼"),
    st.Page(str(DEMO_ROOT / "pages/4_economy.py"), title="Economy & policy", icon="📈"),
])
page.run()
