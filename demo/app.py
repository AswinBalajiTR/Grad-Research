"""Five-page research dashboard: research question, enrollment, discourse, work, and economy."""
from pathlib import Path
import sys
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DEMO_ROOT))
st.set_page_config(page_title="International Student Research", layout="wide")
page = st.navigation([
    st.Page(str(DEMO_ROOT / "pages/0_research.py"), title="Research question", default=True),
    st.Page(str(DEMO_ROOT / "pages/1_enrollment.py"), title="Enrollment"),
    st.Page(str(DEMO_ROOT / "pages/2_discourse.py"), title="Reddit"),
    st.Page(str(DEMO_ROOT / "pages/3_h1b.py"), title="H-1B"),
    st.Page(str(DEMO_ROOT / "pages/4_economy.py"), title="Economy & Policy"),
])
page.run()
