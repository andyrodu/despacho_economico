import streamlit as st

st.title("Limitaciones")
st.caption("Transparencia del simulador: qué simplifica y qué no modela todavía.")

st.markdown("""
**Limitaciones actuales (Semana 1):**
- No hay descarga real de demanda todavía (solo dummy/local)
- No hay capacidades reales por tecnología aún
- No corre PyPSA (solo interfaz)
- No hay restricciones de red (congestión), rampas, reservas, etc.

**Se agregará en semanas posteriores:**
- Datos reales de CENACE (Semana 2)
- Capacidades y supuestos por tecnología (Semana 3)
- Despacho PyPSA (Semana 4)
- Escenarios y sensibilidad (Semana 7–9)
""")
