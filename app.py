import io
import streamlit as st
import rectpack
from rectpack import PackingMode, PackingBin, newPacker, GuillotineBssfSas, GuillotineSplitSlas
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image

# ---------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA WEB
# ---------------------------------------------------------
st.set_page_config(page_title="Optimizador de Corte de Vidrio", layout="wide")
st.title("🪟 Optimizador de Corte de Vidrio profesional")

# ---------------------------------------------------------
# BARRA LATERAL: INGRESO DE DATOS DE LA PLANCHA MADRE
# ---------------------------------------------------------
st.sidebar.header("1. Plancha Madre (Vidrio Base)")
plancha_w = st.sidebar.number_input("Ancho de la plancha (mm)", value=3300, step=100)
plancha_h = st.sidebar.number_input("Alto de la plancha (mm)", value=2440, step=100)
cantidad_planchas = st.sidebar.number_input("Cantidad de planchas disponibles", value=5, min_value=1)
permitir_rotacion = st.sidebar.checkbox("Permitir rotar piezas (90°)", value=True)

# ---------------------------------------------------------
# ÁREA PRINCIPAL: LISTA DE VIDRIOS A OPTIMIZAR
# ---------------------------------------------------------
st.subheader("2. Lista de vidrios a optimizar")

if "pedidos" not in st.session_state:
    st.session_state.pedidos = [
        {"etiqueta": "V1", "ancho": 1190, "alto": 665, "cantidad": 1},
        {"etiqueta": "V1", "ancho": 1160, "alto": 650, "cantidad": 2},
        {"etiqueta": "V1", "ancho": 2300, "alto": 350, "cantidad": 1},
        {"etiqueta": "V1", "ancho": 665, "alto": 1190, "cantidad": 1},
    ]

# Tabla interactiva para modificar/agregar piezas
edited_data = st.data_editor(
    st.session_state.pedidos,
    num_rows="dynamic",
    column_config={
        "etiqueta": st.column_config.TextColumn("Identificador / Cliente", required=True),
        "ancho": st.column_config.NumberColumn("Ancho (mm)", min_value=10, required=True),
        "alto": st.column_config.NumberColumn("Alto (mm)", min_value=10, required=True),
        "cantidad": st.column_config.NumberColumn("Cantidad", min_value=1, step=1, required=True),
    },
    use_container_width=True
)

# ---------------------------------------------------------
# FUNCIONES DE OPTIMIZACIÓN Y GRÁFICOS
# ---------------------------------------------------------
def optimizar_cortes(plancha_w, plancha_h, max_bins, rotacion, pedidos):
    # Usamos el modo Guillotina (Corte de vidrio real de lado a lado)
    packer = newPacker(
        mode=PackingMode.Selecting,
        pack_algo=GuillotineBssfSas,
        split_algo=GuillotineSplitSlas,
        rotation=rotacion
    )
    packer.add_bin(plancha_w, plancha_h, count=max_bins)

    for item in pedidos:
        if not item or not isinstance(item, dict):
            continue
        tag = item.get("etiqueta", "Pieza")
        w = int(item.get("ancho") or 0)
        h = int(item.get("alto") or 0)
        cant = int(item.get("cantidad") or 1)
        if w > 0 and h > 0:
            for _ in range(cant):
                rid_info = f"{tag}|{w}|{h}"
                packer.add_rect(w, h, rid=rid_info)

    packer.pack()
    return packer

def generar_imagen_plano(abin, plancha_w, plancha_h, num_plancha):
    fig, ax = plt.subplots(figsize=(11, 7))

    # Ocultar ejes X / Y tradicionales
    ax.axis('off')

    # Plancha Madre Base
    rect_madre = patches.Rectangle((0, 0), plancha_w, plancha_h, linewidth=2, edgecolor='black', facecolor='#F5F6F8')
    ax.add_patch(rect_madre)

    colores = ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F', '#EDC948', '#B07AA1']
    area_usada = 0
    tag_color_map = {}
    color_idx = 0

    cortes_x = set([0, plancha_w])
    cortes_y = set([0, plancha_h])

    for rect in abin:
        x, y, w, h = rect.x, rect.y, rect.width, rect.height
        
        cortes_x.add(x)
        cortes_x.add(x + w)
        cortes_y.add(y)
        cortes_y.add(y + h)

        rid_str = str(rect.rid)
        if "|" in rid_str:
            parts = rid_str.split("|")
            rid = parts[0]
            w_orig, h_orig = int(parts[1]), int(parts[2])
        else:
            rid = rid_str
            w_orig, h_orig = w, h

        area_usada += (w * h)

        if rid not in tag_color_map:
            tag_color_map[rid] = colores[color_idx % len(colores)]
            color_idx += 1

        # Pieza trazada
        rect_pieza = patches.Rectangle((x, y), w, h, linewidth=1.2, edgecolor='#1E1E1E', facecolor=tag_color_map[rid], alpha=0.85)
        ax.add_patch(rect_pieza)

        # Etiqueta de la pieza
        if (w == w_orig and h == h_orig):
            texto_medidas = f"Corte: {w} x {h} mm"
        else:
            texto_medidas = f"Corte: {w} x {h} mm\n(Rotado, Orig: {w_orig}x{h_orig})"

        ax.text(
            x + w/2, y + h/2, f"{rid}\n{texto_medidas}",
            color='white', weight='bold', fontsize=8, ha='center', va='center',
            bbox=dict(boxstyle="round,pad=0.2", fc="black", ec="none", alpha=0.6)
        )

    # ---------------------------------------------------------
    # PROYECCIÓN DE LÍNEAS ROJAS DE CORTE CONTINUO (GUILLOTINA)
    # ---------------------------------------------------------
    for cx in sorted(cortes_x):
        if 0 < cx < plancha_w:
            ax.plot([cx, cx], [0, plancha_h], color='red', linestyle='--', linewidth=1, alpha=0.75)

    for cy in sorted(cortes_y):
        if 0 < cy < plancha_h:
            ax.plot([0, plancha_w], [cy, cy], color='red', linestyle='--', linewidth=1, alpha=0.75)

    # ---------------------------------------------------------
    # ACOTADO TÉCNICO (MEDIDAS GENERALES DE LA PLANCHA)
    # ---------------------------------------------------------
    margin_x = plancha_w * 0.08
    margin_y = plancha_h * 0.08

    # Cota Ancho Plancha (Abajo)
    ax.annotate(
        '', xy=(0, -margin_y*0.4), xytext=(plancha_w, -margin_y*0.4),
        arrowprops=dict(arrowstyle='<->', color='black', lw=1.5)
    )
    ax.text(plancha_w/2, -margin_y*0.7, f"Ancho Plancha: {plancha_w} mm", ha='center', va='top', fontsize=10, fontweight='bold')

    # Cota Alto Plancha (Izquierda)
    ax.annotate(
        '', xy=(-margin_x*0.4, 0), xytext=(-margin_x*0.4, plancha_h),
        arrowprops=dict(arrowstyle='<->', color='black', lw=1.5)
    )
    ax.text(-margin_x*0.7, plancha_h/2, f"Alto Plancha: {plancha_h} mm", ha='right', va='center', rotation=90, fontsize=10, fontweight='bold')

    aprovechamiento = (area_usada / (plancha_w * plancha_h)) * 100
    merma = 100 - aprovechamiento

    ax.set_xlim(-margin_x*1.5, plancha_w + margin_x*0.5)
    ax.set_ylim(-margin_y*1.5, plancha_h + margin_y*0.5)
    ax.set_aspect('equal')
    plt.title(f"Plancha #{num_plancha} — Aprovechamiento: {aprovechamiento:.2f}% | Merma: {merma:.2f}%", fontweight='bold', pad=15)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf, aprovechamiento, merma

# ---------------------------------------------------------
# FUNCIÓN DE GENERACIÓN DE PDF
# ---------------------------------------------------------
def generar_pdf_reporte(packer, plancha_w, plancha_h):
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1A365D'), spaceAfter=10)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.gray, spaceAfter=15)

    elements.append(Paragraph("Hoja de Optimización y Esquema de Corte de Vidrio", title_style))
    elements.append(Paragraph(f"Dimensiones Plancha Madre: {plancha_w} x {plancha_h} mm", subtitle_style))

    for i, abin in enumerate(packer):
        if len(abin) == 0:
            continue
        
        img_buf, aprovechamiento, merma = generar_imagen_plano(abin, plancha_w, plancha_h, i + 1)
        
        elements.append(Paragraph(f"<b>Plancha #{i + 1}</b> — Aprovechamiento: <b>{aprovechamiento:.2f}%</b> (Merma: {merma:.2f}%)", styles['Heading2']))
        elements.append(Spacer(1, 5))
        
        elements.append(Image(img_buf, width=700, height=350))
        elements.append(Spacer(1, 15))

    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer

# ---------------------------------------------------------
# BOTÓN Y EJECUCIÓN
# ---------------------------------------------------------
if st.button("🚀 Optimizar Cortes y Generar Informe", type="primary"):
    with st.spinner("Calculando plano óptimo de corte guillotina..."):
        packer = optimizar_cortes(plancha_w, plancha_h, cantidad_planchas, permitir_rotacion, edited_data)
        
        planchas_usadas = [b for b in packer if len(b) > 0]
        
        if len(planchas_usadas) == 0:
            st.error("No se pudieron empaquetar las piezas. Verifique que el tamaño de las piezas sea menor al de la plancha madre.")
        else:
            st.success(f"¡Optimización completada! Se requieren **{len(planchas_usadas)}** plancha(s) madre.")

            for i, abin in enumerate(planchas_usadas):
                img_buf, aprovechamiento, merma = generar_imagen_plano(abin, plancha_w, plancha_h, i + 1)
                st.image(img_buf, caption=f"Esquema de Corte - Plancha {i+1}", use_container_width=True)

            pdf_data = generar_pdf_reporte(packer, plancha_w, plancha_h)
            st.download_button(
                label="📄 Descargar Planos de Corte en PDF",
                data=pdf_data,
                file_name="Planos_de_Corte_Vidrio.pdf",
                mime="application/pdf"
            )
