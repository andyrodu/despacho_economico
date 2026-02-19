import streamlit as st

st.title("Escenarios")
st.caption("Semana 1: estructura. Aquí definiremos casos base vs 2026 y comparaciones.")

st.markdown("""
**Objetivo:**
- Seleccionar escenario base (hoy) vs escenario 2026
- Ajustar supuestos (capacidad, costos)
- Comparar resultados del despacho
""")

esc = st.selectbox("Escenario", ["Base (hoy)", "2026 (proyección)", "Alta renovable", "Gas caro"])

st.info(f"Escenario seleccionado: **{esc}**")
st.write("En Semana 7–9 aquí aparecerá la comparación de resultados entre escenarios.")
