import streamlit as st
import pandas as pd
import numpy as np

st.title("Demanda CENACE")
st.caption("Semana 1: placeholder. Semana 2: descarga y limpieza real de datos.")

st.markdown("""
**Objetivo:**
- Descargar demanda horaria (CENACE) para SIN / BCA / BCS
- Limpiar datos y dejarlos listos para el despacho
""")

sistema = st.selectbox("Sistema", ["SIN", "BCA", "BCS"])
dias = st.slider("Horizonte (días)", 1, 15, 7)

# Dummy demand series
hours = dias * 24
idx = pd.date_range("2026-01-01", periods=hours, freq="H")
demanda = 30000 + 5000*np.sin(np.linspace(0, 6*np.pi, hours)) + 1500*np.random.randn(hours)
df = pd.DataFrame({"timestamp": idx, "demanda_MW": demanda.clip(min=0)})

st.subheader("Vista previa (dummy)")
st.line_chart(df.set_index("timestamp")["demanda_MW"])

st.dataframe(df.head(10), use_container_width=True)

st.warning("En Semana 2 se reemplaza este dummy por descarga real desde CENACE (CSV/ZIP/API según corresponda).")
