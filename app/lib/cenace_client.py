import streamlit as st
from datetime import datetime, date
from pathlib import Path

import pandas as pd

from app.lib.cenace_client import fetch_demand

st.title("Demanda CENACE")
st.caption("Semana 2: Demanda real CENACE (batch + cache + DST).")

CACHE_DIR = Path("data") / "cache"
OUT_DIR = Path("data") / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

system = st.selectbox("Sistema", ["SIN", "BCA", "BCS"])
start_date = st.date_input("Fecha inicio", value=date(2024, 2, 1))
days = st.slider("Duración (días, máx 30; se parte en bloques de 7)", 1, 30, 7)

if st.button("Descargar demanda"):
    with st.spinner("Descargando (con batching + caché)..."):
        df, q, blocks = fetch_demand(
            system=system,
            start=datetime.combine(start_date, datetime.min.time()),
            days=int(days),
            cache_dir=CACHE_DIR,
        )

    st.success(f"Listo. Filas: {q['rows']} | NaNs: {q['nans']} | Neg: {q['negatives']} | Duplicados: {q['duplicates']} | Missing hours: {q['missing_hours']}")

    st.subheader("Serie de demanda (MW)")
    st.line_chart(df["demand_mw"])

    st.subheader("Reporte de calidad (global)")
    st.json(q)

    st.subheader("Bloques (batching) y fuente")
    st.dataframe(pd.DataFrame([{
        "block_start": b["block_start"],
        "block_days": b["block_days"],
        "source": b["source"],
        "rows": b["quality"]["rows"],
        "nans": b["quality"]["nans"],
        "duplicates": b["quality"]["duplicates"],
        "missing_hours": b["quality"]["missing_hours"],
    } for b in blocks]), use_container_width=True)

    out_path = OUT_DIR / f"demand_{system}_{start_date}_{days}d.parquet"
    df.to_parquet(out_path, index=True)
    st.info(f"Guardado en: {out_path}")

    st.download_button(
        "Descargar CSV",
        data=df.reset_index().rename(columns={"index": "timestamp"}).to_csv(index=False).encode("utf-8"),
        file_name=f"demand_{system}_{start_date}_{days}d.csv",
        mime="text/csv",
    )
