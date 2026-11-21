import numpy as np
from PIL import Image

NAME = "wise0855"
d = np.load(f"{NAME}.npz")
A, mjd, wave = d["arrays"], d["mjd"], d["wave"]

early = np.where(mjd < 61000)[0]
late = np.where(mjd >= 61000)[0]

pairs = []
for i in early:
    j = late[np.argmin(np.abs(wave[late] - wave[i]))]
    if abs(wave[j] - wave[i]) < 0.02 * wave[i]:
        pairs.append((i, j))
print(len(pairs), "matched pairs")

SCALE = 8
def to_img(a, lo, hi):
    n = np.clip((a - lo) / (hi - lo + 1e-9), 0, 1)
    return Image.fromarray((n * 255).astype(np.uint8)).resize(
        (a.shape[1] * SCALE, a.shape[0] * SCALE), Image.BICUBIC)

lo, hi = np.percentile(A, [1, 99.8])
diffs = [A[j] - A[i] for i, j in pairs]
m = np.percentile(np.abs(np.concatenate([x.ravel() for x in diffs])), 99.5)

blink, dimgs = [], []
for k, (i, j) in enumerate(pairs):
    blink += [to_img(A[i], lo, hi), to_img(A[j], lo, hi)]
    dimgs.append(to_img(diffs[k], -m, m))
    print(k, "MJD", round(mjd[i], 1), "->", round(mjd[j], 1), "wave", round(wave[i], 3), round(wave[j], 3))

blink[0].save(f"{NAME}_blink.gif", save_all=True, append_images=blink[1:], duration=500, loop=0)
dimgs[0].save(f"{NAME}_diff.gif", save_all=True, append_images=dimgs[1:], duration=500, loop=0)
print("Done: open", NAME + "_blink.gif and", NAME + "_diff.gif")