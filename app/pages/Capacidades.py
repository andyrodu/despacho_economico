import streamlit as st
import pandas as pd
from pathlib import Path

st.title("Capacidades")
st.caption("Semana 1: estructura. Semana 3: conectar CSVs (capacidad por sistema y caso 2026).")

BASE_PATH = Path("data")
INPUTS = BASE_PATH / "inputs"
PROCESSED = BASE_PATH / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

archivo = st.selectbox(
    "Caso de capacidades",
    [
        ("Base (2024)", "capacity_2024_by_system.csv"),
        ("Caso 2026", "capacity_2026_case.csv"),
    ],
    format_func=lambda x: x[0],
)[1]

csv_path = INPUTS / archivo

if not csv_path.exists():
    st.error(f"No encontré {csv_path}. Crea el archivo en el repo (data/inputs/).")
    st.stop()

df = pd.read_csv(csv_path)

# Validación mínima de columnas esperadas
cols = {"system", "technology", "capacity_mw"}
if not cols.issubset(df.columns):
    st.error(f"El CSV debe tener columnas {sorted(list(cols))}. Encontré: {list(df.columns)}")
    st.stop()

sistema = st.selectbox("Sistema", ["SIN", "BCA", "BCS"])

df_sys = df[df["system"] == sistema].copy()

# ✅ Mostrar tabla SIN la columna system
df_display = df_sys[["technology", "capacity_mw"]].copy()

st.subheader("Tabla (editable)")
edited_display = st.data_editor(
    df_display,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "technology": st.column_config.TextColumn("technology"),
        "capacity_mw": st.column_config.NumberColumn("capacity_mw", min_value=0.0, step=10.0),
    },
)

# ✅ Re-agregar system para guardar/descargar
edited_full = edited_display.copy()
edited_full["system"] = sistema
edited_full = edited_full[["system", "technology", "capacity_mw"]]

col1, col2 = st.columns(2)

with col1:
    if st.button("Guardar cambios (processed)"):
        # Reintegrar cambios al df completo
        df_other = df[df["system"] != sistema].copy()
        df_out = pd.concat([df_other, edited_full], ignore_index=True)

        out_path = PROCESSED / f"{Path(archivo).stem}_edited.csv"
        df_out.to_csv(out_path, index=False)

        st.success(f"Guardado: {out_path}")

with col2:
    st.download_button(
        "Descargar CSV editado (solo este sistema)",
        data=edited_full.to_csv(index=False).encode("utf-8"),
        file_name=f"{sistema}_{Path(archivo).stem}.csv",
        mime="text/csv",
    )

st.info("Tip: Semana 3 pide que estas capacidades sean trazables (fuente oficial + supuestos 2026 documentados).")
