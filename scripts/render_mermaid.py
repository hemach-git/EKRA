"""Render each ```mermaid block in a markdown file to docs/img/diagram_<n>.png."""
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

MD = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/design.md")
OUT = MD.parent / "img"
OUT.mkdir(parents=True, exist_ok=True)

HTML = """<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<style>body{margin:0;background:#fff;font-family:Arial} #c{display:inline-block;padding:16px}</style>
</head><body><div id="c"><pre class="mermaid">%s</pre></div>
<script>
mermaid.initialize({startOnLoad:false, theme:'default',
  themeVariables:{fontSize:'18px'},
  flowchart:{nodeSpacing:30, rankSpacing:35, useMaxWidth:false},
  sequence:{mirrorActors:false, useMaxWidth:false},
  er:{useMaxWidth:false}});
mermaid.run().then(()=>{document.body.dataset.done='1'}).catch(e=>{document.body.dataset.err=String(e)});
</script></body></html>"""


def main():
    blocks = re.findall(r"```mermaid\n(.*?)```", MD.read_text(encoding="utf-8"), re.S)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(device_scale_factor=3, viewport={"width": 1600, "height": 1200})
        for i, code in enumerate(blocks, 1):
            esc = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            page.set_content(HTML % esc)
            page.wait_for_function("document.body.dataset.done || document.body.dataset.err", timeout=30000)
            err = page.evaluate("document.body.dataset.err")
            if err:
                raise SystemExit(f"diagram {i} failed: {err}")
            target = OUT / f"diagram_{i}.png"
            tmp = OUT / f"_tmp_{i}.png"
            page.locator("#c").screenshot(path=str(tmp))
            os.replace(tmp, target)
            print(f"rendered {target}")
        browser.close()


if __name__ == "__main__":
    main()
