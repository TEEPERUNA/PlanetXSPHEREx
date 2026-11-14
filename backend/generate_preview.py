"""
Generates an interactive standalone HTML preview dashboard (preview.html)
allowing Emil and the team to visually test and verify:
- Blink comparator between epochs
- Difference imaging (Epoch Last - Epoch First)
- Contrast stretching & negative inversion
- 102-channel SPHEREx spectrum plot
- Multi-epoch light curves for variable stars
- Gaia DR3 proper motion validation cards
"""

import json
from pathlib import Path
from backend.services.targets import BENCHMARK_TARGETS
from backend.services.pipeline import process_science_pipeline

def generate_html_preview():
    print("Generating full scientific dataset for all 5 targets...")
    all_data = {}
    for target_key in BENCHMARK_TARGETS.keys():
        print(f"  Processing {target_key}...")
        result = process_science_pipeline(target_identifier=target_key, stretch_type="zscale")
        all_data[target_key] = result

    data_json = json.dumps(all_data)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PlanetXSPHEREx - Emil's Science & Image Processing Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: #131b2e;
      --border: #223152;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.25);
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --dipole-pos: #4ade80;
      --dipole-neg: #f87171;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }}
    header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }}
    h1 {{ font-size: 1.5rem; color: #fff; display: flex; align-items: center; gap: 10px; }}
    .badge {{ background: #1e293b; color: var(--accent); padding: 4px 10px; border-radius: 999px; font-size: 0.75rem; border: 1px solid var(--accent); }}
    .target-nav {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 24px; }}
    .target-btn {{
      background: var(--card-bg); border: 1px solid var(--border); color: var(--text);
      padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: 500; font-size: 0.9rem;
      transition: all 0.2s;
    }}
    .target-btn:hover, .target-btn.active {{
      background: #1e293b; border-color: var(--accent); color: var(--accent); box-shadow: 0 0 12px var(--accent-glow);
    }}
    .grid {{ display: grid; grid-template-columns: 460px 1fr; gap: 24px; }}
    @media (max-width: 1024px) {{ .grid {{ grid-template-columns: 1fr; }} }}
    .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
    .card-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 14px; color: #fff; display: flex; justify-content: space-between; align-items: center; }}
    
    /* Image Viewer */
    .viewer-container {{ display: flex; flex-direction: column; align-items: center; background: #000; border-radius: 8px; padding: 12px; border: 1px solid var(--border); position: relative; }}
    .canvas-wrap {{ width: 340px; height: 340px; display: flex; align-items: center; justify-content: center; position: relative; }}
    .canvas-wrap img {{ width: 100%; height: 100%; image-rendering: pixelated; border-radius: 4px; }}
    .viewer-overlay {{ position: absolute; bottom: 8px; left: 8px; font-size: 0.75rem; background: rgba(0,0,0,0.7); padding: 4px 8px; border-radius: 4px; color: #38bdf8; }}
    .crosshair {{ position: absolute; width: 100%; height: 100%; pointer-events: none; }}
    .crosshair::before, .crosshair::after {{ content: ''; position: absolute; background: rgba(56, 189, 248, 0.4); }}
    .crosshair::before {{ top: 50%; left: 0; width: 100%; height: 1px; }}
    .crosshair::after {{ left: 50%; top: 0; width: 1px; height: 100%; }}
    
    /* Controls */
    .controls {{ display: flex; gap: 8px; margin-top: 14px; width: 100%; justify-content: center; flex-wrap: wrap; }}
    .btn {{
      background: #1e293b; border: 1px solid var(--border); color: var(--text); padding: 8px 14px;
      border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 500;
    }}
    .btn:hover {{ border-color: var(--accent); color: var(--accent); }}
    .btn.active {{ background: var(--accent); color: #000; font-weight: 600; }}
    
    /* Metadata & Gaia */
    .meta-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 0.88rem; }}
    .meta-label {{ color: var(--text-muted); }}
    .meta-val {{ font-weight: 500; color: #fff; }}
    .gaia-box {{
      margin-top: 14px; padding: 12px; border-radius: 8px; background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.3); font-size: 0.85rem; line-height: 1.4;
    }}
    .chart-box {{ height: 260px; margin-top: 12px; }}
  </style>
</head>
<body>

  <header>
    <div>
      <h1>🔭 PlanetXSPHEREx <span class="badge">Science & Image Engine</span></h1>
      <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 4px;">Designed by Emil · NASA Space Apps Challenge</p>
    </div>
    <div style="font-size: 0.85rem; color: var(--accent);">
      ✓ Astrometric Alignment &nbsp;·&nbsp; ✓ Difference Dipoles &nbsp;·&nbsp; ✓ 102ch Spectra &nbsp;·&nbsp; ✓ Gaia DR3 Verified
    </div>
  </header>

  <nav class="target-nav" id="targetNav"></nav>

  <div class="grid">
    <!-- Left Column: Blink & Difference Viewer -->
    <div class="card">
      <div class="card-title">
        <span id="targetTitle">Target Viewer</span>
        <span class="badge" id="targetTypeBadge">Type</span>
      </div>

      <div class="viewer-container">
        <div class="canvas-wrap">
          <img id="viewerImage" src="" alt="FITS Display">
          <div class="crosshair" id="crosshair"></div>
          <div class="viewer-overlay" id="frameOverlay">Epoch 1</div>
        </div>

        <div class="controls">
          <button class="btn" id="playBtn" onclick="togglePlay()">⏸ Pause</button>
          <button class="btn" id="diffBtn" onclick="toggleDiff()">Toggle Difference (ΔI)</button>
          <button class="btn" id="invertBtn" onclick="toggleInvert()">Invert (Negative)</button>
          <button class="btn" onclick="stepFrame(-1)">◀ Prev</button>
          <button class="btn" onclick="stepFrame(1)">Next ▶</button>
        </div>
      </div>

      <div style="margin-top: 16px;">
        <div class="card-title" style="font-size: 0.95rem; margin-bottom: 8px;">Target Science & Astrometry</div>
        <div class="meta-row"><span class="meta-label">Coordinates</span><span class="meta-val" id="metaCoords">--</span></div>
        <div class="meta-row"><span class="meta-label">Phenomenon</span><span class="meta-val" id="metaPhenomenon" style="max-width: 65%; text-align: right;">--</span></div>
        <div class="gaia-box" id="gaiaBox">Loading Gaia DR3 astrometry...</div>
      </div>
    </div>

    <!-- Right Column: Spectrum & Light Curve -->
    <div style="display: flex; flex-direction: column; gap: 24px;">
      <!-- Spectrum Card -->
      <div class="card">
        <div class="card-title">
          <span>SPHEREx 102-Channel Near-Infrared Spectrum (0.75 – 5.0 µm)</span>
          <span style="font-size: 0.8rem; color: var(--text-muted);">Detectors D1–D6</span>
        </div>
        <div class="chart-box">
          <canvas id="spectrumChart"></canvas>
        </div>
      </div>

      <!-- Light Curve Card -->
      <div class="card">
        <div class="card-title">
          <span>Multi-Epoch Photometric Light Curve</span>
          <span class="badge" id="variableBadge">Variable</span>
        </div>
        <div class="chart-box">
          <canvas id="lightCurveChart"></canvas>
        </div>
      </div>
    </div>
  </div>

  <script>
    const DATA = {data_json};
    let currentTargetKey = "barnard";
    let currentFrameIdx = 0;
    let isPlaying = true;
    let isDiffMode = false;
    let playInterval = null;
    let spectrumChart = null;
    let lightCurveChart = null;

    function init() {{
      const nav = document.getElementById("targetNav");
      Object.keys(DATA).forEach(key => {{
        const btn = document.createElement("button");
        btn.className = "target-btn" + (key === currentTargetKey ? " active" : "");
        btn.textContent = DATA[key].target.name;
        btn.onclick = () => selectTarget(key);
        nav.appendChild(btn);
      }});

      selectTarget(currentTargetKey);
      startPlayback();
    }}

    function selectTarget(key) {{
      currentTargetKey = key;
      document.querySelectorAll(".target-btn").forEach((b, i) => {{
        b.classList.toggle("active", Object.keys(DATA)[i] === key);
      }});

      const tData = DATA[key];
      document.getElementById("targetTitle").textContent = tData.target.name;
      document.getElementById("targetTypeBadge").textContent = tData.target.id.toUpperCase();
      document.getElementById("metaCoords").textContent = `RA ${{tData.target.ra_deg.toFixed(4)}}°, Dec ${{tData.target.dec_deg.toFixed(4)}}°`;
      
      const gaia = tData.gaia_validation;
      document.getElementById("gaiaBox").innerHTML = `
        <strong>[Gaia DR3 Astrometry Verification]</strong><br>
        Status: <span style="color: ${{gaia.is_match ? 'var(--dipole-pos)' : 'var(--dipole-neg)'}}">${{gaia.status}}</span><br>
        ${{gaia.validation_message}}<br>
        ${{gaia.accumulated_shift_since_2016_arcsec ? `Cumulative Proper Motion: <b>${{gaia.accumulated_shift_since_2016_arcsec}}″</b> (since 2016)` : ''}}
      `;

      isDiffMode = false;
      document.getElementById("diffBtn").classList.remove("active");
      currentFrameIdx = 0;
      updateViewer();
      updateCharts(tData);
    }}

    function updateViewer() {{
      const tData = DATA[currentTargetKey];
      const img = document.getElementById("viewerImage");
      const overlay = document.getElementById("frameOverlay");

      if (isDiffMode) {{
        img.src = tData.difference_frame.data_uri;
        overlay.textContent = "Difference Image (ΔI = Last - First)";
      }} else {{
        const frame = tData.frames[currentFrameIdx];
        img.src = frame.data_uri;
        overlay.textContent = `Epoch ${{frame.epoch_index}} (${{frame.year}})`;
      }}
    }}

    function togglePlay() {{
      isPlaying = !isPlaying;
      document.getElementById("playBtn").textContent = isPlaying ? "⏸ Pause" : "▶ Play";
      if (isPlaying) startPlayback(); else clearInterval(playInterval);
    }}

    function startPlayback() {{
      clearInterval(playInterval);
      playInterval = setInterval(() => {{
        if (isPlaying && !isDiffMode) {{
          const tData = DATA[currentTargetKey];
          currentFrameIdx = (currentFrameIdx + 1) % tData.frames.length;
          updateViewer();
        }}
      }}, 600);
    }}

    function toggleDiff() {{
      isDiffMode = !isDiffMode;
      document.getElementById("diffBtn").classList.toggle("active", isDiffMode);
      updateViewer();
    }}

    function toggleInvert() {{
      const img = document.getElementById("viewerImage");
      img.style.filter = img.style.filter === "invert(1)" ? "invert(0)" : "invert(1)";
    }}

    function stepFrame(delta) {{
      isDiffMode = false;
      document.getElementById("diffBtn").classList.remove("active");
      const tData = DATA[currentTargetKey];
      currentFrameIdx = (currentFrameIdx + delta + tData.frames.length) % tData.frames.length;
      updateViewer();
    }}

    function updateCharts(tData) {{
      // 1. Spectrum Chart
      const specData = tData.spectrum.data;
      const ctxSpec = document.getElementById("spectrumChart").getContext("2d");
      if (spectrumChart) spectrumChart.destroy();
      spectrumChart = new Chart(ctxSpec, {{
        type: 'line',
        data: {{
          labels: specData.map(d => d.wavelength_um),
          datasets: [{{
            label: 'Flux Density',
            data: specData.map(d => d.flux),
            borderColor: '#38bdf8',
            backgroundColor: 'rgba(56, 189, 248, 0.1)',
            borderWidth: 2,
            pointRadius: 1,
            fill: true
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ title: {{ display: true, text: 'Wavelength (µm)', color: '#94a3b8' }}, grid: {{ color: '#223152' }} }},
            y: {{ title: {{ display: true, text: 'Flux (mJy)', color: '#94a3b8' }}, grid: {{ color: '#223152' }} }}
          }}
        }}
      }});

      // 2. Light Curve Chart
      const lcData = tData.light_curve.light_curve;
      const ctxLc = document.getElementById("lightCurveChart").getContext("2d");
      if (lightCurveChart) lightCurveChart.destroy();
      document.getElementById("variableBadge").textContent = tData.light_curve.is_variable ? "VARIABLE" : "STABLE";
      document.getElementById("variableBadge").style.borderColor = tData.light_curve.is_variable ? "#4ade80" : "#94a3b8";

      lightCurveChart = new Chart(ctxLc, {{
        type: 'scatter',
        data: {{
          datasets: [{{
            label: 'Observed Epochs',
            data: lcData.map(d => ({{ x: d.mjd, y: d.flux }})),
            backgroundColor: '#4ade80',
            borderColor: '#22c55e',
            showLine: true,
            borderWidth: 2,
            pointRadius: 6
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ title: {{ display: true, text: 'Modified Julian Date (MJD)', color: '#94a3b8' }}, grid: {{ color: '#223152' }} }},
            y: {{ title: {{ display: true, text: 'Relative Flux', color: '#94a3b8' }}, grid: {{ color: '#223152' }} }}
          }}
        }}
      }});
    }}

    window.onload = init;
  </script>
</body>
</html>
"""
    output_path = Path("preview.html")
    output_path.write_text(html_content, encoding="utf-8")
    print(f"✓ Standalone interactive dashboard written to: {output_path.resolve()}")

if __name__ == "__main__":
    generate_html_preview()
