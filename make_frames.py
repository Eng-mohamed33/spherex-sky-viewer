import os, time, warnings
import numpy as np
import requests
import pyvo
from pyvo.dal.adhoc import DatalinkResults
from astropy import log
from astropy.io import fits
from astropy.wcs import WCS
from astropy.utils.exceptions import AstropyWarning
from PIL import Image

warnings.simplefilter("ignore", AstropyWarning)
log.setLevel("ERROR")

TTARGETS = {
    "barnard":  (269.446, 4.768, "/D3"),
    "wise0855": (133.766, -7.243, "/D6"),  # approx. 2026 position
}
NAME = "wise0855"
ra, dec, DET = TTARGETS[NAME]
size = 0.1
N, OUT = 80, 464

os.makedirs("frames", exist_ok=True)

tap = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP")
q = f"""
SELECT obs_id, t_min, access_url
FROM spherex.obscore
WHERE obs_collection = 'spherex_dr1'
AND CONTAINS(POINT('ICRS', {ra}, {dec}), s_region) = 1
ORDER BY t_min
"""
res = [r for r in tap.run_sync(q).to_table() if r["access_url"].endswith(DET)]
print("images", DET, ":", len(res))

arrays, mjds, waves = [], [], []
for i in range(len(res)):
    if len(arrays) >= N:
        break
    row = res[i]
    try:
        dl = DatalinkResults.from_result_url(row["access_url"]).to_table()
        cut = [r for r in dl if r["semantics"] == "#cutout"][0]
        url = (f"https://irsa.ipac.caltech.edu/ibe/cutout?"
               f"path={cut['path']}&ra={ra}&dec={dec}&size={size}")
        content = None
        for attempt in range(3):
            r = requests.get(url, timeout=120)
            if r.status_code == 200 and r.content[:6] == b"SIMPLE":
                content = r.content
                break
            time.sleep(2)
        if content is None:
            print("skip", i, "status", r.status_code)
            continue

        fn = f"frames/{NAME}_{i:02d}.fits"
        open(fn, "wb").write(content)
        with fits.open(fn) as h:
            a = np.nan_to_num(h["IMAGE"].data.astype(float) - h["ZODI"].data.astype(float))
            try:
                wl = float(WCS(h["IMAGE"].header, h, key="W")
                           .pixel_to_world(a.shape[1] // 2, a.shape[0] // 2)[0].value)
            except Exception:
                wl = np.nan
        if min(a.shape) < 58 or np.isnan(wl):
            print("skip", i, "edge/no-wave", a.shape)
            continue
        a = a[:58, :58]
        a = a - np.median(a)
        arrays.append(a)
        mjds.append(float(row["t_min"]))
        waves.append(wl)
        print(len(arrays) - 1, "MJD", round(mjds[-1], 2), "wave", round(wl, 3))
    except Exception as e:
        print("skip", i, e)

np.savez(f"{NAME}.npz", arrays=np.array(arrays), mjd=np.array(mjds), wave=np.array(waves))

allv = np.concatenate([a.ravel() for a in arrays])
lo, hi = np.percentile(allv, [1, 99.8])
imgs = []
for a in arrays:
    n = np.clip((a - lo) / (hi - lo + 1e-9), 0, 1)
    imgs.append(Image.fromarray((n * 255).astype(np.uint8)).resize((OUT, OUT), Image.BICUBIC))
imgs[0].save(f"{NAME}.gif", save_all=True, append_images=imgs[1:], duration=300, loop=0)
print("Done: open", NAME + ".gif")