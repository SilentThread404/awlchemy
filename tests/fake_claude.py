"""Stand-in for Claude Code: replaces claude_code.run, checks the options, yields canned SDK messages."""
import uuid
from awlchemy import claude_code as cc

CALLS = []

def _result(structured=None, text="", sid=None):
    return cc.ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id=sid or uuid.uuid4().hex, result=text, structured_output=structured)

def _ev(event):
    return cc.StreamEvent(uuid=uuid.uuid4().hex, session_id="s", event=event)

GUIDE = {
 "summary": "A two-layer key fob with a folded connector strap trapped in the perimeter seam. A perfect first project: one straight saddle-stitch line around a rounded rectangle.",
 "difficulty": "beginner", "difficulty_reason": "Only straight stitching and simple gluing; the three-layer connector is the one fiddly part.",
 "time_estimate": "2–3 hours, plus glue drying", "finished_size": "40 × 80 mm body",
 "skills_learned": ["accurate cutting", "pricking stitch holes", "saddle stitch", "edge burnishing"],
 "before_you_start": "Print page 3 at **100% / Actual size** and measure the 20 mm calibration square.",
 "leather": [{"parts": "G1, G2 panels", "leather": "Vegetable-tanned cowhide, full grain", "thickness_mm": "1.2–1.6", "thickness_oz": "3–4", "why": "Firm enough to keep its shape, burnishes well.", "alternative": "Any veg-tan offcut of similar thickness"},
             {"parts": "G3 connector strap", "leather": "Vegetable-tanned cowhide", "thickness_mm": "1.0–1.2", "thickness_oz": "2.5–3", "why": "Thinner so the folded strap isn't bulky inside the seam."}],
 "leather_amount": "One 10 × 15 cm offcut covers everything with room for a test piece.",
 "hardware": [{"item": "Split key ring", "quantity": "1", "size": "25–30 mm"}, {"item": "Swivel snap hook", "quantity": "1", "notes": "eye must fit the ring"}],
 "consumables": [{"item": "Waxed polyester thread", "spec": "0.6–0.8 mm"}, {"item": "Contact cement", "notes": "thin layer, keep clear of holes"}],
 "tools": [{"name": "Craft knife", "purpose": "Cutting the pieces", "essential": True, "substitute": "Sharp utility knife"},
           {"name": "Diamond stitching chisel 4 mm", "purpose": "Punching even stitch holes", "essential": True, "substitute": "1 mm round punch or an awl"},
           {"name": "Edge beveler size 1", "purpose": "Rounding the edges", "essential": False, "substitute": "Sandpaper on a block"},
           {"name": "Wood slicker", "purpose": "Burnishing", "essential": False, "substitute": "Canvas cloth"}],
 "steps": [{"title": "Print and check the pattern", "pattern_says": "Print on A4 at 100% and measure the calibration squares.", "how_to": "Open the **original PDF**, choose *Actual size*. Measure the 20 mm square with a steel ruler.", "techniques": ["pattern printing"], "tips": ["Glue the printout to cardstock for a reusable template."], "watch_out": ["Fit to page shrinks everything by ~3%."]},
           {"title": "Cut and mark the leather pieces", "pattern_says": "Cut G1, G2, G3 and transfer every stitching hole.", "how_to": "Trace with a silver pen on the **flesh side**. Cut the straight lines against a steel ruler in 2–3 light passes.", "techniques": ["cutting leather"], "watch_out": ["A dull blade drags and tears."]},
           {"title": "Stitch the perimeter", "pattern_says": "Saddle-stitch the full perimeter, backstitch 2–3 holes.", "how_to": "Thread a needle on each end of ~4× the seam length of thread...", "techniques": ["saddle stitch"], "tips": ["Keep the same needle on top each stitch."]}],
 "unclear_points": ["The pattern doesn't give a stitch spacing; 3–4 mm suits 1 mm holes."],
 "practice_first": "Stitch 10 cm on a scrap folded in two.",
 "finishing_and_care": "Burnish the edges with water or gum tragacanth; a little balm on the grain."
}

def fake_run(prompt, opts):
    CALLS.append((prompt, opts))
    assert opts.permission_mode == "dontAsk" and opts.setting_sources == [] and opts.strict_mcp_config
    assert opts.env.get("ANTHROPIC_API_KEY") == ""
    assert not {"Bash", "Write", "Edit"} & set(opts.tools)
    guard = opts.hooks["PreToolUse"][0]
    assert guard.matcher == "Read|WebFetch" and guard.hooks == [cc.guard_tools]
    schema = (opts.output_format or {}).get("schema") or {}
    if "steps" in schema.get("properties", {}):  # build guide
        assert opts.tools == ["Read"] and "page 1:" in prompt, prompt[:200]
        yield cc.AssistantMessage(content=[cc.ToolUseBlock(id="t1", name="Read", input={"file_path": "x/pattern.pdf"})], model="m")
        yield _result(GUIDE)
    elif "techniques" in schema.get("properties", {}):  # video search
        assert opts.tools == ["WebSearch"]
        asked = [l[2:] for l in prompt.splitlines() if l.startswith("- ")]
        yield cc.AssistantMessage(content=[cc.ToolUseBlock(id="t1", name="WebSearch", input={"query": "saddle stitch tutorial"})], model="m")
        yield cc.UserMessage(content=[cc.ToolResultBlock(tool_use_id="t1", content=
            "Links: https://www.youtube.com/watch?v=dQw4w9WgXcQ https://www.youtube.com/watch?v=9bZkp7q19f0")])
        rec = {"techniques": [
            {"technique": t, "videos": [
                {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ" if "stitch" in t else "https://www.youtube.com/watch?v=9bZkp7q19f0",
                 "title": f"How to do {t} (beginner)", "channel": "Leathercraft Channel", "why": f"Close-up demo of {t}."},
                {"url": "https://youtu.be/AAAAAAAAAAA", "title": "Invented video", "channel": "Nobody"}]}
            for t in asked]}
        yield _result(rec)
    else:  # chat
        assert opts.include_partial_messages and "WebSearch" in opts.tools
        if opts.resume:
            assert "Conversation so far" not in prompt
        yield cc.AssistantMessage(content=[cc.ToolUseBlock(id="t1", name="WebSearch", input={"query": "veg tan leather shop Netherlands"})], model="m")
        text = "For a first key fob, use **1.2–1.6 mm** veg-tan. Try the Card Holder (#5) next. [Example leather shop](https://example.com/leer) ships across NL."
        for i in range(0, len(text), 40):
            yield _ev({"type": "content_block_delta", "delta": {"type": "text_delta", "text": text[i:i + 40]}})
        yield cc.AssistantMessage(content=[cc.TextBlock(text=text)], model="m")
        yield _result(text=text, sid=opts.resume or "session-1")

def install():
    cc.run = fake_run
