import streamlit as st

st.title("Despacho PyPSA")
st.caption("Semana 1: placeholder. Semana 4: modelo PyPSA funcionando.")

st.markdown("""
**Objetivo:**
- Construir la red PyPSA (generadores + carga)
- Ejecutar el despacho económico
- Mostrar resultados (generación, costo, precio marginal)
""")

st.subheader("Parámetros (placeholder)")
st.slider("Costo variable - Ciclo combinado ($/MWh)", 0, 2000, 900, step=50)
st.slider("Costo variable - Térmica convencional ($/MWh)", 0, 3000, 1400, step=50)

run = st.button("Correr despacho (Semana 1: no ejecuta)")

if run:
    st.info("En Semana 4 este botón ejecutará PyPSA y aquí aparecerán gráficas/tablas.")
else:
    st.write("Listo para conectar capacidades + demanda en las próximas semanas.")
