"""Three-page research dashboard: enrollment, discourse, and post-study work."""
from pathlib import Path
import sys
import streamlit as st

CODE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE_ROOT))
st.set_page_config(page_title="International Student Research", page_icon="🎓", layout="wide")
page = st.navigation([
    st.Page(str(CODE_ROOT / "pages/1_enrollment.py"), title="Enrollment", icon="🎓", default=True),
    st.Page(str(CODE_ROOT / "pages/2_discourse.py"), title="YouTube and Reddit", icon="💬"),
    st.Page(str(CODE_ROOT / "pages/3_h1b.py"), title="H-1B", icon="💼"),
])
page.run()
