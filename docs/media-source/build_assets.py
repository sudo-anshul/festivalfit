"""Build the README tour and diagrams from real, unmodified UI screenshots.

Usage: python build_assets.py /path/to/captured/screenshots
Requires Pillow. Generated figures use FestivalFit's product palette.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parents[1] / "assets"
PAPER, INK, LIME, LAVENDER, PURPLE = "#f6f5f0", "#2d263b", "#d7ef86", "#eee8f4", "#705488"


def font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("Install Arial or DejaVu Sans to render the caption frame.")


def product_tour(captures):
    scenes = [
        ("profile", "01", "Start with your film.", "Exact runtime. Release history. The goals that matter.", 2700),
        ("research", "02", "Choose your research depth.", "A quick shortlist, or fuller rule-page verification.", 3000),
        ("report", "03", "Read the decision. Inspect the evidence.", "Potential matches, open questions and quoted blockers.", 4000),
        ("plan", "04", "Turn a shortlist into a plan.", "Compare options and keep known fees in view.", 3500),
        ("export", "05", "Take your research with you.", "PDF / Markdown / CSV / JSON, from the same report.", 3000),
    ]
    frames = []
    for name, number, title, subtitle, duration in scenes:
        screenshot = Image.open(captures / f"{name}.png").convert("RGB")
        assert screenshot.size == (1280, 850)
        screenshot.save(ASSETS / "screens" / f"{name}.png", optimize=True)
        frame = Image.new("RGB", (1400, 1060), INK)
        draw = ImageDraw.Draw(frame)
        draw.rounded_rectangle((54, 25, 110, 81), radius=14, fill=LIME)
        draw.text((65, 35), number, font=font(30, True), fill=INK)
        draw.text((132, 28), title, font=font(34, True), fill=PAPER)
        draw.text((132, 68), subtitle, font=font(20), fill=LAVENDER)
        frame.paste(screenshot, (60, 113))
        draw.rounded_rectangle((59, 112, 1340, 964), radius=3, outline=PURPLE, width=2)
        draw.text((60, 990), "FICTIONAL SAMPLE  /  ACTUAL HOSTED INTERFACE", font=font(19, True), fill=LIME)
        for index in range(5):
            x = 1210 + index * 28
            draw.ellipse((x, 993, x + 12, 1005), fill=LIME if index == int(number) - 1 else PURPLE)
        frames.append((frame.resize((1120, 848), Image.Resampling.LANCZOS), duration))
    frames[2][0].save(ASSETS / "tour-poster.png", optimize=True)
    palette_strip = Image.new("RGB", (1120, 848 * len(frames)))
    for index, (frame, _) in enumerate(frames):
        palette_strip.paste(frame, (0, 848 * index))
    palette = palette_strip.quantize(colors=192, method=Image.Quantize.MEDIANCUT)
    animation, durations = [], []
    for index, (frame, duration) in enumerate(frames):
        animation.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
        durations.append(duration)
        following = frames[(index + 1) % len(frames)][0]
        for weight in (.25, .5, .75):
            blended = Image.blend(frame, following, weight)
            animation.append(blended.quantize(palette=palette, dither=Image.Dither.NONE))
            durations.append(80)
    animation[0].save(ASSETS / "product-tour.gif", save_all=True, append_images=animation[1:], duration=durations, loop=0, optimize=True, disposal=2)


def svg_document(width, height, title, description, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{title}</title><desc id="desc">{description}</desc>
<rect width="{width}" height="{height}" rx="18" fill="{PAPER}"/>
<style>text{{font-family:Arial,Helvetica,sans-serif;fill:{INK}}}.label{{font-size:16px;font-weight:700;letter-spacing:1.6px;fill:{PURPLE}}}.heading{{font-family:Georgia,serif;font-size:32px}}.body{{font-size:18px}}.muted{{fill:#655d6f}}.small{{font-size:16px}}</style>
{body}</svg>'''


def diagrams():
    nodes = [
        (44, "01 / YOUR FILM", "A precise profile", ["Runtime, countries,", "screenings and goals"]),
        (292, "02 / GEMINI", "Plan the search", ["Target current editions", "and relevant rules"]),
        (540, "03 / PARALLEL", "Retrieve evidence", ["Search + optional", "full-page extraction"]),
        (788, "04 / GEMINI + PYTHON", "Assess and verify", ["Extract rules; check", "quotes and conditions"]),
        (1036, "05 / YOUR DECISION", "A cited shortlist", ["Compare, save and", "export one snapshot"]),
    ]
    body = '<text x="44" y="44" class="label">THE RESEARCH LOOP</text><text x="44" y="89" class="heading">A bounded agent. An inspectable decision.</text>'
    body += '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="#705488"/></marker></defs>'
    for index, (x, label, title, lines) in enumerate(nodes):
        fill = LIME if index == 4 else "#ffffff"
        body += f'<rect x="{x}" y="129" width="216" height="162" rx="12" fill="{fill}" stroke="#dfdbe4"/><text x="{x+16}" y="162" class="label" style="font-size:13px;letter-spacing:.8px">{label}</text><text x="{x+16}" y="197" style="font-size:21px;font-weight:700">{title}</text>'
        for row, line in enumerate(lines):
            body += f'<text x="{x+16}" y="{231+26*row}" class="body muted">{line}</text>'
        if index < 4:
            body += f'<path d="M{x+222} 211 H{x+241}" stroke="#705488" stroke-width="2" marker-end="url(#arrow)"/>'
    body += '<path d="M896 300 V331 H648 V300" fill="none" stroke="#705488" stroke-width="2" stroke-dasharray="5 5" marker-end="url(#arrow)"/><text x="583" y="366" class="small muted">One optional follow-up for gaps or alternatives</text>'
    body += '<path d="M44 394 H1252" stroke="#dfdbe4"/><text x="44" y="429" class="body">Cloud Run + service identity + Secret Manager</text><text x="1252" y="429" class="body" text-anchor="end">180-second limit · partial findings preserved</text>'
    (ASSETS / "research-loop.svg").write_text(svg_document(1296, 460, "FestivalFit research loop", "Your film profile goes to Gemini search planning, Parallel Search and optional Extract, Gemini assessment and local evidence validation, then a cited report. One optional follow-up researches gaps. Cloud Run hosts the bounded request.", body))

    body = '<text x="44" y="43" class="label">VERIFIED, WITH CONTEXT</text><text x="44" y="87" class="heading">The checks behind the demo.</text>'
    body += '<path d="M580 116 V319" stroke="#dfdbe4"/>'
    for x, number, label in [(44, "126", "automated tests"), (225, "4", "export formats"), (407, "10", "viewport widths")]:
        body += f'<text x="{x}" y="189" style="font-size:64px;font-family:Georgia,serif">{number}</text><text x="{x}" y="225" class="body muted">{label}</text>'
    body += '<text x="44" y="284" class="small muted">Recorded release checks · Firefox + Chrome layouts</text>'
    body += '<text x="620" y="132" class="label">HOSTED RUNS / 09 SEP 2026</text>'
    for y, label, seconds, color, detail in [(181, "Quick", 17.0, PURPLE, "18 sources"), (248, "Detailed", 18.9, INK, "18 sources + 3 expanded pages")]:
        length = 320 * seconds / 20
        body += f'<text x="620" y="{y}" class="body">{label}</text><rect x="720" y="{y-19}" width="{length}" height="24" rx="4" fill="{color}"/><text x="{733+length}" y="{y}" class="body" style="font-weight:700">{seconds:.1f}s</text><text x="720" y="{y+27}" class="small muted">{detail}</text>'
    body += '<text x="620" y="315" class="small muted">Two individual observations; not a performance benchmark.</text>'
    (ASSETS / "verification.svg").write_text(svg_document(1296, 354, "Observed release checks and hosted research timings", "The recorded release passed 126 tests, supports 4 export formats and was checked at 10 viewport widths in Firefox and Chrome. One Quick run took 17.0 seconds; one Detailed run took 18.9 seconds. These are individual smoke tests, not a benchmark.", body))


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "screens").mkdir(exist_ok=True)
    product_tour(Path(sys.argv[1]))
    diagrams()
    print(json.dumps({str(path.relative_to(ASSETS)): path.stat().st_size for path in ASSETS.rglob('*') if path.is_file()}, indent=2))
