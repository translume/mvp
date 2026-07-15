from __future__ import annotations

import base64
from pathlib import Path

pre {
  background: #ccc !important;
}

TRANSLUME_CSS = """
:root {
  --translume-violet: #6d28d9;
  --translume-indigo: #4f46e5;
  --translume-blue: #2563eb;
  --translume-cyan: #0891b2;
  --translume-teal: #0d9488;
  --translume-ink: #000;
  --translume-muted: #5f6b7a;
  --translume-line: #333;
  --translume-soft: #333;
  --translume-warning: #9a6700;
  --translume-danger: #b42318;
}

.gradio-container {
  background: #ffffff !important;
  color: var(--translume-ink) !important;
  font-family: "M PLUS Rounded 1c", "Avenir Next", "Segoe UI", sans-serif !important;
  max-width: 1680px !important;
}

h1, h2, h3, h4, .prose h1, .prose h2, .prose h3 {
  font-family: "Elms Sans", "Avenir Next", "Segoe UI", sans-serif !important;
  letter-spacing: -0.02em;
  color: var(--translume-ink) !important;
}

.translume-header {
  display: grid;
  grid-template-columns: minmax(220px, 440px) 1fr;
  gap: 28px;
  align-items: center;
  padding: 18px 0 24px 0;
  border-bottom: 1px solid var(--translume-line);
}

.translume-header img {
  display: block;
  width: 100%;
  max-width: 440px;
  height: auto;
}

.translume-header-copy h1 {
  margin: 0 0 8px 0;
  font-size: clamp(1.65rem, 3vw, 2.45rem);
  background: linear-gradient(90deg, var(--translume-violet), var(--translume-blue), var(--translume-teal));
  -webkit-background-clip: text;
  color: transparent !important;
}

.translume-header-copy p {
  margin: 0;
  max-width: 900px;
  color: var(--translume-muted);
  line-height: 1.55;
}

.translume-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.translume-badge {
  border: 1px solid var(--translume-line);
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 0.78rem;
  color: var(--translume-indigo);
  background: #ffffff;
}

.translume-panel {
  border: 1px solid var(--translume-line) !important;
  border-radius: 14px !important;
  background: #ffffff !important;
  box-shadow: none !important;
}

.translume-status {
  border-left: 4px solid var(--translume-blue);
  padding: 10px 14px;
  background: var(--translume-soft);
  border-radius: 0 10px 10px 0;
}


.translume-decision-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin: 8px 0 16px 0;
}

.translume-decision-card {
  border: 1px solid var(--translume-line);
  border-radius: 14px;
  padding: 12px 14px;
  background: linear-gradient(180deg, #ffffff, var(--translume-soft));
}

.translume-decision-label {
  display: block;
  color: var(--translume-muted);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  margin-bottom: 6px;
  text-transform: uppercase;
}

.translume-decision-value {
  display: block;
  color: var(--translume-ink);
  font-size: 0.94rem;
  line-height: 1.42;
  overflow-wrap: anywhere;
}

.translume-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.translume-summary-item {
  border: 1px solid var(--translume-line);
  border-radius: 10px;
  padding: 10px 12px;
  background: #ffffff;
}

.translume-summary-label {
  display: block;
  color: var(--translume-muted);
  font-size: 0.75rem;
  margin-bottom: 3px;
}

.translume-summary-value {
  display: block;
  color: var(--translume-ink);
  font-size: 0.96rem;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.translume-summary-list {
  margin: 8px 0 0 18px;
  padding: 0;
  color: var(--translume-muted);
}

.translume-summary-list li {
  margin: 4px 0;
}

.translume-safety-note {
  border-left: 4px solid var(--translume-violet);
  padding: 10px 14px;
  background: #faf8ff;
  color: var(--translume-ink);
  border-radius: 0 10px 10px 0;
}

.translume-error {
  border-left: 4px solid var(--translume-danger);
  padding: 10px 14px;
  background: #fff7f6;
  color: var(--translume-danger);
  border-radius: 0 10px 10px 0;
}

button.primary, .primary {
  background: linear-gradient(90deg, var(--translume-violet), var(--translume-blue), var(--translume-teal)) !important;
  border: none !important;
  color: #ffffff !important;
  box-shadow: none !important;
}

button.secondary, .secondary {
  background: #ffffff !important;
  border: 1px solid var(--translume-indigo) !important;
  color: var(--translume-indigo) !important;
  box-shadow: none !important;
}

.tabs, .tab-nav, .panel, .block {
  box-shadow: none !important;
}

a, .prose a {
  color: var(--translume-indigo) !important;
}

a:hover, .prose a:hover {
  color: var(--translume-teal) !important;
}

@media (max-width: 800px) {
  .translume-header {
    grid-template-columns: 1fr;
  }
}
"""


def header_html() -> str:
    """Return a self-contained branded header without external asset calls."""
    logo_path = Path(__file__).resolve().parent / "assets" / "translume-logo.png"
    if not logo_path.exists():
        raise FileNotFoundError(f"Translume logo asset is missing: {logo_path}")
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"""
    <section class="translume-header">
      <img src="data:image/png;base64,{encoded}" alt="Translume — Illuminating Biomedical Discovery" />
      <div class="translume-header-copy">
        <h1>Oncologist Cockpit</h1>
        <p>
          Convert one oncology report into a source-backed tumor behavior
          intelligence brief with treatment logic, escape risks, biomarker
          monitoring, re-testing triggers, and next-test guidance.
        </p>
        <div class="translume-badges">
          <span class="translume-badge">Private local models</span>
          <span class="translume-badge">Clinician decision support</span>
          <span class="translume-badge">Human validation required</span>
        </div>
      </div>
    </section>
    """
