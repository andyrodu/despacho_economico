import base64
import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st


# ----------------------------
# CONFIG / PATHS
# ----------------------------
st.title("Capacidades")
st.caption("Semana 1: estructura. Semana 3: conectar CSVs (capacidad por sistema y caso 2026).")

BASE_PATH = Path("data")
INPUTS = BASE_PATH / "inputs"
PROCESSED = BASE_PATH / "processed"
INPUTS.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

DEFAULT_TECHS = [
    "Ciclo combinado",
    "Térmica convencional",
    "Hidro",
    "Eólica",
    "Solar",
    "Nuclear",
]

# ----------------------------
# GITHUB COMMIT HELPERS
# ----------------------------
def _get_secret(name: str, default=None):
    # Permite correr local sin secrets (no truena)
    return st.secrets.get(name, default) if hasattr(st, "secrets") else default


GITHUB_TOKEN = _get_secret("GITHUB_TOKEN", None)
GITHUB_OWNER = _get_secret("GITHUB_OWNER", None)
GITHUB_REPO = _get_secret("GITHUB_REPO", None)
GITHUB_BRANCH = _get_secret("GITHUB_BRANCH", "main")


def github_put_file(
    *,
    owner: str,
    repo: str,
    branch: str,
    token: str,
    path_in_repo: str,
    content_bytes: bytes,
    commit_message: str,
):
    """
    Crea/actualiza un archivo en GitHub usando Contents API.
    """
    if not all([owner, repo, branch, token]):
        raise ValueError("Faltan secrets de GitHub (OWNER/REPO/BRANCH/TOKEN).")

    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path_in_repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    # 1) Revisar si existe para obtener SHA
    sha = None
    r_get = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=30)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")
    elif r_get.status_code in (404,):
        sha = None
    else:
        raise RuntimeError(f"GitHub GET error {r_get.status_code}: {r_get.text}")

    # 2) Hacer PUT con base64 content
    b64 = base64.b64encode(content_bytes).decode("utf-8")
    payload = {
        "message": commit_message,
        "content": b64,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r_put = requests.put(api_url, headers=headers, data=json.dumps(payload), timeout=30)
    if r_put.status_code not in (200, 201):
        raise RuntimeError(f"GitHub PUT error {r_put.status_code}: {r_put.text}")

    return r_put.json()


# ----------------------------
# UI: SELECT CASE / LOAD DATA
# ----------------------------
case_label, archivo = st.selectbox(
    "Caso de capacidades",
    [
        ("Base (2024)", "capacity_2024_by_system.csv"),
        ("Caso 2026", "capacity_2026_case.csv"),
    ],
    format_func=lambda x: x[0],
)

csv_path = INPUTS / archivo

if csv_path.exists():
    df = pd.read_csv(csv_path)
else:
    st.warning(f"No encontré {csv_path}. Te muestro una plantilla para que puedas llenar y guardar/commitear.")
    df = pd.DataFrame(
        {
            "system": ["SIN"] * len(DEFAULT_TECHS),
            "technology": DEFAULT_TECHS,
            "capacity_mw": [0.0] * len(DEFAULT_TECHS),
        }
    )

required = {"system", "technology", "capacity_mw"}
if not required.issubset(df.columns):
    st.error(f"El CSV debe tener columnas {sorted(list(required))}. Encontré: {list(df.columns)}")
    st.stop()

df["system"] = df["system"].astype(str).str.strip().str.upper()
df["technology"] = df["technology"].astype(str).str.strip()
df["capacity_mw"] = pd.to_numeric(df["capacity_mw"], errors="coerce").fillna(0.0)

sistema = st.selectbox("Sistema", ["SIN", "BCA", "BCS"])

df_sys = df[df["system"] == sistema].copy()
if df_sys.empty:
    st.info(f"No hay filas para {sistema}. Te pongo plantilla para que la llenes.")
    df_sys = pd.DataFrame(
        {"system": [sistema] * len(DEFAULT_TECHS), "technology": DEFAULT_TECHS, "capacity_mw": [0.0] * len(DEFAULT_TECHS)}
    )

# Mostrar sin system
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

# Reconstruir con system
edited_full = edited_display.copy()
edited_full["system"] = sistema
edited_full = edited_full[["system", "technology", "capacity_mw"]]

df_other = df[df["system"] != sistema].copy()
df_out = pd.concat([df_other, edited_full], ignore_index=True)

# ----------------------------
# BUTTONS: SAVE LOCAL + DOWNLOAD + COMMIT
# ----------------------------
col1, col2, col3 = st.columns(3)

# A) Guardar (server local / cloud filesystem)
with col1:
    if st.button("Guardar en server (data/processed)"):
        out_path = PROCESSED / f"{Path(archivo).stem}_edited.csv"
        df_out.to_csv(out_path, index=False)
        st.success(f"Guardado en: {out_path}")

# B) Descargar CSVs
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
        file_name=f"{Path(archivo).stem}_FULL.csv",
        mime="text/csv",
    )

st.divider()

# C) Commit a GitHub
st.subheader("Guardar directo al repo (GitHub commit)")

# Puedes cambiar la carpeta destino en el repo aquí:
# - "data/processed/..." (recomendado)
# - o "data/inputs/..." si quieres que “alimente” la app como input
dest_folder = st.selectbox("Carpeta destino en el repo", ["data/processed", "data/inputs"], index=0)

commit_filename = f"{Path(archivo).stem}_edited.csv"
path_in_repo = f"{dest_folder}/{commit_filename}"

commit_msg = st.text_input(
    "Mensaje de commit",
    value=f"Update capacidades {case_label} - {sistema}",
)

if not (GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO):
    st.warning("Faltan secrets de GitHub. Configura GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO (y opcional GITHUB_BRANCH).")
else:
    if st.button("✅ Commit a GitHub ahora"):
        try:
            csv_bytes = df_out.to_csv(index=False).encode("utf-8")
            resp = github_put_file(
                owner=GITHUB_OWNER,
                repo=GITHUB_REPO,
                branch=GITHUB_BRANCH,
                token=GITHUB_TOKEN,
                path_in_repo=path_in_repo,
                content_bytes=csv_bytes,
                commit_message=commit_msg,
            )
            commit_url = resp.get("commit", {}).get("html_url", "")
            st.success(f"Listo: commiteado en `{path_in_repo}` en branch `{GITHUB_BRANCH}`.")
            if commit_url:
                st.write(commit_url)
        except Exception as e:
            st.error(f"Error haciendo commit: {e}")

st.info("Tip: Semana 3 pide que estas capacidades sean trazables (fuente oficial + supuestos 2026 documentados).")
