# Manual fonts

The PDF manual uses **Mulish** (a friendly, lightly-rounded humanist sans) for its
Blender Blocks identity. `generate.py` loads these when present and falls back to Helvetica if
they're missing, so the tool still runs without them.

- `Mulish-Display.ttf` — weight 600, for headings / wordmark / badges
- `Mulish-Body.ttf` — weight 400, for labels and body text

Both are static instances baked from the Google Fonts Mulish variable font, licensed under
the SIL Open Font License 1.1 (see `OFL.txt`). To regenerate (dev-only, needs `fonttools`):

```sh
pip install fonttools
python - <<'PY'
import urllib.request
from fontTools import ttLib
from fontTools.varLib.instancer import instantiateVariableFont
url = "https://github.com/google/fonts/raw/main/ofl/mulish/Mulish%5Bwght%5D.ttf"
open("Mulish.ttf", "wb").write(urllib.request.urlopen(url).read())
for w, out in [(600, "Mulish-Display.ttf"), (400, "Mulish-Body.ttf")]:
    f = ttLib.TTFont("Mulish.ttf")
    instantiateVariableFont(f, {"wght": w}, inplace=True)
    f.save(out)
PY
```
