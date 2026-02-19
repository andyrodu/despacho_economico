import streamlit as st
import pandas as pd
from pathlib import Path

st.title("Capacidades")
st.caption("Semana 2: cargar/editar capacidades por sistema (SIN/BCA/BCS) con CSVs. Luego se reemplazan por datos reales.")

BASE_PATH = Path("data")
INPUTS = BASE_PATH / "inputs"
PROCESSED = BASE_PATH / "processed"
INPUTS.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

TECNOLOGIAS_BASE = [
    "Ciclo combinado",
    "Térmica convencional",
    "Hidro",
    "Eólica",
    "Solar",
    "Nuclear",
]

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
    st.error(f"No encontré {csv_path}. Créalo en el repo (data/inputs/).")
    st.stop()

df = pd.read_csv(csv_path)

cols = {"system", "technology", "capacity_mw"}
if not cols.issubset(df.columns):
    st.error(f"El CSV debe tener columnas {sorted(list(cols))}. Encontré: {list(df.columns)}")
    st.stop()

# Normalizar types
df["system"] = df["system"].astype(str).str.upper().str.strip()
df["technology"] = df["technology"].astype(str).str.strip()
df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce").fillna(0.0)

sistema = st.selectbox("Sistema", ["SIN", "BCA", "BCS"])

# --- Si faltan filas para ese sistema, generarlas automáticamente ---
df_sys = df[df["system"] == sistema].copy()

if df_sys.empty:
    st.info(f"No hay filas para {sistema}. Te genero plantilla base para que la llenes.")
    df_sys = pd.DataFrame(
        {"system": sistema, "technology": TECNOLOGIAS_BASE, "capacity_mw": 0.0}
    )

# Si hay filas pero faltan tecnologías, completar las faltantes
faltantes = [t for t in TECNOLOGIAS_BASE if t not in set(df_sys["technology"])]
if faltantes:
    df_missing = pd.DataFrame({"system": sistema, "technology": faltantes, "capacity_mw": 0.0})
    df_sys = pd.concat([df_sys, df_missing], ignore_index=True)

# Mostrar tabla SIN columna system (pero conservarla para guardar)
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

# Re-construir df completo para este sistema
edited_full = edited_display.copy()
edited_full["system"] = sistema
edited_full = edited_full[["system", "technology", "capacity_mw"]]

# Reintegrar al df total (quita sistema actual y pega versión editada)
df_other = df[df["system"] != sistema].copy()
df_out = pd.concat([df_other, edited_full], ignore_index=True)

# Orden bonito
df_out["system"] = df_out["system"].astype(str)
df_out = df_out.sort_values(["system", "technology"]).reset_index(drop=True)

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Guardar en server (data/processed)"):
        out_path = PROCESSED / f"{Path(archivo).stem}_edited.csv"
        df_out.to_csv(out_path, index=False)
        st.success(f"Guardado: {out_path}")

with col2:
    st.download_button(
        "Descargar (solo sistema)",
        data=edited_full.to_csv(index=False).encode("utf-8"),
        file_name=f"{sistema}_{Path(archivo).stem}.csv",
        mime="text/csv",
    )

with col3:
    st.download_button(
        "Descargar (completo)",
        data=df_out.to_csv(index=False).encode("utf-8"),
        file_name=f"{Path(archivo).stem}_edited.csv",
        mime="text/csv",
    )

st.info("Tip: En Semana 3-4 reemplazamos aproximados por fuentes oficiales y documentamos supuestos 2026.")
