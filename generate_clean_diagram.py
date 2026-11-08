import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def draw_diagram():
    # 16:9 canvas at 300 DPI (5400x3300 px)
    fig, ax = plt.subplots(figsize=(20, 12), dpi=300)
    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Minimalist Black & White Theme
    COLOR_BORDER_BOLD = '#09090B'  # Deep pitch black
    COLOR_BORDER_CARD = '#27272A'  # Dark slate black
    COLOR_BORDER_SUB  = '#71717A'  # Subtle medium gray
    BG_WHITE = '#FFFFFF'
    BG_LIGHT = '#F8FAFC'           # Very light crisp tint
    BG_CORE  = '#F1F5F9'           # Slate container tint
    TEXT_BLACK = '#09090B'
    TEXT_MUTED = '#52525B'
    LINE_ARROW = '#09090B'

    def draw_card(x, y, w, h, title, subtitle="", bullets=None, bg=BG_WHITE, border=COLOR_BORDER_CARD, lw=1.6, r=1.6, title_size=10.5, sub_size=8.2):
        # Rounded box
        box = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            facecolor=bg,
            edgecolor=border,
            linewidth=lw,
            zorder=2
        )
        ax.add_patch(box)

        # Title
        ty = y + h - 1.6
        ax.text(x + w / 2, ty, title, ha='center', va='top', fontsize=title_size, fontweight='bold', color=TEXT_BLACK, zorder=3)

        # Subtitle
        curr_y = ty - 1.7
        if subtitle:
            ax.text(x + w / 2, curr_y, subtitle, ha='center', va='top', fontsize=sub_size, fontstyle='italic', color=TEXT_MUTED, zorder=3)
            curr_y -= 1.6

        # Bullets
        if bullets:
            curr_y -= 0.3
            for b in bullets:
                ax.text(x + 1.8, curr_y, f"•  {b}", ha='left', va='top', fontsize=sub_size, color=TEXT_BLACK, zorder=3)
                curr_y -= 1.65

        return (x + w / 2, y + h / 2)

    def draw_arrow(x1, y1, x2, y2, label="", label_pos=0.5, lw=1.6, rad=0):
        cstyle = f"arc3,rad={rad}" if rad != 0 else "arc3,rad=0"
        ax.annotate(
            "",
            xy=(x2, y2), xycoords='data',
            xytext=(x1, y1), textcoords='data',
            arrowprops=dict(
                arrowstyle="-|>",
                color=LINE_ARROW,
                lw=lw,
                mutation_scale=13,
                connectionstyle=cstyle
            ),
            zorder=5
        )
        if label:
            mx = x1 + (x2 - x1) * label_pos
            my = y1 + (y2 - y1) * label_pos
            ax.text(mx, my, label, ha='center', va='center', fontsize=7.5, fontweight='bold', color=TEXT_BLACK,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=COLOR_BORDER_SUB, lw=0.8), zorder=6)

    # ── HEADER ─────────────────────────────────────────────────────────────
    ax.text(50, 97.6, "YARDS & PARTS AUTOMOTIVE — SYSTEM ARCHITECTURE", ha='center', va='top',
            fontsize=16, fontweight='bold', color=TEXT_BLACK)
    ax.text(50, 95.3, "Autonomous B2B Salvage Yard Quoting, Hollander Interchange & Omnichannel Sales Cadence Platform",
            ha='center', va='top', fontsize=9.5, color=TEXT_MUTED)
    ax.plot([4, 96], [93.8, 93.8], color='#E2E8F0', lw=1.2, zorder=1)

    # ── LAYER 1: INBOUND CHANNELS ──────────────────────────────────────────
    ax.text(4, 92.4, "LAYER 1: CUSTOMER CHANNELS & INBOUND TOUCHPOINTS", fontsize=8.0, fontweight='bold', color=COLOR_BORDER_SUB)

    ch_w, ch_h, ch_y = 21.0, 6.2, 85.0
    draw_card(4.0,  ch_y, ch_w, ch_h, "Web Chat & Store", "Online Widget", ["Self-serve guided quoting", "Instant VIN entry prompt"])
    draw_card(28.0, ch_y, ch_w, ch_h, "Voice Telephony", "Twilio SIP / Voice", ["Inbound phone quote requests", "Interactive voice response"])
    draw_card(52.0, ch_y, ch_w, ch_h, "SMS / Mobile Messaging", "Twilio Messaging", ["Direct SMS quote inquiries", "Photo & spec sharing"])
    draw_card(75.0, ch_y, ch_w, ch_h, "Email Dispatch", "Gmail SMTP Relay", ["Part availability inquiries", "Repair shop quote requests"])

    # ── LAYER 2: USER APPLICATION COCKPITS ─────────────────────────────────
    ax.text(4, 82.5, "LAYER 2: USER APPLICATIONS & WORKFLOW COCKPITS", fontsize=8.0, fontweight='bold', color=COLOR_BORDER_SUB)

    app_w, app_h, app_y = 29.0, 10.5, 70.0
    draw_card(4.0,  app_y, app_w, app_h, "VIN Quoting Engine (/quoting)", "Interactive 5-Step Quoting Wizard", [
        "17-character VIN auto-decode (NHTSA)",
        "Hollander compatibility match (95% vs 55%)",
        "Margin safeguards (≥20% gross margin lock)",
        "Instant ReportLab B2B formal PDF quotes"
    ], bg=BG_LIGHT)

    draw_card(35.5, app_y, app_w, app_h, "Sales Rep Cockpit (/dashboard/rep)", "Unified Rep Command Center", [
        "Quote Simulator & Timeline side-by-side",
        "13 Contextual Battlecards search popover",
        "Active Cadence Leads full-width table",
        "1-Click 'Connect' menu (Call, Email, SMS)"
    ], bg=BG_LIGHT)

    draw_card(67.0, app_y, app_w, app_h, "Cart Auto-Mailer (/dashboard/auto-mailer)", "Autonomous 7-Day Nurture Drip", [
        "Day 0: Formal PDF quote summary email",
        "Day 3: Fitment & warranty reassurance",
        "Day 4: Authorized 4% discount (code: YARDS4)",
        "Day 6: Final notice before floor release"
    ], bg=BG_LIGHT)

    # Arrows L1 -> L2
    draw_arrow(14.5, ch_y, 18.5, app_y + app_h)
    draw_arrow(38.5, ch_y, 47.0, app_y + app_h)
    draw_arrow(62.5, ch_y, 53.0, app_y + app_h)
    draw_arrow(85.5, ch_y, 81.5, app_y + app_h)

    # ── LAYER 3: AGENT CORE CONTAINER ──────────────────────────────────────
    ax.text(4, 67.5, "LAYER 3: AUTONOMOUS AGENT CORE & SALES CADENCE CONTROLLER", fontsize=8.0, fontweight='bold', color=COLOR_BORDER_SUB)

    core_w, core_h, core_y = 92.0, 17.5, 47.5
    core_box = patches.FancyBboxPatch(
        (4.0, core_y), core_w, core_h,
        boxstyle="round,pad=0,rounding_size=2.0",
        facecolor=BG_CORE,
        edgecolor=COLOR_BORDER_BOLD,
        linewidth=2.0,
        zorder=2
    )
    ax.add_patch(core_box)
    ax.text(50, core_y + core_h - 1.3, "AI SALES AGENT CORE & CADENCE CONTROLLER", ha='center', va='top', fontsize=11.5, fontweight='bold', color=TEXT_BLACK, zorder=3)
    ax.text(50, core_y + core_h - 2.8, "State Machine, Tool Calling, Multi-Turn Dialogue & Commercial Safeguards", ha='center', va='top', fontsize=8.2, fontstyle='italic', color=TEXT_MUTED, zorder=3)

    # 4 Inner Pillars inside Layer 3
    pil_w, pil_h, pil_y = 20.8, 12.0, 49.0
    draw_card(6.2,  pil_y, pil_w, pil_h, "7-Phase Sales Flow", "Guided Dialogue Machine", [
        "1. Greet & Qualify",
        "2. Vehicle VIN Decode",
        "3. Fitment Matching",
        "4. Persona-Aware Pitch",
        "5. Objection Handling",
        "6. Close / Callback"
    ], bg=BG_WHITE, border=COLOR_BORDER_SUB, lw=1.1, r=1.0, title_size=9.2, sub_size=7.5)

    draw_card(28.8, pil_y, pil_w, pil_h, "13 Sales Battlecards", "Objection Scripts", [
        "Mileage check (<80k mi)",
        "Compression test (180 PSI)",
        "Warranty terms (90-day)",
        "Freight & dispatch (24h)",
        "Fitment guarantees",
        "Trade price negotiation"
    ], bg=BG_WHITE, border=COLOR_BORDER_SUB, lw=1.1, r=1.0, title_size=9.2, sub_size=7.5)

    draw_card(51.4, pil_y, pil_w, pil_h, "Commercial Rules", "Financial Safeguards", [
        "Minimum 20% margin lock",
        "Dynamic markup calculation",
        "Refundable core deposits",
        "Mileage-grade adjustments",
        "Freight zone estimator",
        "4% pre-authorized discount"
    ], bg=BG_WHITE, border=COLOR_BORDER_SUB, lw=1.1, r=1.0, title_size=9.2, sub_size=7.5)

    draw_card(73.8, pil_y, pil_w, pil_h, "Bilingual Processor", "Native EN & ES Engines", [
        "Automatic language detect",
        "English (en-US) dialogue",
        "Spanish (es-US) dialogue",
        "Bilingual quote recap SMS",
        "Speech synthesis & voice",
        "Consistent tone & terms"
    ], bg=BG_WHITE, border=COLOR_BORDER_SUB, lw=1.1, r=1.0, title_size=9.2, sub_size=7.5)

    # Arrows L2 -> L3
    draw_arrow(18.5, app_y, 22.0, core_y + core_h)
    draw_arrow(50.0, app_y, 50.0, core_y + core_h)
    draw_arrow(81.5, app_y, 78.0, core_y + core_h)

    # ── LAYER 4: VEHICLE DATA, HOLLANDER & LOGISTICS ───────────────────────
    ax.text(4, 45.0, "LAYER 4: VEHICLE SPECIFICATION, PARTS CATALOG & LOGISTICS ENGINES", fontsize=8.0, fontweight='bold', color=COLOR_BORDER_SUB)

    eng_w, eng_h, eng_y = 29.0, 10.5, 32.5
    draw_card(4.0,  eng_y, eng_w, eng_h, "NHTSA vPIC Vehicle API", "Federal Vehicle Database ($0 / Free)", [
        "17-character VIN decoded via REST API",
        "Extracts Year, Make, Model, and Trim",
        "Displacement (L), Cylinders, Fuel Type",
        "Transmission codes and drive type (FWD/AWD)"
    ], bg=BG_LIGHT)

    draw_card(35.5, eng_y, eng_w, eng_h, "Hollander Interchange & Inventory", "Master Salvage Catalog (cadence.db)", [
        "659 OEM parts across 9 vehicle lines",
        "Hollander cross-reference fitment matrix",
        "Compatibility confidence scoring",
        "Grade A stock & bench compression stats"
    ], bg=BG_LIGHT)

    draw_card(67.0, eng_y, eng_w, eng_h, "Omnichannel Comms Relay", "Twilio & Gmail SMTP Dispatchers", [
        "Twilio Voice (7-Node IVR state machine)",
        "Twilio SMS (Concatenated quote recap text)",
        "Gmail SMTP (ReportLab PDF attachment delivery)",
        "Public HTTPS tunnel (Cloudflare Webhooks)"
    ], bg=BG_LIGHT)

    # Arrows L3 -> L4
    draw_arrow(22.0, core_y, 18.5, eng_y + eng_h)
    draw_arrow(50.0, core_y, 50.0, eng_y + eng_h)
    draw_arrow(78.0, core_y, 81.5, eng_y + eng_h)

    # ── LAYER 5: COMMERCE & CRM INTEGRATION ────────────────────────────────
    ax.text(4, 30.0, "LAYER 5: COMMERCE CONNECTOR & CRM SYNCHRONIZATION", fontsize=8.0, fontweight='bold', color=COLOR_BORDER_SUB)

    com_w, com_h, com_y = 43.5, 9.5, 18.5
    draw_card(4.0,  com_y, com_w, com_h, "CommerceConnector Interface", "Shopify Storefront MCP & Extensible Stores", [
        "Abstract interface for multi-platform inventory & cart creation",
        "Shopify Storefront MCP integration (Catalog Search, Policy FAQ)",
        "Admin GraphQL API draft orders and customer checkout links"
    ], bg=BG_WHITE)

    draw_card(52.5, com_y, com_w, com_h, "CRM & Intelligence Feed", "Zoho CRM & Real-Time Event Webhook", [
        "Direct REST deal sync: In Cadence, Quote Delivered, Closed Won",
        "HMAC-SHA256 signed event stream (`crm.sync`, `quote_generated`)",
        "Full audit payload with gross margin, cost, shipping, and rep notes"
    ], bg=BG_WHITE)

    # Arrows L4 -> L5
    draw_arrow(18.5, eng_y, 22.0, com_y + com_h)
    draw_arrow(50.0, eng_y, 30.0, com_y + com_h)
    draw_arrow(50.0, eng_y, 68.0, com_y + com_h)
    draw_arrow(81.5, eng_y, 78.0, com_y + com_h)

    # Horizontal connection between Commerce and CRM
    draw_arrow(47.5, com_y + com_h / 2, 52.5, com_y + com_h / 2, label="deal.sync", label_pos=0.5, lw=1.3)

    # ── FOOTER / LEGEND ───────────────────────────────────────────────────
    ax.plot([4, 96], [16.5, 16.5], color='#E2E8F0', lw=1.0, zorder=1)
    ax.text(50, 14.5, "Yards & Parts Automotive  •  B2B Salvage Yard Platform  •  Enterprise Architecture v1.0",
            ha='center', va='top', fontsize=8.5, color=TEXT_MUTED)

    # Save to all required paths
    out_dir_artifact = r"C:\Users\Admin\.gemini\antigravity\brain\92229623-5397-48b9-989f-9a9cb99cc2ae"
    out_dir_project = r"C:\Users\Admin\.gemini\antigravity\scratch\sales-cadence"
    out_dir_static = os.path.join(out_dir_project, "app", "static")

    path_art_png = os.path.join(out_dir_artifact, "architecture_diagram.png")
    path_proj_png = os.path.join(out_dir_project, "architecture_diagram.png")
    path_static_png = os.path.join(out_dir_static, "architecture_diagram.png")
    path_svg = os.path.join(out_dir_artifact, "architecture_diagram.svg")

    plt.tight_layout(pad=1.0)
    plt.savefig(path_art_png, dpi=300, facecolor='#FFFFFF', edgecolor='none')
    plt.savefig(path_proj_png, dpi=300, facecolor='#FFFFFF', edgecolor='none')
    plt.savefig(path_static_png, dpi=300, facecolor='#FFFFFF', edgecolor='none')
    plt.savefig(path_svg, facecolor='#FFFFFF', edgecolor='none')
    plt.close()

    print("Architecture diagram generated successfully with zero collisions!")

if __name__ == "__main__":
    draw_diagram()
