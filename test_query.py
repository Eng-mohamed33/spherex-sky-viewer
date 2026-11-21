import os
import requests
import pyvo
from pyvo.dal.adhoc import DatalinkResults
from astropy.io import fits

ra, dec, size = 133.79513, -7.245147, 0.02  # size بالدرجات
N = 3  # عدد الصور للتجربة

os.makedirs("cutouts", exist_ok=True)

tap = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP")
q = f"""
SELECT obs_id, t_min, em_min, em_max, access_url
FROM spherex.obscore
WHERE obs_collection = 'spherex_dr1'
AND CONTAINS(POINT('ICRS', {ra}, {dec}), s_region) = 1
ORDER BY t_min
"""
res = tap.run_sync(q).to_table()
print("عدد الصور:", len(res))

for i, row in enumerate(res[:N]):
    dl = DatalinkResults.from_result_url(row["access_url"]).to_table()
    cut = [r for r in dl if r["semantics"] == "#cutout"][0]
    url = (f"https://irsa.ipac.caltech.edu/ibe/cutout?"
           f"path={cut['path']}&ra={ra}&dec={dec}&size={size}")
    fn = f"cutouts/{i}_{row['obs_id']}_{int(row['em_min']*1e9)}nm.fits"
    r = requests.get(url, timeout=120)
    print(i, r.status_code, len(r.content), "bytes")
    open(fn, "wb").write(r.content)

    with fits.open(fn) as h:
        h.info()
        print("IMAGE shape:", h["IMAGE"].data.shape, "| MJD:", row["t_min"])