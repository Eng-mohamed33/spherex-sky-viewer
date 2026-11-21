# SPHEREx Sky Viewer

NASA Space Apps Challenge 2026 — **Planet X and SPHEREx**.

A web tool that shows SPHEREx images of any sky position (RA/Dec) as a short
"video", so moving objects can be spotted by eye. Early and late observations
are matched by wavelength and shown as a blink or a difference image.

## Features
- RA / Dec / field of view / detector input, plus presets (Barnard's Star, WISE 0855, Epsilon Indi, RW Aurigae, R Draconis)
- Frames (video), Blink early/late, and Difference (late − early) modes
- All frames are reprojected to one north-up grid, zodiacal light is subtracted
- Gaia DR3 stars overlaid, moved by proper motion to each frame's date
- Predicted-position marker for WISE 0855 (from its catalogue proper motion)
- DSS2 sky map (Aladin Lite) of the same field
- Shareable links: `?ra=269.446&dec=4.768&fov=0.1&det=D3`

## Data
- SPHEREx DR1 spectral images and cutouts: NASA/IPAC Infrared Science Archive (IRSA)
- Gaia DR3: ESA Gaia archive (TAP)
- DSS2: CDS Aladin Lite

## Run
```
python -m pip install -r requirements.txt
python -m uvicorn server:app --reload --port 8000
```
In a second terminal:
```
cd web
npm install
npm run dev
```
Open http://localhost:5173 . If the API is not on localhost:8000, change `API` in `web/src/App.jsx`.

## How it works
1. IRSA TAP query finds the SPHEREx DR1 images covering the position.
2. Cutouts are downloaded (and cached in `cutcache/`).
3. Each cutout minus its ZODI image is reprojected to a common north-up grid (about 6.2 arcsec/pixel).
4. Early and late frames are paired by wavelength (within 2%) and subtracted.

## Results and limits (honest notes)
- **Barnard's Star:** the difference images show a positive/negative pair in the direction of its proper motion, and the Gaia-predicted position follows the star between epochs. This is a visual check, not a measurement.
- **Epsilon Indi:** only two epochs about 5 months apart, a saturated star, and an expected shift under half a pixel — no usable motion signal.
- **WISE 0855:** not detected. It is very faint; the predicted-position marker is provided to show where to look.
- **RW Aurigae, R Draconis:** frames load with Gaia overlay; variability is not quantified.
- Bright stars saturate, so their cores are empty.
- Preset positions for 2026 are approximate (catalogue position plus proper motion).
- IRSA's cutout service sometimes returns HTTP 503 or drops connections; press Load again (downloaded cutouts are cached).
- Only the DR1 collection is searched.