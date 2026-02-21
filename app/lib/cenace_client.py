from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

# Endpoint AJAX de CENACE (lo usaste en Semana 1)
CENACE_URL = "https://www.cenace.gob.mx/GraficaDemanda.aspx/obtieneValoresTotal"
# Página referer para "warm-up" de cookies (ASP.NET a veces lo necesita)
REFERER_PAGE = "https://www.cenace.gob.mx/GraficaDemanda.aspx"

# Headers tipo navegador (ayuda a que no te regrese HTML/bloqueo tan fácil)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.cenace.gob.mx",
    "Referer": REFERER_PAGE,
}


@dataclass
class FetchResult:
    df: pd.DataFrame
    source: str  # "api" or "cache"
    raw_len: int = 0  # tamaño aproximado de la respuesta cruda (debug)


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _cache_path(cache_dir: Path, system: str, start: datetime, end: datetime) -> Path:
    s = start.strftime("%Y%m%d")
    e = end.strftime("%Y%m%d")
    return cache_dir / f"demand_{system}_{s}_{e}.parquet"


def _unwrap_payload(payload: Any) -> Any:
    """
    CENACE a veces responde ASP.NET style: {"d": "...json..."} o {"d": {...}}
    """
    if isinstance(payload, dict) and "d" in payload:
        d = payload["d"]
        if isinstance(d, str):
            try:
                return json.loads(d)
            except Exception:
                return d
        return d
    return payload


def _find_series(payload: Any) -> Tuple[List[Any], List[Any]]:
    """
    Intenta detectar (timestamps, values) en distintas estructuras posibles.
    """
    payload = _unwrap_payload(payload)

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            pass

    candidates: List[Tuple[List[Any], List[Any]]] = []

    def looks_like_values(xs: List[Any]) -> bool:
        if not xs:
            return False
        sample = xs[: min(5, len(xs))]
        return all(isinstance(x, (int, float)) or x is None for x in sample)

    def looks_like_dates(xs: List[Any]) -> bool:
        if not xs:
            return False
        sample = xs[: min(5, len(xs))]
        ok = 0
        for x in sample:
            if isinstance(x, (int, float)):
                ok += 1  # epoch-ish
            elif isinstance(x, str):
                ok += 1
        return ok == len(sample)

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            # patrones directos
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

            # patrón tipo Highcharts: categories + series[{data:[]}]
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
                possible_time_keys = ["timestamp", "time", "fecha", "datetime", "x"]
                possible_val_keys = ["value", "val", "demanda", "y"]
                for tk in possible_time_keys:
                    for vk in possible_val_keys:
                        if tk in obj[0] and vk in obj[0]:
                            t = [x.get(tk) for x in obj]
                            y = [x.get(vk) for x in obj]
                            if looks_like_dates(t) and looks_like_values(y):
                                candidates.append((t, y))
            for v in obj:
                walk(v)

    walk(payload)

    if not candidates:
        raise ValueError(f"No pude detectar series (timestamps/values). Tipo payload: {type(payload)}")

    candidates = [c for c in candidates if len(c[0]) == len(c[1]) and len(c[0]) > 0]
    candidates.sort(key=lambda c: len(c[0]), reverse=True)
    return candidates[0]


def _parse_timestamps(ts: List[Any]) -> pd.DatetimeIndex:
    """
    Convierte timestamps epoch/ms/strings a DatetimeIndex naive (sin tz).
    """
    if isinstance(ts[0], (int, float)):
        v = float(ts[0])
        unit = "ms" if v > 10_000_000_000 else "s"
        out = pd.to_datetime(pd.Series(ts, dtype="float64"), unit=unit, errors="coerce")
        return pd.DatetimeIndex(out).tz_localize(None)

    out = pd.to_datetime(pd.Series(ts, dtype="string"), errors="coerce", utc=False)
    return pd.DatetimeIndex(out).tz_localize(None)


def _quality_report(df: pd.DataFrame) -> Dict[str, Any]:
    s = df["demand_mw"]
    idx = df.index
    duplicates = int(idx.duplicated().sum())
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


def _try_request(session: requests.Session, payload: Dict[str, Any], timeout_s: int) -> Tuple[Any, int]:
    """
    Hace warm-up (GET a la página) + POST al endpoint.
    Devuelve (json_data, raw_len).
    Si regresa HTML / 403 / etc, lanza RuntimeError con snippet del body (para debug).
    """
    # warm-up
    session.get(REFERER_PAGE, headers=DEFAULT_HEADERS, timeout=timeout_s)

    r = session.post(
        CENACE_URL,
        data=json.dumps(payload),
        headers=DEFAULT_HEADERS,
        timeout=timeout_s,
    )

    ct = (r.headers.get("Content-Type") or "").lower()
    raw = r.text or ""
    raw_len = len(raw.encode("utf-8", errors="ignore"))

    if r.status_code != 200:
        snippet = raw[:400].replace("\n", " ")
        raise RuntimeError(f"HTTP {r.status_code} | Content-Type={ct} | body_snippet={snippet}")

    # A veces devuelve HTML (bloqueo)
    if "text/html" in ct or "<html" in raw.lower():
        snippet = raw[:400].replace("\n", " ")
        raise RuntimeError(f"Respuesta HTML (posible bloqueo). Content-Type={ct} | body_snippet={snippet}")

    # intenta JSON
    try:
        return r.json(), raw_len
    except Exception:
        # intenta parsear el texto como JSON
        try:
            return json.loads(raw), raw_len
        except Exception:
            snippet = raw[:400].replace("\n", " ")
            raise RuntimeError(f"No es JSON. Content-Type={ct} | body_snippet={snippet}")


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

    # Intentamos varios payloads porque el endpoint real puede ignorarlos / variar
    payload_candidates = [
        {},  # algunos endpoints ignoran filtros y regresan "algo"
        {"sistema": system},
        {
            "sistema": system,
            "fechaInicio": start.strftime("%Y-%m-%d"),
            "fechaFin": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
        },
    ]

    last_err: Optional[Exception] = None
    session = requests.Session()

    for attempt in range(1, retries + 1):
        for payload in payload_candidates:
            try:
                data, raw_len = _try_request(session, payload, timeout_s=timeout_s)

                ts, vals = _find_series(data)
                idx = _parse_timestamps(ts)

                ser = pd.Series(vals, index=idx, name="demand_mw").astype("float64")
                df = ser.to_frame().sort_index()

                # cache
                df.to_parquet(cpath, index=True)
                return FetchResult(df=df, source="api", raw_len=raw_len)

            except Exception as e:
                last_err = e

        time.sleep(0.8 * attempt)

    # fallback cache
    if cpath.exists():
        df = pd.read_parquet(cpath)
        df.index = pd.to_datetime(df.index, errors="coerce")
        if "demand_mw" not in df.columns and len(df.columns) == 1:
            df.columns = ["demand_mw"]
        return FetchResult(df=df.sort_index(), source="cache", raw_len=0)

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
                "raw_len": res.raw_len,
                "quality": _quality_report(res.df),
            }
        )

        cursor = end
        remaining -= chunk

    df = pd.concat(all_parts).sort_index()
    df = df[~df.index.duplicated(keep="first")]

    global_q = _quality_report(df[["demand_mw"]])

    return df, global_q, blocks
