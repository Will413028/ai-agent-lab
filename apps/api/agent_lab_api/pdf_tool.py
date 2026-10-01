import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "NotoSansTC-Regular.ttf"


def generate_pdf(content: str) -> bytes:
    if "NotoSansTC" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("NotoSansTC", str(FONT_PATH)))
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=52,
        bottomMargin=52,
        title="AI Agent Lab 任務產物",
    )
    body = ParagraphStyle(
        "body",
        fontName="NotoSansTC",
        fontSize=11,
        leading=19,
        textColor=colors.HexColor("#283329"),
        wordWrap="CJK",
        spaceAfter=8,
    )
    title = ParagraphStyle("title", parent=body, fontSize=18, leading=27, spaceAfter=14)
    story = []
    for line in content.splitlines():
        is_heading = line.startswith("# ") or line.startswith("## ")
        text = line.removeprefix("## ").removeprefix("# ") if is_heading else line
        if text.strip():
            story.append(Paragraph(escape(text), title if is_heading else body))
        else:
            story.append(Spacer(1, 8))

    def footer(canvas, doc):
        canvas.setFont("NotoSansTC", 8)
        canvas.setFillColor(colors.HexColor("#637360"))
        canvas.drawString(48, 30, "AI Agent Lab")
        canvas.drawRightString(A4[0] - 48, 30, str(doc.page))

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
