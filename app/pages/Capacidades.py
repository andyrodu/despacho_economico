import streamlit as st
import pandas as pd

st.title("Capacidades")
st.caption("Semana 1: estructura (placeholder). Aquí definiremos capacidades instaladas por tecnología.")

st.markdown("""
**Objetivo de esta página (MVP):**
- Elegir el sistema (SIN / BCA / BCS)
- Definir capacidades por tecnología (MW)
- Guardar la tabla para usarla en el despacho
""")

sistema = st.selectbox("Sistema", ["SIN", "BCA", "BCS"])

data = {
    "tecnologia": ["Ciclo combinado", "Térmica convencional", "Hidro", "Eólica", "Solar", "Nuclear"],
    "capacidad_MW": [30000, 15000, 12000, 9000, 12000, 1600],
}
df = pd.DataFrame(data)

st.subheader("Tabla base (editable)")
edited = st.data_editor(df, num_rows="fixed", use_container_width=True)

st.info("En Semana 2–3 esta tabla se conectará con datos reales / supuestos del proyecto.")
st.write("Vista previa:", edited)
