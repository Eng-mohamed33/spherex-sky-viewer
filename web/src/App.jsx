import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

const API = "http://localhost:8000";
const PIX = 6.2; // arcsec per SPHEREx pixel (approx.)
const GAIA_EPOCH_MJD = 57388.0; // 2016.0

// approximate 2026 positions (high proper motion objects), verify before using
const PRESETS = [
  { name: "Barnard's Star", ra: 269.446, dec: 4.768, det: "D3" },
  { name: "WISE 0855", ra: 133.760, dec: -7.242, det: "D6",
    // WISE position (May 2010) + proper motion (Kirkpatrick et al.), mas/yr
    track: { name: "WISE 0855", ra: 133.7951649, dec: -7.2451021, mjd0: 55320.376, pmra: -8118.9, pmdec: 679.3 } },
  { name: "Epsilon Indi", ra: 330.892, dec: -56.804, det: "D3" },
  { name: "RW Aurigae", ra: 76.957, dec: 30.401, det: "D3" },
  { name: "R Draconis", ra: 248.174, dec: 66.755, det: "D3" },
];

const mjdToDate = (m) =>
  new Date((m - 40587) * 86400000).toISOString().slice(0, 10);

function pct(arr, q) {
  const s = Float32Array.from(arr).sort();
  return s[Math.min(s.length - 1, Math.floor(q * s.length))];
}

function Sky({ px, w, h, lo, hi, north, east, gaia, track, mjd, ra0, dec0, size = 464 }) {
  const ref = useRef(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || !px) return;
    const off = document.createElement("canvas");
    off.width = w;
    off.height = h;
    const octx = off.getContext("2d");
    const img = octx.createImageData(w, h);
    for (let i = 0; i < w * h; i++) {
      const v = Math.max(0, Math.min(1, (px[i] - lo) / (hi - lo + 1e-9)));
      const g = v * 255;
      img.data[4 * i] = g;
      img.data[4 * i + 1] = g;
      img.data[4 * i + 2] = g;
      img.data[4 * i + 3] = 255;
    }
    octx.putImageData(img, 0, 0);
    const ctx = c.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(off, 0, 0, size, size);

    // Gaia DR3 overlay, moved by proper motion to this frame's date
    if (gaia && gaia.length && mjd) {
      const dt = (mjd - GAIA_EPOCH_MJD) / 365.25;
      const c0 = Math.cos((dec0 * Math.PI) / 180);
      const k = size / w;
      ctx.strokeStyle = "#ff6b6b";
      ctx.lineWidth = 1.5;
      for (const s of gaia) {
        const cosd = Math.cos((s.dec * Math.PI) / 180);
        const ra = s.ra + (s.pmra * dt) / (3.6e6 * cosd);
        const dec = s.dec + (s.pmdec * dt) / 3.6e6;
        const dx = (-(ra - ra0) * c0 * 3600) / PIX;
        const dy = (-(dec - dec0) * 3600) / PIX;
        const x = (w / 2 + dx) * k;
        const y = (h / 2 + dy) * k;
        if (x < 0 || y < 0 || x > size || y > size) continue;
        const r = 6 + Math.max(0, 16.5 - s.g) * 0.6;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, 2 * Math.PI);
        ctx.stroke();
      }
    }

    // predicted position of a tracked high-proper-motion object
    if (track && mjd) {
      const dt = (mjd - track.mjd0) / 365.25;
      const c0 = Math.cos((dec0 * Math.PI) / 180);
      const k = size / w;
      const tdec = track.dec + (track.pmdec * dt) / 3.6e6;
      const tra = track.ra +
        (track.pmra * dt) / (3.6e6 * Math.cos((track.dec * Math.PI) / 180));
      const x = (w / 2 + (-(tra - ra0) * c0 * 3600) / PIX) * k;
      const y = (h / 2 + (-(tdec - dec0) * 3600) / PIX) * k;
      ctx.strokeStyle = "#22d3ee";
      ctx.fillStyle = "#22d3ee";
      ctx.lineWidth = 1.5;
      const g = 9;
      ctx.beginPath();
      ctx.moveTo(x - 22, y); ctx.lineTo(x - g, y);
      ctx.moveTo(x + g, y); ctx.lineTo(x + 22, y);
      ctx.moveTo(x, y - 22); ctx.lineTo(x, y - g);
      ctx.moveTo(x, y + g); ctx.lineTo(x, y + 22);
      ctx.stroke();
      ctx.font = "12px system-ui";
      ctx.fillText(track.name + " (predicted)", x + 26, y - 6);
    }

    const arrow = (v, label, color) => {
      if (!v) return;
      const ox = 50, oy = size - 50, L = 36;
      const ex = ox + v[0] * L, ey = oy + v[1] * L;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(ex, ey);
      ctx.stroke();
      ctx.font = "13px system-ui";
      ctx.fillText(label, ex + v[0] * 8 - 4, ey + v[1] * 8 + 4);
    };
    arrow(north, "N", "#ffd43b");
    arrow(east, "E", "#69db7c");
  }, [px, w, h, lo, hi, north, east, gaia, track, mjd, ra0, dec0, size]);
  return <canvas ref={ref} width={size} height={size} className="sky" />;
}

function Aladin({ ra, dec, fov }) {
  const ref = useRef(null);
  const al = useRef(null);
  useEffect(() => {
    if (!window.A || !ref.current) return;
    const f = Number(fov);
    const target = `${ra} ${dec}`;
    window.A.init.then(() => {
      if (!al.current) {
        al.current = window.A.aladin(ref.current, {
          survey: "P/DSS2/color",
          target,
          fov: f,
          showReticle: true,
          showZoomControl: false,
          showFullscreenControl: false,
        });
      } else {
        al.current.gotoRaDec(Number(ra), Number(dec));
      }
      setTimeout(() => al.current.setFoV(f), 300);
    });
  }, [ra, dec, fov]);
  return <div ref={ref} className="aladin" />;
}

export default function App() {
  const p = new URLSearchParams(window.location.search);
  const [ra, setRa] = useState(p.get("ra") || "269.446");
  const [dec, setDec] = useState(p.get("dec") || "4.768");
  const [fov, setFov] = useState(p.get("fov") || "0.1");
  const [det, setDet] = useState(p.get("det") || "D3");
  const [n, setN] = useState(20);
  const [mode, setMode] = useState("frames");
  const [sortBy, setSortBy] = useState("mjd");
  const [frames, setFrames] = useState([]);
  const [gaia, setGaia] = useState([]);
  const [showGaia, setShowGaia] = useState(true);
  const [target, setTarget] = useState(null);
  const [trackObj, setTrackObj] = useState(null);
  const [dims, setDims] = useState({ w: 0, h: 0 });
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(500);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const sorted = useMemo(() => {
    const f = [...frames];
    f.sort((a, b) =>
      sortBy === "wave" ? (a.wave ?? 99) - (b.wave ?? 99) : a.mjd - b.mjd
    );
    return f;
  }, [frames, sortBy]);

  // pairs: early epoch vs late epoch, matched by wavelength
  const pairs = useMemo(() => {
    if (frames.length < 2) return [];
    const byT = [...frames].sort((a, b) => a.mjd - b.mjd);
    let gap = 0, cut = 0;
    for (let i = 1; i < byT.length; i++) {
      const g = byT[i].mjd - byT[i - 1].mjd;
      if (g > gap) { gap = g; cut = i; }
    }
    const early = byT.slice(0, cut);
    const late = byT.slice(cut);
    const out = [];
    for (const a of early) {
      if (a.wave == null) continue;
      let best = null, bd = 1e9;
      for (const b of late) {
        if (b.wave == null) continue;
        const d = Math.abs(b.wave - a.wave);
        if (d < bd) { bd = d; best = b; }
      }
      if (best && bd < 0.02 * a.wave) {
        out.push({ a, b: best, diff: best.px.map((v, i) => v - a.px[i]) });
      }
    }
    return out;
  }, [frames]);

  const stats = useMemo(() => {
    if (!frames.length) return null;
    const len = frames[0].px.length;
    const all = new Float32Array(frames.length * len);
    frames.forEach((f, i) => all.set(f.px, i * len));
    let dm = 1e-4;
    if (pairs.length) {
      const d = new Float32Array(pairs.length * len);
      pairs.forEach((q, i) => d.set(q.diff.map((v) => Math.abs(v)), i * len));
      dm = pct(d, 0.995);
    }
    return { lo: pct(all, 0.01), hi: pct(all, 0.998), dm };
  }, [frames, pairs]);

  const count =
    mode === "frames" ? sorted.length : mode === "blink" ? pairs.length * 2 : pairs.length;

  async function load(r = ra, d = dec, s = fov, dt = det) {
    setLoading(true);
    setError("");
    setPlaying(false);
    window.history.replaceState(null, "", `?ra=${r}&dec=${d}&fov=${s}&det=${dt}`);
    try {
      const gp = fetch(
        `${API}/gaia?ra=${r}&dec=${d}&radius=${Number(s) * 0.8}`
      ).then((x) => x.json()).catch(() => ({ stars: [] }));
      const res = await fetch(
        `${API}/frames?ra=${r}&dec=${d}&size=${s}&det=${dt}&n=${n}`
      );
      const data = await res.json();
      const fs = (data.frames || []).map((f) => ({
        mjd: f.mjd,
        wave: f.wave,
        north: f.north,
        east: f.east,
        px: Float32Array.from(f.data.flat()),
      }));
      setFrames(fs);
      setDims({ w: data.w || 0, h: data.h || 0 });
      setTarget({ ra: r, dec: d, fov: s });
      const g = await gp;
      setGaia(g.stars || []);
      setTick(0);
      if (!fs.length) setError(data.note || "No frames for this position.");
      else if (data.timed_out)
        setError(`Loaded ${fs.length} frames only (IRSA is slow). Press Load again to fetch more.`);
    } catch (e) {
      setError("Server error: " + e.message);
    }
    setLoading(false);
  }

  useEffect(() => {
    if (p.get("ra") && p.get("dec")) load();
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    if (!playing || !count) return;
    const t = setInterval(() => setTick((x) => x + 1), speed);
    return () => clearInterval(t);
  }, [playing, speed, count]);

  function pick(pr) {
    setRa(pr.ra);
    setDec(pr.dec);
    setDet(pr.det);
    setTrackObj(pr.track || null);
    load(pr.ra, pr.dec, fov, pr.det);
  }

  let view = null, label = "";
  if (count && stats) {
    const t = tick % count;
    if (mode === "frames") {
      const f = sorted[t];
      view = { px: f.px, lo: stats.lo, hi: stats.hi, n: f.north, e: f.east, mjd: f.mjd };
      label = `Frame ${t + 1}/${count} | ${mjdToDate(f.mjd)} | ${f.wave ? f.wave.toFixed(3) : "n/a"} µm`;
    } else if (mode === "blink") {
      const q = pairs[Math.floor(t / 2)];
      const f = t % 2 ? q.b : q.a;
      view = { px: f.px, lo: stats.lo, hi: stats.hi, n: f.north, e: f.east, mjd: f.mjd };
      label = `Pair ${Math.floor(t / 2) + 1}/${pairs.length} | ${t % 2 ? "LATE" : "EARLY"} ${mjdToDate(f.mjd)} | ${q.a.wave.toFixed(3)} µm`;
    } else {
      const q = pairs[t];
      view = { px: q.diff, lo: -stats.dm, hi: stats.dm, n: q.b.north, e: q.b.east, mjd: q.b.mjd };
      label = `Diff ${t + 1}/${count} | ${mjdToDate(q.b.mjd)} minus ${mjdToDate(q.a.mjd)} | ${q.a.wave.toFixed(3)} µm`;
    }
  }

  return (
    <div className="app">
      <h1>SPHEREx Sky Viewer</h1>

      <div className="presets">
        {PRESETS.map((pr) => (
          <button key={pr.name} onClick={() => pick(pr)}>{pr.name}</button>
        ))}
      </div>

      <div className="form">
        <label>RA (deg)
          <input value={ra} onChange={(e) => { setRa(e.target.value); setTrackObj(null); }} /></label>
        <label>Dec (deg)
          <input value={dec} onChange={(e) => { setDec(e.target.value); setTrackObj(null); }} /></label>
        <label>FOV (deg)
          <input value={fov} onChange={(e) => setFov(e.target.value)} /></label>
        <label>Detector
          <select value={det} onChange={(e) => setDet(e.target.value)}>
            {["D1", "D2", "D3", "D4", "D5", "D6"].map((d) => <option key={d}>{d}</option>)}
          </select></label>
        <label>Frames
          <input type="number" value={n} onChange={(e) => setN(e.target.value)} /></label>
        <button className="go" onClick={() => load()} disabled={loading}>
          {loading ? "Loading..." : "Load"}
        </button>
      </div>

      {error && <p className="err">{error}</p>}
      {loading && <p>Fetching from IRSA, this can take 1-2 minutes...</p>}

      {frames.length > 0 && (
        <div className="modes">
          <select value={mode} onChange={(e) => { setMode(e.target.value); setTick(0); }}>
            <option value="frames">Frames (video)</option>
            <option value="blink">Blink early / late</option>
            <option value="diff">Difference (late - early)</option>
          </select>
          {mode === "frames" && (
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="mjd">Sort by time</option>
              <option value="wave">Sort by wavelength</option>
            </select>
          )}
          <label className="chk">
            <input type="checkbox" checked={showGaia}
              onChange={(e) => setShowGaia(e.target.checked)} />
            Gaia DR3 overlay ({gaia.length})
          </label>
          {mode !== "frames" && pairs.length === 0 && (
            <span className="err">No matching pairs: need frames from 2 different epochs.</span>
          )}
        </div>
      )}

      {view && (
        <div className="row">
          <div className="viewer">
            <Sky px={view.px} w={dims.w} h={dims.h} lo={view.lo} hi={view.hi}
                 north={view.n} east={view.e}
                 gaia={showGaia ? gaia : null} track={trackObj} mjd={view.mjd}
                 ra0={Number(target.ra)} dec0={Number(target.dec)} />
            <div className="meta">{label}</div>
            <div className="controls">
              <button onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</button>
              <input type="range" min="0" max={count - 1} value={tick % count}
                onChange={(e) => { setTick(+e.target.value); setPlaying(false); }} />
              <label>Speed
                <input type="range" min="100" max="1000" step="50" value={1100 - speed}
                  onChange={(e) => setSpeed(1100 - +e.target.value)} /></label>
            </div>
          </div>
          {target && (
            <div className="aladinbox">
              <Aladin ra={target.ra} dec={target.dec} fov={target.fov} />
              <div className="meta">DSS2 (old epoch), same field</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}