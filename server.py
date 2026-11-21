import io, os, time, warnings, socket, hashlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutTimeout

import numpy as np
import requests
import pyvo
from astropy import log
from astropy.io import fits
from astropy.wcs import WCS
from astropy.utils.exceptions import AstropyWarning
from pyvo.dal.adhoc import DatalinkResults
from reproject import reproject_interp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

warnings.simplefilter("ignore", AstropyWarning)
log.setLevel("ERROR")
socket.setdefaulttimeout(60)  # nothing is allowed to hang forever

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

TAP = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP")
GAIA = pyvo.dal.TAPService("https://gea.esac.esa.int/tap-server/tap")
CACHE = {}
GCACHE = {}
PIX_ARCSEC = 6.2      # SPHEREx pixel scale (approx.)
BUDGET_SEC = 150      # max time for one /frames request
WORKERS = 2           # IRSA is flaky: keep parallel connections low
CUTDIR = "cutcache"   # downloaded cutouts are kept here between runs
os.makedirs(CUTDIR, exist_ok=True)
DL_CACHE = {}


def tap_query(service, q, tries=3):
    """TAP query with retries (IRSA sometimes drops the connection)."""
    last = None
    for i in range(tries):
        try:
            return service.run_sync(q).to_table()
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def target_wcs(ra, dec, n):
    # north up, east left on the canvas
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    s = PIX_ARCSEC / 3600.0
    w.wcs.cdelt = [-s, -s]
    return w


def fetch_cutout(row, ra, dec, size):
    """Returns (bytes or None, reason). Every cutout is cached on disk, so a
    retry (press Load again) only re-downloads what failed before."""
    ident = str(row["access_url"])
    key = hashlib.md5(f"{ident}|{ra:.4f}|{dec:.4f}|{size}".encode()).hexdigest()
    fn = os.path.join(CUTDIR, key + ".fits")
    if os.path.exists(fn):
        with open(fn, "rb") as f:
            return f.read(), ""
    try:
        path = DL_CACHE.get(ident)
        if path is None:
            dl = DatalinkResults.from_result_url(ident).to_table()
            path = str([r for r in dl if r["semantics"] == "#cutout"][0]["path"])
            DL_CACHE[ident] = path
    except Exception as e:
        return None, f"datalink failed ({type(e).__name__})"
    url = (f"https://irsa.ipac.caltech.edu/ibe/cutout?"
           f"path={path}&ra={ra}&dec={dec}&size={size}")
    reason = "cutout: no response"
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=(10, 45))
            if r.status_code == 200 and r.content[:6] == b"SIMPLE":
                tmp = fn + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(r.content)
                os.replace(tmp, fn)
                return r.content, ""
            if r.status_code != 200:
                reason = f"cutout: HTTP {r.status_code}"
            else:
                reason = "cutout: reply is not a FITS file"
        except Exception as e:
            reason = f"cutout: {type(e).__name__}"
        time.sleep(2 * (attempt + 1))
    return None, reason


def process(args):
    row, ra, dec, size, N = args
    oid = str(row["obs_id"])
    content, why = fetch_cutout(row, ra, dec, size)
    if content is None:
        print(f"  {oid}: FAILED - {why}", flush=True)
        return {"why": why}
    try:
        with fits.open(io.BytesIO(content)) as h:
            data = np.nan_to_num(h["IMAGE"].data.astype(float)
                                 - h["ZODI"].data.astype(float))
            src = WCS(h["IMAGE"].header)
            try:
                wl = float(WCS(h["IMAGE"].header, h, key="W")
                           .pixel_to_world(data.shape[1] // 2, data.shape[0] // 2)[0].value)
                if np.isnan(wl):
                    wl = None
            except Exception:
                wl = None
        out, _ = reproject_interp((data, src), target_wcs(ra, dec, N),
                                  shape_out=(N, N), order="bilinear")
        valid = np.isfinite(out)
        if valid.mean() < 0.6:
            why = "target near the detector edge (less than 60% of the field covered)"
            print(f"  {oid}: skipped - {why}", flush=True)
            return {"why": why}
        out = out - np.median(out[valid])
        out[~valid] = 0.0
        print(f"  {oid}: ok", flush=True)
        return {"out": out, "mjd": float(row["t_min"]), "wave": wl}
    except Exception as e:
        why = f"read/reproject error: {type(e).__name__}: {str(e)[:80]}"
        print(f"  {oid}: FAILED - {why}", flush=True)
        return {"why": why}


@app.get("/ping")
def ping():
    t0 = time.time()
    try:
        t = tap_query(TAP, "SELECT TOP 1 obs_id FROM spherex.obscore", tries=1)
        return {"irsa": "ok", "seconds": round(time.time() - t0, 1), "rows": len(t)}
    except Exception as e:
        return {"irsa": "FAILED", "error": f"{type(e).__name__}: {str(e)[:150]}",
                "seconds": round(time.time() - t0, 1)}


@app.get("/frames")
def frames(ra: float, dec: float, size: float = 0.1, det: str = "D3", n: int = 30):
    key = (round(ra, 4), round(dec, 4), size, det, n)
    if key in CACHE:
        return CACHE[key]

    q = f"""
    SELECT obs_id, t_min, access_url FROM spherex.obscore
    WHERE obs_collection = 'spherex_dr1'
    AND CONTAINS(POINT('ICRS', {ra}, {dec}), s_region) = 1
    ORDER BY t_min
    """
    try:
        tbl = tap_query(TAP, q)
    except Exception as e:
        return {"frames": [],
                "note": f"IRSA search failed after retries ({type(e).__name__}). Try again in a minute."}
    rows = [r for r in tbl if r["access_url"].endswith("/" + det)]
    if not rows:
        return {"frames": [],
                "note": f"No {det} images cover this point in DR1. Try another detector."}

    N = int(round(size * 3600 / PIX_ARCSEC))
    cand = sorted(set(np.linspace(0, len(rows) - 1, min(2 * n, len(rows))).astype(int).tolist()))
    jobs = [(rows[i], ra, dec, size, N) for i in cand]
    print(f"/frames {det}: {len(rows)} images cover the point, trying {len(jobs)}", flush=True)

    ex = ThreadPoolExecutor(WORKERS)
    futs = [ex.submit(process, j) for j in jobs]
    good, reasons, timed_out = [], Counter(), False
    try:
        for f in as_completed(futs, timeout=BUDGET_SEC):
            r = f.result()
            if "out" in r:
                good.append(r)
            else:
                reasons[r["why"]] += 1
            if len(good) >= n:
                break
    except FutTimeout:
        timed_out = True
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    if not good:
        why = "; ".join(f"{k} (x{v})" for k, v in reasons.most_common(3)) or "no result"
        if timed_out:
            why += f"; IRSA was too slow (stopped after {BUDGET_SEC} s)"
        return {"frames": [], "rows": len(rows),
                "note": f"{len(rows)} {det} images cover this point but none could be used: {why}"}

    result = {"ra": ra, "dec": dec, "size": size, "det": det, "h": N, "w": N,
              "skipped": dict(reasons), "timed_out": timed_out,
              "frames": [{"mjd": g["mjd"], "wave": g["wave"],
                          "north": [0.0, -1.0], "east": [-1.0, 0.0],
                          "data": np.round(g["out"], 3).tolist()}
                         for g in good]}
    if not timed_out and len(good) >= 2:
        CACHE[key] = result
    return result


def fnum(x):
    try:
        if np.ma.is_masked(x):
            return 0.0
        v = float(x)
        return v if np.isfinite(v) else 0.0
    except Exception:
        return 0.0


@app.get("/gaia")
def gaia(ra: float, dec: float, radius: float = 0.08, gmax: float = 16.5):
    key = (round(ra, 4), round(dec, 4), round(radius, 3), gmax)
    if key in GCACHE:
        return GCACHE[key]
    q = f"""
    SELECT TOP 600 ra, dec, pmra, pmdec, phot_g_mean_mag AS g
    FROM gaiadr3.gaia_source
    WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {radius}))
    AND phot_g_mean_mag < {gmax}
    ORDER BY phot_g_mean_mag
    """
    try:
        t = tap_query(GAIA, q)
        stars = [{"ra": fnum(r["ra"]), "dec": fnum(r["dec"]),
                  "pmra": fnum(r["pmra"]), "pmdec": fnum(r["pmdec"]),
                  "g": fnum(r["g"])} for r in t]
    except Exception as e:
        return {"stars": [], "error": str(e)[:150]}
    out = {"stars": stars}
    GCACHE[key] = out
    return out


@app.get("/coverage")
def coverage(ra: float, dec: float):
    q = f"""
    SELECT access_url, t_min FROM spherex.obscore
    WHERE obs_collection = 'spherex_dr1'
    AND CONTAINS(POINT('ICRS', {ra}, {dec}), s_region) = 1
    """
    t = tap_query(TAP, q)
    counts = {}
    for r in t:
        d = str(r["access_url"]).rsplit("/", 1)[-1]
        counts[d] = counts.get(d, 0) + 1
    return {"ra": ra, "dec": dec, "images_per_detector": counts, "total": len(t)}