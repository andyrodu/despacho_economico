from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests


CENACE_URL = "https://www.cenace.gob.mx/GraficaDemanda.aspx/obtieneValoresTotal"


@dataclass
class FetchResult:
    df: pd.DataFrame
    source: str  # "api" or "cache"


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _cache_path(cache_dir: Path, system: str, start: datetime, end: datetime) -> Path:
    s = start.strftime("%Y%m%d")
    e = end.strftime("%Y%m%d")
    return cache_dir / f"demand_{system}_{s}_{e}.parquet"


def _find_series(payload: Any) -> Tuple[List[Any], List[Any]]:
    """
    Intenta encontrar (timestamps, values) en respuestas típicas.
    - A veces viene como dict con llaves 'd' (ASP.NET) o 'Data' o 'Series'
    - timestamps pueden venir como strings o epoch/ms
    """
    # Unwrap ASP.NET style: {"d": "...json..."} o {"d": {...}}
    if isinstance(payload, dict) and "d" in payload:
        d = payload["d"]
        try:
            payload = json.loads(d) if isinstance(d, str) else d
        except Exception:
            payload = d

    # Si es string JSON
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            pass

    # Helper: busca listas numéricas y listas de fechas
    def looks_like_dates(xs: List[Any]) -> bool:
        if not xs:
            return False
        sample = xs[: min(5, len(xs))]
        ok = 0
        for x in sample:
            if isinstance(x, (int, float)):
                ok += 1  # epoch-ish, lo parseamos luego
            elif isinstance(x, str):
                ok += 1
        return ok == len(sample)

    def looks_like_values(xs: List[Any]) -> bool:
        if not xs:
            return False
        sample = xs[: min(5, len(xs))]
        return all(isinstance(x, (int, float)) for x in sample)

    # Candidatos: (dates, values)
    candidates: List[Tuple[List[Any], List[Any]]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            # patrones comunes
            for k1, k2 in [
                ("timestamps", "values"),
                ("fechas", "valores"),
                ("x", "y"),
                ("X", "Y"),
                ("categories", "data"),
                ("labels", "data"),
            ]:
                if k1 in obj and k2 in obj and isinstance(obj[k1], list) and isinstance(obj[k2], list):
                    candidates.append((obj[k1], obj[k2]))

            # series list: [{"data":[...], "name":...}, ...] + categories
            if "series" in obj and "categories" in obj and isinstance(obj["series"], list) and isinstance(obj["categories"], list):
                cats = obj["categories"]
                for s in obj["series"]:
                    if isinstance(s, dict) and "data" in s and isinstance(s["data"], list):
                        candidates.append((cats, s["data"]))

            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            # lista de dicts con timestamp/value
            if obj and all(isinstance(x, dict) for x in obj):
                # intenta llaves comunes
                possible_time_keys = ["timestamp", "time", "fecha", "datetime", "x"]
                possible_val_keys = ["value", "val", "demanda", "y"]
                for tk in possible_time_keys:
                    for vk in possible_val_keys:
                        if tk in obj[0] and vk in obj[0]:
                            t = [x.get(tk) for x in obj]
                            y = [x.get(vk) for x in obj]
                            if looks_like_dates(t) and all(isinstance(v, (int, float, type(None))) for v in y):
                                candidates.append((t, y))
            for v in obj:
                walk(v)

    walk(payload)

    # si no encontró patrones, intenta heurística básica sobre dict con dos listas
    if isinstance(payload, dict):
        lists = [(k, v) for k, v in payload.items() if isinstance(v, list)]
        for i in range(len(lists)):
            for j in range(len(lists)):
                if i == j:
                    continue
                a = lists[i][1]
                b = lists[j][1]
                if looks_like_dates(a) and looks_like_values(b) and len(a) == len(b):
                    candidates.append((a, b))

    if not candidates:
        raise ValueError("No pude detectar series (timestamps/values) en la respuesta de CENACE.")

    # elige el mejor candidato: mismo largo, values numéricos
    candidates = [c for c in candidates if len(c[0]) == len(c[1]) and len(c[0]) > 0]
    candidates.sort(key=lambda c: len(c[0]), reverse=True)
    return candidates[0]


def _parse_timestamps(ts: List[Any]) -> pd.DatetimeIndex:
    # epoch ms / epoch s / string
    if isinstance(ts[0], (int, float)):
        # si parece ms (muy grande)
        v = float(ts[0])
        unit = "ms" if v > 10_000_000_000 else "s"
        return pd.to_datetime(pd.Series(ts, dtype="float64"), unit=unit, errors="coerce").dt.tz_localize(None)

    # strings
    out = pd.to_datetime(pd.Series(ts, dtype="string"), errors="coerce", utc=False)
    return pd.DatetimeIndex(out).tz_localize(None)


def _quality_report(df: pd.DataFrame) -> Dict[str, Any]:
    s = df["demand_mw"]
    # huecos/duplicados por timestamp
    idx = df.index
    duplicates = int(idx.duplicated().sum())
    # si tiene frecuencia horaria, esperamos horas consecutivas
    missing = 0
    if len(idx) >= 2:
        full = pd.date_range(idx.min(), idx.max(), freq="H")
        missing = int(len(full.difference(idx)))
    return {
        "rows": int(len(df)),
        "nans": int(s.isna().sum()),
        "negatives": int((s < 0).sum()),
        "duplicates": duplicates,
        "missing_hours": missing,
        "start": str(idx.min()) if len(idx) else None,
        "end": str(idx.max()) if len(idx) else None,
    }


def fetch_demand_block(
    system: str,
    start: datetime,
    end: datetime,
    cache_dir: Path,
    retries: int = 3,
    timeout_s: int = 30,
) -> FetchResult:
    """
    Descarga demanda para [start, end) y cachea en disco.
    Si falla API, intenta cargar caché.
    """
    _safe_mkdir(cache_dir)
    cpath = _cache_path(cache_dir, system, start, end)

    payload = {
        # OJO: estos campos pueden variar por endpoint real.
        # Ajusta aquí si tu JSON requiere otros nombres.
        "sistema": system,
        "fechaInicio": start.strftime("%Y-%m-%d"),
        "fechaFin": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
    }

    last_err: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            r = requests.post(CENACE_URL, json=payload, timeout=timeout_s)
            r.raise_for_status()
            data = r.json()

            ts, vals = _find_series(data)
            idx = _parse_timestamps(ts)

            ser = pd.Series(vals, index=idx, name="demand_mw").astype("float64")
            df = ser.to_frame().sort_index()

            # cache
            df.to_parquet(cpath, index=True)
            return FetchResult(df=df, source="api")

        except Exception as e:
            last_err = e
            time.sleep(0.8 * attempt)

    # fallback cache
    if cpath.exists():
        df = pd.read_parquet(cpath)
        # si parquet no trae índice bien, fuerza
        if "demand_mw" in df.columns:
            df = df.set_index(df.columns[0]) if df.index.name is None else df
        df.index = pd.to_datetime(df.index, errors="coerce")
        return FetchResult(df=df.sort_index(), source="cache")

    raise RuntimeError(f"Falló CENACE y no hay caché disponible. Último error: {last_err}")


def fetch_demand(
    system: str,
    start: datetime,
    days: int,
    cache_dir: Path,
) -> Tuple[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]:
    """
    Batching <= 7 días por request. Concatena todo.
    Devuelve df + reporte calidad global + reportes por bloque.
    """
    if days < 1:
        raise ValueError("days debe ser >= 1")

    blocks: List[Dict[str, Any]] = []
    all_parts: List[pd.DataFrame] = []

    remaining = days
    cursor = start

    while remaining > 0:
        chunk = min(7, remaining)
        end = cursor + timedelta(days=chunk)

        res = fetch_demand_block(system=system, start=cursor, end=end, cache_dir=cache_dir)
        part = res.df.copy()
        part["source"] = res.source

        all_parts.append(part)
        blocks.append(
            {
                "block_start": cursor.strftime("%Y-%m-%d"),
                "block_days": chunk,
                "source": res.source,
                "quality": _quality_report(res.df),
            }
        )

        cursor = end
        remaining -= chunk

    df = pd.concat(all_parts).sort_index()
    # quita duplicados por si algún bloque se traslapa
    df = df[~df.index.duplicated(keep="first")]

    global_q = _quality_report(df[["demand_mw"]])

    return df, global_q, blocks
