import streamlit as st
import pandas as pd
from pathlib import Path

st.title("Capacidades")
st.caption("Semana 1: estructura. Semana 3: conectar CSVs (capacidad por sistema y caso 2026).")

BASE_PATH = Path("data")
INPUTS = BASE_PATH / "inputs"
PROCESSED = BASE_PATH / "processed"
INPUTS.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

# Tecnologías base (ajústalas si tu profe pide otras)
DEFAULT_TECHS = [
    "Ciclo combinado",
    "Térmica convencional",
    "Hidro",
    "Eólica",
    "Solar",
    "Nuclear",
]

# 1) Selección del caso (archivo)
case_label, archivo = st.selectbox(
    "Caso de capacidades",
    [
        ("Base (2024)", "capacity_2024_by_system.csv"),
        ("Caso 2026", "capacity_2026_case.csv"),
    ],
    format_func=lambda x: x[0],
)

csv_path = INPUTS / archivo

# 2) Cargar o crear plantilla si no existe
if csv_path.exists():
    df = pd.read_csv(csv_path)
else:
    st.warning(f"No encontré {csv_path}. Te muestro una plantilla para que puedas llenar y descargar/guardar.")
    df = pd.DataFrame(
        {
            "system": ["SIN"] * len(DEFAULT_TECHS),
            "technology": DEFAULT_TECHS,
            "capacity_mw": [0.0] * len(DEFAULT_TECHS),
        }
    )

# 3) Validación mínima de columnas
required = {"system", "technology", "capacity_mw"}
if not required.issubset(df.columns):
    st.error(f"El CSV debe tener columnas {sorted(list(required))}. Encontré: {list(df.columns)}")
    st.stop()

# Normalizamos tipos / texto
df["system"] = df["system"].astype(str).str.strip().str.upper()
df["technology"] = df["technology"].astype(str).str.strip()
df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce").fillna(0.0)

# 4) Selección del sistema
sistema = st.selectbox("Sistema", ["SIN", "BCA", "BCS"])

df_sys = df[df["system"] == sistema].copy()

# Si no hay filas para ese sistema, creamos plantilla
if df_sys.empty:
    st.info(f"No hay filas para {sistema} en este archivo. Te pongo una plantilla para que la llenes.")
    df_sys = pd.DataFrame(
        {"system": [sistema] * len(DEFAULT_TECHS), "technology": DEFAULT_TECHS, "capacity_mw": [0.0] * len(DEFAULT_TECHS)}
    )

# 5) Mostrar tabla SIN la columna system
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

# 6) Reconstruir dataframe completo (reagregando system)
edited_full = edited_display.copy()
edited_full["system"] = sistema
edited_full = edited_full[["system", "technology", "capacity_mw"]]

# 7) Reintegrar al df total (quitando el sistema actual y pegando editado)
df_other = df[df["system"] != sistema].copy()
df_out = pd.concat([df_other, edited_full], ignore_index=True)

col1, col2 = st.columns(2)

with col1:
    if st.button("Guardar cambios (a data/processed)"):
        out_path = PROCESSED / f"{Path(archivo).stem}_edited.csv"
        df_out.to_csv(out_path, index=False)
        st.success(f"Guardado en: {out_path}")

with col2:
    st.download_button(
        "Descargar CSV (solo este sistema)",
        data=edited_full.to_csv(index=False).encode("utf-8"),
        file_name=f"{sistema}_{Path(archivo).stem}.csv",
        mime="text/csv",
    )

st.download_button(
    "Descargar CSV (completo: SIN+BCA+BCS)",
    data=df_out.to_csv(index=False).encode("utf-8"),
    file_name=f"{Path(archivo).stem}_FULL.csv",
    mime="text/csv",
)

st.info("Tip: Semana 3 pide que estas capacidades sean trazables (fuente oficial + supuestos 2026 documentados).")
