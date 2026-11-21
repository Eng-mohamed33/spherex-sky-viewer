import numpy as np
from PIL import Image

NAME = "wise0855"
d = np.load(f"{NAME}.npz")
A, mjd, wave = d["arrays"], d["mjd"], d["wave"]

early = A[mjd < 61000]
late = A[mjd >= 61000]
print("early frames:", len(early), "| late frames:", len(late))

def clipped_median(stack, sigma=3):
    med = np.median(stack, axis=0)
    std = np.std(stack, axis=0) + 1e-9
    masked = np.where(np.abs(stack - med) < sigma * std, stack, np.nan)
    return np.nanmedian(masked, axis=0)

E = clipped_median(early)
L = clipped_median(late)
D = L - E

SCALE = 8
def to_img(a, lo, hi):
    n = np.clip((a - lo) / (hi - lo + 1e-9), 0, 1)
    return Image.fromarray((n * 255).astype(np.uint8)).resize(
        (a.shape[1] * SCALE, a.shape[0] * SCALE), Image.BICUBIC)

lo, hi = np.percentile(np.concatenate([E.ravel(), L.ravel()]), [1, 99.5])
ie, il = to_img(E, lo, hi), to_img(L, lo, hi)
ie.save(f"{NAME}_early.png")
il.save(f"{NAME}_late.png")
ie.save(f"{NAME}_stack_blink.gif", save_all=True, append_images=[il],
        duration=600, loop=0)

m = np.percentile(np.abs(D), 99.5)
to_img(D, -m, m).save(f"{NAME}_stack_diff.png")

# strongest positive / negative residuals (pixel x, y)
ys, xs = np.unravel_index(np.argsort(D.ravel())[::-1][:3], D.shape)
print("brightest residuals (x,y):", list(zip(xs.tolist(), ys.tolist())))
ys, xs = np.unravel_index(np.argsort(D.ravel())[:3], D.shape)
print("darkest residuals (x,y):", list(zip(xs.tolist(), ys.tolist())))
print("Done: open", NAME + "_stack_blink.gif and", NAME + "_stack_diff.png")