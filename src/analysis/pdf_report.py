"""
pdf_report.py — Automated Publication-Quality PDF Report Generator.

Compiles a comprehensive benchmark report including:
  - Executive summary and research overview
  - 3-Zone decision framework recommendations
  - 7 structured benchmark tables
  - 10 publication charts with captions and analysis
  - Break-even computational trade-offs
  - Header/footer with page numbers and authorship
"""

from __future__ import annotations

import csv
import io
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and print total page numbers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(
                36, 11 * inch - 28,
                "Serialization Benchmark Study: JSON vs JSON+GZIP vs MessagePack"
            )
            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.5)
            self.line(36, 11 * inch - 32, 8.5 * inch - 36, 11 * inch - 32)

        # Footer (all pages)
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(36, 36, 8.5 * inch - 36, 36)

        self.drawString(
            36, 24,
            "Built by Prithvi Kharje & Viraj Ravani"
        )
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * inch - 36, 24, page_str)
        self.restoreState()


def _load_csv_rows(csv_path: Path) -> List[List[str]]:
    """Load rows from a CSV file."""
    if not csv_path.exists():
        return []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        return [row for row in reader if row]


def _build_table_flowable(
    rows: List[List[str]],
    col_widths: Optional[List[float]] = None,
    styles: Optional[Dict[str, ParagraphStyle]] = None,
) -> Table:
    """Format CSV rows into a styled ReportLab Table."""
    if not rows:
        return Table([["No data available"]], colWidths=[500])

    p_body = styles["TableBody"] if styles else None
    p_head = styles["TableHead"] if styles else None

    table_data = []
    # Header
    head_row = []
    for cell in rows[0]:
        head_row.append(Paragraph(str(cell), p_head) if p_head else str(cell))
    table_data.append(head_row)

    # Body
    for r in rows[1:]:
        row_cells = []
        for cell in r:
            row_cells.append(Paragraph(str(cell), p_body) if p_body else str(cell))
        table_data.append(row_cells)

    num_cols = len(rows[0])
    if col_widths is None:
        total_w = 540.0
        w = total_w / num_cols
        col_widths = [w] * num_cols

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ])
    )
    return t


def generate_pdf_report(
    output_path_or_buffer: Any,
    tables_dir: Path = Path("results/tables"),
    plots_dir: Path = Path("plots"),
    summary_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Generate the complete benchmark PDF report.
    :param output_path_or_buffer: File path string, Path object, or io.BytesIO buffer.
    """
    doc = SimpleDocTemplate(
        output_path_or_buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=46,
    )

    sample_styles = getSampleStyleSheet()

    # Custom typography
    styles = {
        "DocTitle": ParagraphStyle(
            "DocTitle",
            parent=sample_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            alignment=0,
            spaceAfter=6,
        ),
        "DocSub": ParagraphStyle(
            "DocSub",
            parent=sample_styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#475569"),
            spaceAfter=14,
        ),
        "MetaBanner": ParagraphStyle(
            "MetaBanner",
            parent=sample_styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#64748b"),
        ),
        "SecHeading": ParagraphStyle(
            "SecHeading",
            parent=sample_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=14,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "SubSecHeading": ParagraphStyle(
            "SubSecHeading",
            parent=sample_styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=sample_styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#334155"),
            spaceAfter=8,
        ),
        "Callout": ParagraphStyle(
            "Callout",
            parent=sample_styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13.5,
            textColor=colors.HexColor("#1e293b"),
        ),
        "Caption": ParagraphStyle(
            "Caption",
            parent=sample_styles["Italic"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#64748b"),
            alignment=1,
            spaceAfter=12,
        ),
        "TableHead": ParagraphStyle(
            "TableHead",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#0f172a"),
        ),
        "TableBody": ParagraphStyle(
            "TableBody",
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#334155"),
        ),
    }

    story = []

    # 1. Header & Title Block
    story.append(Paragraph("Serialization Benchmark Study: JSON, Compressed JSON, and MessagePack", styles["DocTitle"]))
    story.append(Paragraph(
        "An End-to-End Workload- and Network-Aware Performance Study across Latency, Payload Compaction, and Break-Even Bandwidth",
        styles["DocSub"]
    ))

    # Meta banner
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    meta_p = Paragraph(
        f"<b>Authors:</b> Built by Prithvi Kharje &amp; Viraj Ravani &nbsp;|&nbsp; "
        f"<b>Environment:</b> Python 3.14 &bull; FastAPI Transport Harness &bull; psutil &nbsp;|&nbsp; "
        f"<b>Date:</b> {current_time_str}",
        styles["MetaBanner"]
    )
    story.append(meta_p)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=12))

    # 2. Executive Summary & 3-Zone Decision Framework
    story.append(Paragraph("1. Executive Summary &amp; Decision Framework", styles["SecHeading"]))
    exec_summary_text = (
        "This experimental benchmark evaluates end-to-end performance trade-offs among three serialization formats: "
        "<b>JSON</b> (human-readable baseline), <b>JSON + GZIP</b> (compression-optimized), and <b>MessagePack</b> "
        "(binary serialization). Total end-to-end wall-clock latency (<i>T</i><sub>e2e</sub> = <i>T</i><sub>ser</sub> + "
        "<i>T</i><sub>comp</sub> + <i>T</i><sub>net</sub> + <i>T</i><sub>decomp</sub> + <i>T</i><sub>deser</sub>), "
        "payload size reduction, and CPU/memory utilization are measured under controlled network profiles."
    )
    story.append(Paragraph(exec_summary_text, styles["Body"]))

    # 3-Zone Callout Box
    zone_box_data = [
        [Paragraph("<b>The 3-Zone Decision Framework:</b><br/>"
                   "&bull; <b>Zone 1 (No Switch, Gain &lt; 5%):</b> Stay with baseline JSON. Serialization/compression overhead is not amortized.<br/>"
                   "&bull; <b>Zone 2 (Evaluate, 5% &le; Gain &lt; 20%):</b> Context-dependent. Switch only if network-bound or bandwidth costs dominate.<br/>"
                   "&bull; <b>Zone 3 (Switch, Gain &ge; 20%):</b> Strongly recommend switching to MessagePack or JSON+GZIP for significant throughput.",
                   styles["Callout"])]
    ]
    t_zone = Table(zone_box_data, colWidths=[540])
    t_zone.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_zone)
    story.append(Spacer(1, 12))

    # 3. Tables 1 & 2
    story.append(Paragraph("2. Experimental Configuration &amp; Encoding/Decoding Benchmarks", styles["SecHeading"]))
    
    t1_rows = _load_csv_rows(tables_dir / "table1_config_dataset_summary.csv")
    if t1_rows:
        story.append(Paragraph("<b>Table 1: Experimental Configuration &amp; Dataset Summary</b>", styles["SubSecHeading"]))
        story.append(_build_table_flowable(t1_rows, styles=styles))
        story.append(Spacer(1, 10))

    t2_rows = _load_csv_rows(tables_dir / "table2_encoding_decoding_compression.csv")
    if t2_rows:
        story.append(Paragraph("<b>Table 2: Encoding, Decoding &amp; Compression Benchmark</b>", styles["SubSecHeading"]))
        story.append(_build_table_flowable(t2_rows, styles=styles))
        story.append(Spacer(1, 12))

    # 4. Tables 3 & 4
    story.append(Paragraph("3. Payload Transmission &amp; Relative Gain Benchmarks", styles["SecHeading"]))
    t3_rows = _load_csv_rows(tables_dir / "table3_payload_network_transmission.csv")
    if t3_rows:
        story.append(Paragraph("<b>Table 3: Payload &amp; Network Wire Transmission Benchmark</b>", styles["SubSecHeading"]))
        story.append(_build_table_flowable(t3_rows, styles=styles))
        story.append(Spacer(1, 10))

    t4_rows = _load_csv_rows(tables_dir / "table4_e2e_relative_gain.csv")
    if t4_rows:
        story.append(Paragraph("<b>Table 4: End-to-End Performance &amp; Relative Gain vs Baseline JSON</b>", styles["SubSecHeading"]))
        story.append(_build_table_flowable(t4_rows, styles=styles))
        story.append(Spacer(1, 12))

    # 5. Tables 5, 6, 7
    story.append(Paragraph("4. Break-Even Bandwidth &amp; Decision Model Recommendations", styles["SecHeading"]))
    t6_rows = _load_csv_rows(tables_dir / "table6_breakeven_computational_tradeoffs.csv")
    if t6_rows:
        story.append(Paragraph("<b>Table 6: Break-Even Bandwidth (B_BE) and Computational Trade-Off Results</b>", styles["SubSecHeading"]))
        # Narrow columns for table 6
        w6 = [90, 50, 60, 45, 55, 120, 120]
        story.append(_build_table_flowable(t6_rows, col_widths=w6, styles=styles))
        story.append(Spacer(1, 10))

    t7_rows = _load_csv_rows(tables_dir / "table7_decision_framework_recommendations.csv")
    if t7_rows:
        story.append(Paragraph("<b>Table 7: Final Decision Framework Classification &amp; Action Recommendations</b>", styles["SubSecHeading"]))
        w7 = [70, 75, 75, 65, 70, 65, 120]
        story.append(_build_table_flowable(t7_rows, col_widths=w7, styles=styles))
        story.append(Spacer(1, 12))

    # 6. Embedded Charts & Figures
    story.append(PageBreak())
    story.append(Paragraph("5. Publication Visualizations &amp; Empirical Charts", styles["SecHeading"]))
    story.append(Paragraph(
        "Below are the high-resolution empirical charts generated from measured benchmark runs, "
        "illustrating payload reduction, latency scaling, resource utilization, and break-even crossover points.",
        styles["Body"]
    ))
    story.append(Spacer(1, 8))

    chart_catalog = [
        ("payload/chart1_payload_vs_original.png", "Figure 1: Serialized Wire Payload vs Original Dataset Size across Formats"),
        ("performance/chart2_ser_deser_time_vs_payload.png", "Figure 2: CPU Serialization and Deserialization Processing Times vs Payload Size"),
        ("performance/chart3_e2e_latency_vs_payload.png", "Figure 3: Total End-to-End Latency vs Payload Size across Network Profiles"),
        ("performance/chart4_e2e_latency_vs_bandwidth.png", "Figure 4: Total Latency vs Network Bandwidth (Highlighting Break-Even Crossover)"),
        ("resources/chart6_cpu_memory_vs_payload.png", "Figure 5: Memory and CPU Resource Consumption Trade-Offs"),
        ("breakeven/chart7_net_saved_vs_cpu_cost.png", "Figure 6: Network Time Saved vs Compute Processing Overhead (Regime Separation)"),
        ("performance/chart8_relative_gain_vs_payload.png", "Figure 7: Relative Latency Gain (%) over Baseline JSON"),
        ("breakeven/chart9_breakeven_crossover.png", "Figure 8: Break-Even Bandwidth Curves (B_BE) across Payload Sizes"),
        ("breakeven/chart10_2d_decision_boundary.png", "Figure 9: 2D Decision Boundary Space (Payload Size vs Network Bandwidth)"),
    ]

    from PIL import Image as PILImage
    from reportlab.lib.utils import ImageReader

    for rel_path, caption in chart_catalog:
        img_path = plots_dir / rel_path
        if img_path.exists():
            try:
                with open(img_path, "rb") as f_img:
                    data = f_img.read()
                if len(data) < 100:
                    continue
                # Verify image can be decoded
                check_im = PILImage.open(io.BytesIO(data))
                check_im.load()

                img_stream = io.BytesIO(data)
                img = Image(img_stream, width=6.8 * inch, height=3.2 * inch)
                story.append(KeepTogether([
                    img,
                    Spacer(1, 4),
                    Paragraph(caption, styles["Caption"]),
                    Spacer(1, 10),
                ]))
            except Exception:
                continue

    # Build the document with the NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)


def get_pdf_report_bytes(
    tables_dir: Path = Path("results/tables"),
    plots_dir: Path = Path("plots"),
    summary_data: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Generate the PDF and return its raw binary bytes."""
    buf = io.BytesIO()
    generate_pdf_report(buf, tables_dir=tables_dir, plots_dir=plots_dir, summary_data=summary_data)
    buf.seek(0)
    return buf.getvalue()
