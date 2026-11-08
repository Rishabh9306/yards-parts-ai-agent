import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def draw_simple_diagram():
    # 16:10 wide canvas, 300 DPI for high-resolution clarity
    fig, ax = plt.subplots(figsize=(16, 11), dpi=300)
    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Minimalist Black & White palette
    COLOR_BLACK = '#09090B'
    COLOR_CARD = '#FFFFFF'
    COLOR_CONTAINER = '#F8FAFC'
    COLOR_MUTED = '#52525B'
    COLOR_LINE = '#09090B'

    def draw_box(x, y, w, h, text, bg=COLOR_CARD, border=COLOR_BLACK, lw=2.0, r=1.4, fontsize=12):
        box = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            facecolor=bg,
            edgecolor=border,
            linewidth=lw,
            zorder=3
        )
        ax.add_patch(box)
        # Headline only - clean, bold, centered
        ax.text(x + w / 2, y + h / 2, text, ha='center', va='center',
                fontsize=fontsize, fontweight='bold', color=COLOR_BLACK, zorder=4)
        return (x + w / 2, y + h / 2)

    def draw_arrow(x1, y1, x2, y2, lw=1.8, rad=0):
        cstyle = f"arc3,rad={rad}" if rad != 0 else "arc3,rad=0"
        ax.annotate(
            "",
            xy=(x2, y2), xycoords='data',
            xytext=(x1, y1), textcoords='data',
            arrowprops=dict(
                arrowstyle="-|>",
                color=COLOR_LINE,
                lw=lw,
                mutation_scale=14,
                connectionstyle=cstyle
            ),
            zorder=5
        )

    # ── HEADER ─────────────────────────────────────────────────────────────
    ax.text(50, 96.8, "YARDS & PARTS AUTOMOTIVE — SYSTEM ARCHITECTURE", ha='center', va='top',
            fontsize=17, fontweight='bold', color=COLOR_BLACK)
    ax.text(50, 94.0, "High-Level Architecture & End-to-End System Flow", ha='center', va='top',
            fontsize=10.5, color=COLOR_MUTED)
    ax.plot([4, 96], [92.0, 92.0], color=COLOR_BLACK, lw=1.4, zorder=1)

    # ── LEFT COLUMN LAYER BADGES (x = 4 to 20) ──────────────────────────────
    # Placing all labels strictly in the left column guarantees NO arrows ever intersect labels!
    def draw_layer_badge(y_center, step_num, title, subtitle=""):
        bw, bh = 15.5, 6.0
        bx, by = 4.0, y_center - bh / 2
        # Card outline for layer label
        card = patches.FancyBboxPatch(
            (bx, by), bw, bh,
            boxstyle="round,pad=0,rounding_size=1.0",
            facecolor=COLOR_CONTAINER,
            edgecolor=COLOR_BLACK,
            linewidth=1.2,
            zorder=2
        )
        ax.add_patch(card)
        ax.text(bx + bw / 2, by + bh - 1.4, f"LAYER {step_num}", ha='center', va='top',
                fontsize=8.5, fontweight='bold', color=COLOR_MUTED, zorder=3)
        ax.text(bx + bw / 2, by + bh - 2.8, title, ha='center', va='top',
                fontsize=10.5, fontweight='bold', color=COLOR_BLACK, zorder=3)
        if subtitle:
            ax.text(bx + bw / 2, by + 1.2, subtitle, ha='center', va='bottom',
                    fontsize=8.0, fontstyle='italic', color=COLOR_MUTED, zorder=3)

    # ── RIGHT AREA: HEADLINE BOXES (x = 22 to 96) ───────────────────────────

    # LAYER 1: CHANNELS (y center = 84.5)
    draw_layer_badge(84.5, "1", "CHANNELS", "Inbound Leads")
    l1_y, l1_h, l1_w = 81.5, 6.0, 17.5
    draw_box(22.0, l1_y, l1_w, l1_h, "Web Chat & Store", fontsize=11.5)
    draw_box(41.0, l1_y, l1_w, l1_h, "Voice Telephony", fontsize=11.5)
    draw_box(60.0, l1_y, l1_w, l1_h, "SMS Messaging", fontsize=11.5)
    draw_box(78.5, l1_y, l1_w, l1_h, "Email Inquiries", fontsize=11.5)

    # Arrows L1 -> L2
    draw_arrow(30.75, l1_y, 33.5, 73.0)   # Web Chat -> Quoting
    draw_arrow(49.75, l1_y, 59.0, 73.0)   # Voice -> Rep Cockpit
    draw_arrow(68.75, l1_y, 59.0, 73.0)   # SMS -> Rep Cockpit
    draw_arrow(87.25, l1_y, 84.5, 73.0)   # Email -> Auto-Mailer

    # LAYER 2: APPLICATIONS (y center = 69.5)
    draw_layer_badge(69.5, "2", "APPLICATIONS", "Workflow Cockpits")
    l2_y, l2_h, l2_w = 66.5, 6.2, 23.5
    draw_box(22.0, l2_y, l2_w, l2_h, "VIN Quoting Engine\n(/quoting)", fontsize=12)
    draw_box(47.25, l2_y, l2_w, l2_h, "Sales Rep Cockpit\n(/dashboard/rep)", fontsize=12)
    draw_box(72.5, l2_y, l2_w, l2_h, "Cart Auto-Mailer\n(/dashboard/auto-mailer)", fontsize=12)

    # Arrows L2 -> L3
    draw_arrow(33.75, l2_y, 30.75, 58.0)  # Quoting -> Dialogue
    draw_arrow(59.0,  l2_y, 49.75, 58.0)  # Cockpit -> Battlecards
    draw_arrow(59.0,  l2_y, 68.75, 58.0)  # Cockpit -> Margin Rules
    draw_arrow(84.25, l2_y, 87.25, 58.0)  # Auto-Mailer -> Bilingual

    # LAYER 3: AI SALES CORE (y center = 54.5)
    draw_layer_badge(54.5, "3", "AI AGENT CORE", "Decision & Dialogue")
    l3_y, l3_h, l3_w = 51.5, 6.2, 17.5
    draw_box(22.0, l3_y, l3_w, l3_h, "7-Phase Dialogue\nSales Machine", fontsize=11.5)
    draw_box(41.0, l3_y, l3_w, l3_h, "13 Objection\nBattlecards", fontsize=11.5)
    draw_box(60.0, l3_y, l3_w, l3_h, "Commercial Rules\n(≥20% Margin Lock)", fontsize=11.5)
    draw_box(78.5, l3_y, l3_w, l3_h, "Bilingual Engine\n(English & Spanish)", fontsize=11.5)

    # Arrows L3 -> L4
    draw_arrow(30.75, l3_y, 33.75, 43.0)  # Dialogue -> NHTSA
    draw_arrow(49.75, l3_y, 59.0, 43.0)   # Battlecards -> Hollander
    draw_arrow(68.75, l3_y, 59.0, 43.0)   # Rules -> Hollander
    draw_arrow(87.25, l3_y, 84.25, 43.0)  # Bilingual -> Comms Relay

    # LAYER 4: DATA & LOGISTICS (y center = 39.5)
    draw_layer_badge(39.5, "4", "DATA & CATALOG", "Fitment & Comms")
    l4_y, l4_h, l4_w = 36.5, 6.2, 23.5
    draw_box(22.0, l4_y, l4_w, l4_h, "NHTSA VIN Decoder\n(vPIC Government API)", fontsize=12)
    draw_box(47.25, l4_y, l4_w, l4_h, "Hollander Interchange\n(Master Parts Catalog)", fontsize=12)
    draw_box(72.5, l4_y, l4_w, l4_h, "Omnichannel Comms Relay\n(Twilio Voice, SMS & SMTP)", fontsize=12)

    # Arrows L4 -> L5
    draw_arrow(33.75, l4_y, 40.0, 28.5)   # VIN Decoder -> Shopify
    draw_arrow(59.0,  l4_y, 40.0, 28.5)   # Hollander -> Shopify
    draw_arrow(59.0,  l4_y, 78.0, 28.5)   # Hollander -> Zoho CRM
    draw_arrow(84.25, l4_y, 78.0, 28.5)   # Comms -> Zoho CRM

    # LAYER 5: COMMERCE & CRM (y center = 24.5)
    draw_layer_badge(24.5, "5", "INTEGRATIONS", "Commerce & CRM")
    l5_y, l5_h, l5_w = 21.0, 7.0, 35.8
    draw_box(22.0, l5_y, l5_w, l5_h, "CommerceConnector Interface\n(Shopify Storefront MCP & Catalog)", fontsize=12.5)
    draw_box(60.2, l5_y, l5_w, l5_h, "Zoho CRM Synchronization\n(Real-Time Deal Updates & Webhooks)", fontsize=12.5)

    # Bidirectional sync between Commerce & CRM
    draw_arrow(57.8, l5_y + l5_h / 2 + 0.8, 60.2, l5_y + l5_h / 2 + 0.8, lw=1.8)
    draw_arrow(60.2, l5_y + l5_h / 2 - 0.8, 57.8, l5_y + l5_h / 2 - 0.8, lw=1.8)

    # ── FOOTER ─────────────────────────────────────────────────────────────
    ax.plot([4, 96], [16.5, 16.5], color=COLOR_BLACK, lw=1.4, zorder=1)
    ax.text(50, 13.5, "Yards & Parts Automotive  •  Autonomous B2B Salvage Yard Quoting Platform  •  System Architecture",
            ha='center', va='top', fontsize=9.5, color=COLOR_MUTED)

    # Output paths
    out_dir_artifact = r"C:\Users\Admin\.gemini\antigravity\brain\92229623-5397-48b9-989f-9a9cb99cc2ae"
    out_dir_project = r"C:\Users\Admin\.gemini\antigravity\scratch\sales-cadence"
    out_dir_static = os.path.join(out_dir_project, "app", "static")

    p1 = os.path.join(out_dir_artifact, "architecture_diagram.png")
    p2 = os.path.join(out_dir_project, "architecture_diagram.png")
    p3 = os.path.join(out_dir_static, "architecture_diagram.png")
    p_svg = os.path.join(out_dir_artifact, "architecture_diagram.svg")

    plt.tight_layout(pad=1.5)
    plt.savefig(p1, dpi=300, facecolor='#FFFFFF', edgecolor='none')
    plt.savefig(p2, dpi=300, facecolor='#FFFFFF', edgecolor='none')
    plt.savefig(p3, dpi=300, facecolor='#FFFFFF', edgecolor='none')
    plt.savefig(p_svg, facecolor='#FFFFFF', edgecolor='none')
    plt.close()

    print("Simple architecture diagram successfully generated!")

if __name__ == "__main__":
    draw_simple_diagram()
