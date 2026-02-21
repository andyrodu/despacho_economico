import streamlit as st
import pandas as pd
from pathlib import Path
import base64
import requests
from datetime import datetime

st.title("Capacidades")
st.caption("Semana 1: estructura. Semana 3: conectar CSVs (capacidad por sistema y caso 2026).")

# -----------------------------
# Paths
# -----------------------------
BASE_PATH = Path("data")
INPUTS = BASE_PATH / "inputs"
PROCESSED = BASE_PATH / "processed"
INPUTS.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

TECHS = ["Ciclo combinado", "Térmica convencional", "Hidro", "Eólica", "Solar", "Nuclear"]
SYSTEMS = ["SIN", "BCA", "BCS"]

# -----------------------------
# Helpers
# -----------------------------
def make_template(system: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "system": [system] * len(TECHS),
            "technology": TECHS,
            "capacity_mw": [0.0] * len(TECHS),
        }
    )

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    # Asegura columnas y tipos
    df = df.copy()
    df["system"] = df["system"].astype(str).str.upper().str.strip()
    df["technology"] = df["technology"].astype(str).str.strip()
    df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce").fillna(0.0)
    return df

def upsert_template_if_missing(df: pd.DataFrame) -> pd.DataFrame:
    # Si faltan sistemas, agrega plantilla para no dejar la tabla vacía
    df = df.copy()
    for s in SYSTEMS:
        if (df["system"] == s).sum() == 0:
            df = pd.concat([df, make_template(s)], ignore_index=True)
    return df

def github_put_file(owner: str, repo: str, path_in_repo: str, content_bytes: bytes, token: str, message: str):
    """
    Crea/actualiza archivo via GitHub Contents API.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path_in_repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 1) Obtener SHA si ya existe
    r_get = requests.get(api_url, headers=headers)
    sha = None
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")
    elif r_get.status_code not in (404,):
        raise RuntimeError(f"GitHub GET error {r_get.status_code}: {r_get.text}")

    # 2) PUT con contenido base64
    b64 = base64.b64encode(content_bytes).decode("utf-8")
    payload = {"message": message, "content": b64}
    if sha:
        payload["sha"] = sha

    r_put = requests.put(api_url, headers=headers, json=payload)
    if r_put.status_code not in (200, 201):
        raise RuntimeError(f"GitHub PUT error {r_put.status_code}: {r_put.text}")

    return r_put.json()

# -----------------------------
# UI: archivo/caso
# -----------------------------
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

# Validación mínima
cols = {"system", "technology", "capacity_mw"}
if not cols.issubset(df.columns):
    st.error(f"El CSV debe tener columnas {sorted(list(cols))}. Encontré: {list(df.columns)}")
    st.stop()

df = normalize_df(df)
df = upsert_template_if_missing(df)

sistema = st.selectbox("Sistema", SYSTEMS)

df_sys = df[df["system"] == sistema].copy()
if df_sys.empty:
    # (ya no debería pasar, pero por seguridad)
    st.warning(f"No hay filas para {sistema}. Te pongo plantilla para que la llenes.")
    df_sys = make_template(sistema)

# Mostramos sin "system"
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

# Reagregamos system para reconstruir el DF completo
edited_full = edited_display.copy()
edited_full["system"] = sistema
edited_full = edited_full[["system", "technology", "capacity_mw"]]
edited_full = normalize_df(edited_full)

# Reconstruir DF completo (otros sistemas + editado)
df_other = df[df["system"] != sistema].copy()
df_out = pd.concat([df_other, edited_full], ignore_index=True)

# Orden opcional (se ve más bonito)
df_out["system"] = pd.Categorical(df_out["system"], categories=SYSTEMS, ordered=True)
df_out["technology"] = pd.Categorical(df_out["technology"], categories=TECHS, ordered=True)
df_out = df_out.sort_values(["system", "technology"]).reset_index(drop=True)

# -----------------------------
# Outputs
# -----------------------------
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Guardar en server (data/processed)"):
        out_path = PROCESSED / f"{Path(archivo).stem}_edited.csv"
        df_out.to_csv(out_path, index=False, encoding="utf-8")
        st.success(f"Guardado local: {out_path}")

with col2:
    st.download_button(
        "Descargar (solo sistema)",
        data=edited_full.to_csv(index=False).encode("utf-8"),
        file_name=f"{sistema}_{Path(archivo).stem}_edited.csv",
        mime="text/csv",
    )

with col3:
    st.download_button(
        "Descargar (completo)",
        data=df_out.to_csv(index=False).encode("utf-8"),
        file_name=f"{Path(archivo).stem}_edited_all_systems.csv",
        mime="text/csv",
    )

st.divider()

# -----------------------------
# GitHub commit (Opción A)
# -----------------------------
st.subheader("Guardar directo al repo (GitHub commit)")

token = st.secrets.get("GITHUB_TOKEN", "")
owner = st.secrets.get("GITHUB_OWNER", "")
repo = st.secrets.get("GITHUB_REPO", "")

target_path_repo = f"data/processed/{Path(archivo).stem}_edited.csv"

if not (token and owner and repo):
    st.info("Configura Secrets: GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO para habilitar el commit por API.")
else:
    commit_msg_default = f"Update capacities ({Path(archivo).stem}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    commit_msg = st.text_input("Mensaje de commit", value=commit_msg_default)

    if st.button("Commit a GitHub (data/processed)"):
        try:
            content = df_out.to_csv(index=False).encode("utf-8")
            res = github_put_file(
                owner=owner,
                repo=repo,
                path_in_repo=target_path_repo,
                content_bytes=content,
                token=token,
                message=commit_msg,
            )
            st.success(f"Commit listo ✅ Archivo actualizado: {target_path_repo}")
        except Exception as e:
            st.error(f"Falló el commit: {e}")

st.info("Tip: Semana 3 pide que estas capacidades sean trazables (fuente oficial + supuestos 2026 documentados).")
