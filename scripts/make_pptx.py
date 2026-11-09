"""Build docs/presentation.pptx (6 slides, simple English, editable). Numbers are read from saved results."""
import glob
import json
import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
NAVY, TEAL, GREY = RGBColor(0x1F, 0x2A, 0x44), RGBColor(0x1B, 0x7F, 0x8C), RGBColor(0x55, 0x5B, 0x6E)


def latest(provider):
    files = sorted(glob.glob(str(ROOT / "evals" / "results" / f"eval_*_{provider}.json")))
    return json.loads(Path(files[-1]).read_text(encoding="utf-8"))["summary"] if files else None


def tests_line():
    p = ROOT / "evals" / "results" / "pytest_latest.txt"
    if p.exists():
        m = re.search(r"(\d+) passed(?:, (\d+) failed)?", p.read_text(encoding="utf-8"))
        if m:
            return f"{m.group(1)} automated tests passed" + (f", {m.group(2)} failed" if m.group(2) else "")
    return "automated tests: see README"


def add_slide(prs, title, bullets, size=20):
    s = prs.slides.add_slide(prs.slide_layouts[5])                 # standard "Title Only" layout
    s.shapes.title.text = title
    t = s.shapes.title.text_frame.paragraphs[0]
    t.font.size, t.font.bold, t.font.color.rgb = Pt(32), True, NAVY
    if bullets:
        tb = s.shapes.add_textbox(Inches(0.7), Inches(1.7), Inches(8.6), Inches(5))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, b in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = "• " + b
            p.font.size, p.font.color.rgb = Pt(size), GREY
            p.space_after = Pt(10)
    return s


def main():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(10), Inches(7.5)
    mock, real = latest("mock"), latest("ollama")

    add_slide(prs, "1. The problem", [
        "Important answers are scattered across wikis, decks, reports and meeting notes.",
        "Finding all work on one topic, such as personalization, takes hours and people still miss things.",
        "Some documents are confidential, and old or conflicting documents are easy to trust by mistake.",
        "Leaders and product teams need a fast, complete answer they can check and trust.",
    ])
    add_slide(prs, "2. Our solution", [
        "EKRA is a research assistant that plans its own research steps and writes a cited report.",
        "It only reads documents the person is allowed to open.",
        "Every statement links to a source; if it cannot find support, it says so.",
        "Runs on a local AI model, so company data stays on the machine.",
    ])
    s = add_slide(prs, "3. How it works", [], 20)
    steps = ["Ask a question", "Plan the search", "Find and read sources", "Check each claim", "Cited report"]
    for i, label in enumerate(steps):
        x = Inches(0.4 + i * 1.9)
        box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(2.2), Inches(1.65), Inches(1.2))
        box.fill.solid()
        box.fill.fore_color.rgb = TEAL
        box.text_frame.text = label
        box.text_frame.paragraphs[0].font.size = Pt(15)
        box.text_frame.paragraphs[0].font.bold = True
        box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        box.text_frame.word_wrap = True
        if i < len(steps) - 1:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + Inches(1.67), Inches(2.65), Inches(0.2), Inches(0.3))
            a.fill.solid()
            a.fill.fore_color.rgb = NAVY
    tb = s.shapes.add_textbox(Inches(0.7), Inches(4.0), Inches(8.6), Inches(3))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, t in enumerate(["If an important document is missing from what it read, it goes back and reads it.",
                           "Statuses (shipped, paused, cancelled) come from clear rules, not AI guesses.",
                           "If two sources disagree, the report shows both."]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "• " + t
        p.font.size, p.font.color.rgb = Pt(18), GREY
        p.space_after = Pt(8)

    res = []
    if mock:
        res.append(f"Wiring checks (mock AI): {mock['passed']} of {mock['total']} test questions passed, "
                   f"{mock['acl_leaks']} permission leaks.")
    if real:
        res.append(f"Real local AI ({real['models']['fast']} + {real['models']['main']}): {real['passed']} of "
                   f"{real['total']} test questions passed, {real['acl_leaks']} permission leaks, "
                   f"average {real['avg_latency_ms'] // 1000} seconds per question.")
    res += [tests_line() + ".",
            "Example question: 9 initiatives found, status history and 1 conflicting report flagged.",
            "All data is synthetic (made up). The mock result checks the plumbing, not AI quality.",
            "These questions were also used to find and fix bugs, so this is a development check, "
            "not proof of the same accuracy on new questions or real documents."]
    add_slide(prs, "4. Demo results", res, 18)
    add_slide(prs, "5. Safety and trust", [
        "Permissions are checked before search and again before the answer is shown.",
        "Instructions hidden inside documents are removed and never followed.",
        "Claims with numbers that are not in the source are dropped.",
        "Every run is recorded: who asked, which documents were used, which model, which settings.",
        "People can rate answers and flag problems; the system never takes actions on its own.",
    ], 19)
    add_slide(prs, "6. Next steps", [
        "Limits today: made-up data, hand-tagged initiatives, rule-based statuses, one machine.",
        "Next: connect real wikis and drives, add company sign-in, find initiatives automatically.",
        "Then: run a pilot with one team on real documents and measure time saved.",
        "Needed to go live: security review, data owner sign-off, hosting, a support owner.",
    ], 19)
    out = ROOT / "docs" / "presentation.pptx"
    prs.save(out)
    print(f"saved {out} with {len(Presentation(out).slides)} slides")


if __name__ == "__main__":
    main()
