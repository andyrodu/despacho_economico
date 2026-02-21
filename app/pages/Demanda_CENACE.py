import streamlit as st
from datetime import datetime, date
from pathlib import Path
import pandas as pd
import sys

# ✅ Esto hace que Python vea la carpeta "app/" como raíz de imports
APP_DIR = Path(__file__).resolve().parents[1]   # .../app
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from lib.cenace_client import fetch_demand

st.title("Demanda CENACE")
st.caption("Semana 2: Demanda real CENACE (batch + cache + DST).")

CACHE_DIR = Path("data") / "cache"
OUT_DIR = Path("data") / "processed"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- UI
system = st.selectbox("Sistema", ["SIN", "BCA", "BCS"])
start_date = st.date_input("Fecha inicio", value=date(2024, 2, 1))
days = st.slider("Duración (días, máx 30; se parte en bloques de 7)", 1, 30, 7)

# ---- Estado (para que no se pierda la gráfica)
if "demand_df" not in st.session_state:
    st.session_state["demand_df"] = None
if "quality" not in st.session_state:
    st.session_state["quality"] = None
if "blocks" not in st.session_state:
    st.session_state["blocks"] = None
if "last_meta" not in st.session_state:
    st.session_state["last_meta"] = None

# ---- Acción
if st.button("Descargar demanda"):
    with st.spinner("Descargando (con batching + caché)..."):
        df, q, blocks = fetch_demand(
            system=system,
            start=datetime.combine(start_date, datetime.min.time()),
            days=int(days),
            cache_dir=CACHE_DIR,
        )

    # Normalizar índice para graficar bonito
    if df is not None and not df.empty:
        # Si el índice no es datetime, lo intentamos convertir
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass
        df = df.sort_index()

    st.session_state["demand_df"] = df
    st.session_state["quality"] = q
    st.session_state["blocks"] = blocks
    st.session_state["last_meta"] = {"system": system, "start_date": start_date, "days": int(days)}

# ---- Render SIEMPRE (si ya hay algo descargado)
df = st.session_state["demand_df"]
q = st.session_state["quality"]
blocks = st.session_state["blocks"]
meta = st.session_state["last_meta"]

if df is None:
    st.info("Pica **Descargar demanda** para traer datos y ver la gráfica.")
else:
    if df.empty:
        st.warning("Se descargó, pero el dataframe viene vacío. Revisa logs / endpoint / sistema-fecha.")
    else:
        st.success(
            f"Listo ({meta['system']} | {meta['start_date']} | {meta['days']} días). "
            f"Filas: {q.get('rows')} | NaNs: {q.get('nans')} | Neg: {q.get('negatives')} | "
            f"Duplicados: {q.get('duplicates')} | Missing hours: {q.get('missing_hours')}"
        )

        # ✅ Gráfica
        st.subheader("Serie de demanda (MW)")
        if "demand_mw" not in df.columns:
            st.error(f"No encuentro columna 'demand_mw'. Columnas disponibles: {list(df.columns)}")
        else:
            st.line_chart(df[["demand_mw"]])

        # Preview rápido para validar que sí hay datos
        with st.expander("Ver preview (head/tail)"):
            st.write("Head:")
            st.dataframe(df.head(10), use_container_width=True)
            st.write("Tail:")
            st.dataframe(df.tail(10), use_container_width=True)

        # Calidad
        st.subheader("Reporte de calidad (global)")
        st.json(q)

        # Bloques
        st.subheader("Bloques (batching) y fuente")
        if blocks:
            st.dataframe(
                pd.DataFrame([{
                    "block_start": b.get("block_start"),
                    "block_days": b.get("block_days"),
                    "source": b.get("source"),
                    "rows": b.get("quality", {}).get("rows"),
                    "nans": b.get("quality", {}).get("nans"),
                    "duplicates": b.get("quality", {}).get("duplicates"),
                    "missing_hours": b.get("quality", {}).get("missing_hours"),
                } for b in blocks]),
                use_container_width=True,
            )

        # Guardar en server
        out_path = OUT_DIR / f"demand_{meta['system']}_{meta['start_date']}_{meta['days']}d.parquet"
        try:
            df.to_parquet(out_path, index=True)
            st.info(f"Guardado en server: {out_path}")
        except Exception as e:
            st.warning(f"No pude guardar parquet: {e}")

        # Descargar CSV
        st.download_button(
            "Descargar CSV",
            data=df.reset_index().rename(columns={"index": "timestamp"}).to_csv(index=False).encode("utf-8"),
            file_name=f"demand_{meta['system']}_{meta['start_date']}_{meta['days']}d.csv",
            mime="text/csv",
        )

