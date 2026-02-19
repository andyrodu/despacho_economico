import os
from pathlib import Path

import pandas as pd
import streamlit as st


# =========================
# Config
# =========================
st.title("Capacidades")
st.caption("Semana 3: capacidades reales + caso 2026 (CSV)")

BASE_DIR = Path(__file__).resolve().parents[2]  # .../despacho_economico
DATA_DIR = BASE_DIR / "data"
INPUTS_DIR = DATA_DIR / "inputs"
PROCESSED_DIR = DATA_DIR / "processed"
DOCS_DIR = BASE_DIR / "docs"

INPUTS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

FILE_2024 = INPUTS_DIR / "capacity_2024_by_system.csv"
FILE_2026 = PROCESSED_DIR / "capacity_2026_case.csv"
ASSUMPTIONS_MD = DOCS_DIR / "growth_assumptions.md"

VALID_SYSTEMS = ["SIN", "BCA", "BCS"]

# Puedes cambiar/expandir estas tecnologías (pero mantenlas consistentes en todo el proyecto)
TECH_DEFAULT = [
    "Ciclo combinado",
    "Térmica convencional",
    "Hidro",
    "Eólica",
    "Solar",
    "Nuclear",
]

DEFAULT_CAP_MW = [30000, 15000, 12000, 9000, 12000, 1600]


# =========================
# Helpers
# =========================
def default_df(system: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "system": [system] * len(TECH_DEFAULT),
            "technology": TECH_DEFAULT,
            "capacity_mw": DEFAULT_CAP_MW,
        }
    )


def load_2024(system: str) -> pd.DataFrame:
    if FILE_2024.exists():
        df_all = pd.read_csv(FILE_2024)
        # normaliza columnas esperadas
        expected = {"system", "technology", "capacity_mw"}
        if not expected.issubset(set(df_all.columns)):
            st.error(f"El archivo {FILE_2024.name} no tiene columnas {expected}.")
            return default_df(system)

        df_sys = df_all[df_all["system"] == system].copy()
        if df_sys.empty:
            return default_df(system)

        # Asegura tipos
        df_sys["capacity_mw"] = pd.to_numeric(df_sys["capacity_mw"], errors="coerce").fillna(0.0)
        df_sys["technology"] = df_sys["technology"].astype(str)
        df_sys["system"] = df_sys["system"].astype(str)
        return df_sys[["system", "technology", "capacity_mw"]].reset_index(drop=True)

    return default_df(system)


def validate_df(df: pd.DataFrame) -> list[str]:
    issues = []
    expected_cols = ["system", "technology", "capacity_mw"]
    for c in expected_cols:
        if c not in df.columns:
            issues.append(f"Falta columna: {c}")

    if issues:
        return issues

    # sistemas válidos
    bad_sys = df[~df["system"].isin(VALID_SYSTEMS)]
    if not bad_sys.empty:
        issues.append("Hay filas con 'system' inválido (debe ser SIN/BCA/BCS).")

    # technology no vacía
    if df["technology"].astype(str).str.strip().eq("").any():
        issues.append("Hay filas con 'technology' vacía.")

    # capacity numérica y no negativa
    cap = pd.to_numeric(df["capacity_mw"], errors="coerce")
    if cap.isna().any():
        issues.append("Hay valores en 'capacity_mw' que no son numéricos.")
    if (cap.fillna(0) < 0).any():
        issues.append("Hay valores negativos en 'capacity_mw'.")

    return issues


def save_2024(df_system: pd.DataFrame, system: str):
    # guarda/actualiza solo ese sistema dentro del CSV global
    if FILE_2024.exists():
        df_all = pd.read_csv(FILE_2024)
        df_all = df_all[df_all["system"] != system].copy()
        df_out = pd.concat([df_all, df_system], ignore_index=True)
    else:
        df_out = df_system.copy()

    df_out = df_out[["system", "technology", "capacity_mw"]].copy()
    df_out.to_csv(FILE_2024, index=False)


def generate_2026(df_2024_sys: pd.DataFrame, growth_map: dict[str, float]) -> pd.DataFrame:
    df = df_2024_sys.copy()
    df["growth_rate"] = df["technology"].map(growth_map).fillna(0.0)
    df["capacity_mw_2026"] = (df["capacity_mw"] * (1.0 + df["growth_rate"])).round(3)

    # Formato final para el CSV 2026
    out = df[["system", "technology", "capacity_mw_2026"]].rename(columns={"capacity_mw_2026": "capacity_mw"})
    return out


def upsert_2026(df_2026_sys: pd.DataFrame, system: str):
    if FILE_2026.exists():
        df_all = pd.read_csv(FILE_2026)
        df_all = df_all[df_all["system"] != system].copy()
        df_out = pd.concat([df_all, df_2026_sys], ignore_index=True)
    else:
        df_out = df_2026_sys.copy()

    df_out = df_out[["system", "technology", "capacity_mw"]].copy()
    df_out.to_csv(FILE_2026, index=False)


# =========================
# UI
# =========================
st.markdown(
    """
**Objetivo (Semana 3):**
- Definir capacidades 2024 por sistema (SIN / BCA / BCS)
- Guardarlas en `data/inputs/capacity_2024_by_system.csv`
- Generar caso 2026 en `data/processed/capacity_2026_case.csv`
- Documentar supuestos en `docs/growth_assumptions.md`
"""
)

system = st.selectbox("Sistema", VALID_SYSTEMS, index=0)

st.divider()
st.subheader("1) Capacidades 2024 (editable)")

df_2024 = load_2024(system)

edited_2024 = st.data_editor(
    df_2024,
    num_rows="fixed",
    use_container_width=True,
    hide_index=True,
    column_config={
        "system": st.column_config.TextColumn(disabled=True),
        "technology": st.column_config.TextColumn("technology"),
        "capacity_mw": st.column_config.NumberColumn("capacity_mw (MW)", min_value=0.0, step=10.0),
    },
)

issues_2024 = validate_df(edited_2024)

colA, colB, colC = st.columns([1, 1, 2])

with colA:
    if st.button("Guardar 2024 (CSV)"):
        if issues_2024:
            st.error("No se puede guardar. Corrige esto:")
            for i in issues_2024:
                st.write(f"- {i}")
        else:
            save_2024(edited_2024, system)
            st.success(f"Guardado: {FILE_2024}")

with colB:
    st.download_button(
        "Descargar CSV 2024",
        data=edited_2024.to_csv(index=False).encode("utf-8"),
        file_name=f"capacity_2024_{system}.csv",
        mime="text/csv",
    )

with colC:
    total_2024 = pd.to_numeric(edited_2024["capacity_mw"], errors="coerce").fillna(0).sum()
    st.metric("Total 2024 (MW)", f"{total_2024:,.0f}")

if issues_2024:
    st.warning("Ojo: hay detalles en tu tabla 2024.")
    for i in issues_2024:
        st.write(f"- {i}")
else:
    st.info("Tabla 2024 OK ✅")

st.divider()
st.subheader("2) Supuestos de crecimiento a 2026 (por tecnología)")

st.caption("Define un % para cada tecnología. Ej: 0.10 = +10%, -0.05 = -5%.")

# crecimiento por tecnología
growth_map = {}
for tech in edited_2024["technology"].tolist():
    default = 0.0
    growth_map[tech] = st.number_input(
        f"Crecimiento 2026 para: {tech}",
        value=float(default),
        step=0.01,
        format="%.3f",
    )

st.markdown("**Generación 2026**: `capacity_2026 = capacity_2024 * (1 + growth_rate)`")

col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    if st.button("Generar 2026"):
        if issues_2024:
            st.error("Primero corrige 2024 antes de generar 2026.")
        else:
            df_2026_sys = generate_2026(edited_2024, growth_map)
            issues_2026 = validate_df(df_2026_sys)

            if issues_2026:
                st.error("Tu 2026 salió con problemas:")
                for i in issues_2026:
                    st.write(f"- {i}")
            else:
                upsert_2026(df_2026_sys, system)
                st.success(f"Guardado: {FILE_2026}")

with col2:
    # preview local para descargar aunque no guardes
    if issues_2024:
        df_2026_preview = pd.DataFrame(columns=["system", "technology", "capacity_mw"])
    else:
        df_2026_preview = generate_2026(edited_2024, growth_map)

    st.download_button(
        "Descargar CSV 2026",
        data=df_2026_preview.to_csv(index=False).encode("utf-8"),
        file_name=f"capacity_2026_{system}.csv",
        mime="text/csv",
        disabled=df_2026_preview.empty,
    )

with col3:
    if not df_2026_preview.empty:
        total_2026 = pd.to_numeric(df_2026_preview["capacity_mw"], errors="coerce").fillna(0).sum()
        st.metric("Total 2026 (MW)", f"{total_2026:,.0f}")

st.subheader("Vista previa 2026")
st.dataframe(df_2026_preview, use_container_width=True, hide_index=True)

st.divider()
st.subheader("3) growth_assumptions.md (documentación)")

default_md = """# Growth assumptions (2024 -> 2026)

## Fuentes
- (Pega aquí fuentes: PRODESEN, CENACE, IEA, etc.)

## Supuestos
- Explica por qué elegiste los crecimientos por tecnología.
- Aclara si es por sistema (SIN/BCA/BCS) o general.
- Unidades: MW.

## Notas
- Este archivo se usará para justificar el caso 2026.
"""

if not ASSUMPTIONS_MD.exists():
    ASSUMPTIONS_MD.write_text(default_md, encoding="utf-8")

md_text = ASSUMPTIONS_MD.read_text(encoding="utf-8")
md_new = st.text_area("Editar growth_assumptions.md", value=md_text, height=240)

if st.button("Guardar growth_assumptions.md"):
    ASSUMPTIONS_MD.write_text(md_new, encoding="utf-8")
    st.success(f"Guardado: {ASSUMPTIONS_MD}")

st.caption("Tip: después de guardar, haz commit/push para que quede en GitHub/Streamlit.")
