# README media

All artwork uses FestivalFit's existing cream, plum and lime identity. The ticket in the hero is a labeled fictional illustration. The product tour is assembled from screenshots of the actual hosted interface using the fictional sample; it is not a recording of a live research run.

- `index.html` and `DESIGN.md`: the deterministic, single-scene animated hero.
- `build_assets.py`: the framed product tour and SVG diagrams.
- `../assets/screens/`: unmodified screenshots captured at a 1280 × 850 viewport, September 9, 2026.
- `../VERIFICATION.md`: the source and limits of the validation graphic's numbers.

## Regenerate the hero

Requires Node.js 22+, FFmpeg and Hyperframes 0.8.32:

```sh
npx --yes hyperframes@0.8.32 check docs/media-source
npx --yes hyperframes@0.8.32 render docs/media-source --fps 15 --quality high --workers 1 --output hero.mp4
ffmpeg -ss 1.6 -t 8 -i hero.mp4 -filter_complex '[0:v]fps=12,scale=1120:512:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3' -loop 0 docs/assets/hero.gif
ffmpeg -ss 4.8 -i hero.mp4 -vf scale=1120:512 -frames:v 1 docs/assets/hero-poster.png
```

The GIF begins after the entrance animation, so its first frame is already readable. A static poster is available for reduced-motion preferences.

## Regenerate the tour and diagrams

With Pillow installed, run from the repository root:

```sh
python docs/media-source/build_assets.py docs/assets/screens
```

To capture new screenshots, use the public sample in a clean browser session. Capture the example film profile, research-depth screen, sample report, comparison with the first two sample candidates saved, and the shortlist export dialog. Keep all screenshots at 1280 × 850. Do not capture access codes or actual private film data.

The tour uses short crossfades between still screenshots. Static views and a poster are linked alongside it. Neither GIF requires runtime JavaScript in the README. These documentation assets are excluded from Cloud Build by the runtime-only upload allowlist.
