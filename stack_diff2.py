import numpy as np
from PIL import Image, ImageDraw
from astropy.convolution import Gaussian2DKernel, convolve

NAME = "wise0855"
d = np.load(f"{NAME}.npz")
A, mjd = d["arrays"], d["mjd"]

def clipped_median(stack, sigma=3):
    med = np.median(stack, axis=0)
    std = np.std(stack, axis=0) + 1e-9
    masked = np.where(np.abs(stack - med) < sigma * std, stack, np.nan)
    return np.nanmedian(masked, axis=0)

E = clipped_median(A[mjd < 61000])
L = clipped_median(A[mjd >= 61000])

k = Gaussian2DKernel(1.2)
E = convolve(E, k, boundary="extend")
L = convolve(L, k, boundary="extend")
D = L - E

mad = np.median(np.abs(D - np.median(D))) * 1.4826
Z = (D - np.median(D)) / mad
H, W = Z.shape
b = 4

def peaks(Z, sign, n=5):
    Y = sign * Z
    out = []
    for y in range(b, H - b):
        for x in range(b, W - b):
            v = Y[y, x]
            if v > 3 and v == Y[y-1:y+2, x-1:x+2].max():
                out.append((round(float(v), 1), x, y))
    return sorted(out, reverse=True)[:n]

print("center pixel: x=%d y=%d" % (W // 2, H // 2))
print("positive peaks (S/N, x, y):", peaks(Z, 1))
print("negative peaks (S/N, x, y):", peaks(Z, -1))

SCALE = 10
def to_img(a, lo, hi):
    n = np.clip((a - lo) / (hi - lo + 1e-9), 0, 1)
    im = Image.fromarray((n * 255).astype(np.uint8))
    return im.resize((W * SCALE, H * SCALE), Image.BICUBIC).convert("RGB")

img = to_img(Z, -6, 6)
dr = ImageDraw.Draw(img)
cx, cy = (W // 2) * SCALE + SCALE // 2, (H // 2) * SCALE + SCALE // 2
r = 6 * SCALE
dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 0, 0), width=2)
img.save(f"{NAME}_z.png")

lo, hi = np.percentile(np.concatenate([E.ravel(), L.ravel()]), [1, 99.5])
ie, il = to_img(E, lo, hi), to_img(L, lo, hi)
ie.save(f"{NAME}_stack_blink.gif", save_all=True, append_images=[il], duration=600, loop=0)
print("Done: open", NAME + "_z.png and", NAME + "_stack_blink.gif")