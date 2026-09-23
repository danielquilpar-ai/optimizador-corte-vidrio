import io
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Librerías para reporte PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ---------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA WEB
# ---------------------------------------------------------
st.set_page_config(page_title="Optimizador de Corte de Vidrio", layout="wide")
st.title("🪟 Optimizador de Corte de Vidrio Profesional")

# ---------------------------------------------------------
# BARRA LATERAL: PLANCHA MADRE Y RETAZOS DE ALMACÉN
# ---------------------------------------------------------
st.sidebar.header("1. Plancha Madre (Vidrio Base)")
plancha_w = st.sidebar.number_input("Ancho de la plancha madre (mm)", value=3300, step=100)
plancha_h = st.sidebar.number_input("Alto de la plancha madre (mm)", value=2140, step=100)
cantidad_planchas = st.sidebar.number_input("Cantidad de planchas madre disponibles", value=5, min_value=1)
permitir_rotacion = st.sidebar.checkbox("Permitir rotar piezas (90°)", value=True)

st.sidebar.markdown("---")
st.sidebar.header("2. Retazos de Almacén (Opcional)")
st.sidebar.write("Agrega sobrantes para usarlos antes que las planchas madre:")

if "retazos" not in st.session_state:
    st.session_state.retazos = [
        {"etiqueta": "R1", "ancho": 1500, "alto": 1000, "cantidad": 1},
        {"etiqueta": "R2", "ancho": 1650, "alto": 2100, "cantidad": 1}
    ]

retazos_editados = st.sidebar.data_editor(
    st.session_state.retazos,
    num_rows="dynamic",
    column_config={
        "etiqueta": st.column_config.TextColumn("Identificador", default="R1", required=True),
        "ancho": st.column_config.NumberColumn("Ancho (mm)", min_value=10, default=1000, required=True),
        "alto": st.column_config.NumberColumn("Alto (mm)", min_value=10, default=1000, required=True),
        "cantidad": st.column_config.NumberColumn("Cant.", min_value=1, default=1, step=1, required=True),
    },
    use_container_width=True,
    key="editor_retazos"
)

# ---------------------------------------------------------
# ÁREA PRINCIPAL: LISTA DE VIDRIOS A OPTIMIZAR
# ---------------------------------------------------------
st.subheader("3. Lista de vidrios a optimizar")

if "pedidos" not in st.session_state:
    st.session_state.pedidos = [
        {"etiqueta": "m3", "ancho": 750, "alto": 2189, "cantidad": 2},
    ]

edited_data = st.data_editor(
    st.session_state.pedidos,
    num_rows="dynamic",
    column_config={
        "etiqueta": st.column_config.TextColumn("Identificador / Cliente", required=True),
        "ancho": st.column_config.NumberColumn("Ancho (mm)", min_value=10, required=True),
        "alto": st.column_config.NumberColumn("Alto (mm)", min_value=10, required=True),
        "cantidad": st.column_config.NumberColumn("Cantidad", min_value=1, step=1, required=True),
    },
    use_container_width=True,
    key="editor_pedidos"
)

# ---------------------------------------------------------
# CLASE Y ESTRUCTURA DE DATOS
# ---------------------------------------------------------
class Rectangulo:
    def __init__(self, x, y, w, h, tag, orig_w, orig_h, rotado):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.tag = tag
        self.orig_w = orig_w
        self.orig_h = orig_h
        self.rotado = rotado

def empaquetar_en_plancha(bin_w, bin_h, piezas, permitir_rot):
    piezas_colocadas = []
    piezas_no_colocadas = []
    cortes_guillotina = []

    max_x_bloque = 0
    piezas_temp = []
    espacios_libres = [(0, 0, bin_w, bin_h)]

    for p in piezas:
        pw, ph = p["w"], p["h"]
        tag = p["tag"]
        colocada = False

        orientaciones = [(pw, ph, False)]
        if permitir_rot and pw != ph:
            orientaciones.append((ph, pw, True))

        for idx_e, (ex, ey, ew, eh) in enumerate(espacios_libres):
            for w_eval, h_eval, es_rot in orientaciones:
                if w_eval <= ew and h_eval <= eh:
                    rect = Rectangulo(ex, ey, w_eval, h_eval, tag, pw, ph, es_rot)
                    piezas_temp.append(rect)
                    espacios_libres.pop(idx_e)

                    if ex + w_eval > max_x_bloque:
                        max_x_bloque = ex + w_eval

                    if ew - w_eval > 0:
                        espacios_libres.append((ex + w_eval, ey, ew - w_eval, h_eval))
                    if eh - h_eval > 0:
                        espacios_libres.append((ex, ey + h_eval, ew, eh - h_eval))

                    espacios_libres.sort(key=lambda s: (s[0], s[1]))
                    colocada = True
                    break
            if colocada:
                break

        if not colocada:
            piezas_no_colocadas.append(p)

    if not piezas_temp:
        return [], piezas, []

    piezas_colocadas = piezas_temp

    # CORTE V1 MAESTRO: Aísla el Retazo R1
    if max_x_bloque < bin_w:
        cortes_guillotina.append({
            "tipo": "V",
            "x": max_x_bloque,
            "y1": 0,
            "y2": bin_h,
            "etiqueta_retazo": "R1"
        })

    # CORTES HORIZONTALES SECUNDARIOS
    y_cortes = set()
    for rect in piezas_colocadas:
        if rect.y + rect.h < bin_h:
            y_cortes.add(rect.y + rect.h)

    for y_c in sorted(y_cortes):
        cortes_guillotina.append({
            "tipo": "H",
            "y": y_c,
            "x1": 0,
            "x2": max_x_bloque,
            "etiqueta_retazo": "R2"
        })

    return piezas_colocadas, piezas_no_colocadas, cortes_guillotina

def optimizar_corte_completo(plancha_w, plancha_h, max_planchas, permitir_rot, pedidos, retazos):
    piezas_pendientes = []
    for item in pedidos:
        if not item or not isinstance(item, dict):
            continue
        tag = str(item.get("etiqueta") or "V")
        w = int(item.get("ancho") or 0)
        h = int(item.get("alto") or 0)
        cant = int(item.get("cantidad") or 1)
        if w > 0 and h > 0:
            for _ in range(cant):
                piezas_pendientes.append({"w": w, "h": h, "tag": tag, "area": w * h})

    piezas_pendientes.sort(key=lambda p: p["area"], reverse=True)
    planchas_usadas = []

    if retazos:
        for ret in retazos:
            if not ret or not isinstance(ret, dict) or len(piezas_pendientes) == 0:
                continue
            rw = int(ret.get("ancho") or 0)
            rh = int(ret.get("alto") or 0)
            rcant = int(ret.get("cantidad") or 1)
            rtag = str(ret.get("etiqueta") or "Retazo")

            if rw <= 0 or rh <= 0:
                continue

            for _ in range(rcant):
                if len(piezas_pendientes) == 0:
                    break
                colocadas, pendientes, cortes = empaquetar_en_plancha(rw, rh, piezas_pendientes, permitir_rot)
                if len(colocadas) > 0:
                    planchas_usadas.append({
                        "colocadas": colocadas,
                        "cortes": cortes,
                        "info": {"tipo": "Retazo", "nombre": rtag, "w": rw, "h": rh}
                    })
                    piezas_pendientes = pendientes

    for i in range(max_planchas):
        if len(piezas_pendientes) == 0:
            break
        colocadas, pendientes, cortes = empaquetar_en_plancha(plancha_w, plancha_h, piezas_pendientes, permitir_rot)
        if len(colocadas) > 0:
            planchas_usadas.append({
                "colocadas": colocadas,
                "cortes": cortes,
                "info": {"tipo": "Plancha Madre", "nombre": f"Plancha Madre #{i+1}", "w": plancha_w, "h": plancha_h}
            })
            piezas_pendientes = pendientes

    return planchas_usadas, piezas_pendientes

# ---------------------------------------------------------
# GENERACIÓN DE PLANO LIMPIO
# ---------------------------------------------------------
def generar_imagen_plano(plancha_data, index_num):
    colocadas = plancha_data["colocadas"]
    cortes = plancha_data["cortes"]
    info = plancha_data["info"]
    b_w, b_h = info["w"], info["h"]
    es_retazo = info["tipo"] == "Retazo"

    fig, ax = plt.subplots(figsize=(11, 7))
    ax.axis('off')

    color_fondo = '#FFF3E0' if es_retazo else '#F5F6F8'
    rect_madre = patches.Rectangle((0, 0), b_w, b_h, linewidth=2, edgecolor='black', facecolor=color_fondo)
    ax.add_patch(rect_madre)

    colores = ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F', '#EDC948', '#B07AA1']
    area_usada = 0
    tag_color_map = {}
    color_idx = 0

    for rect in colocadas:
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        area_usada += (w * h)

        if rect.tag not in tag_color_map:
            tag_color_map[rect.tag] = colores[color_idx % len(colores)]
            color_idx += 1

        rect_pieza = patches.Rectangle((x, y), w, h, linewidth=1, edgecolor='#333333', facecolor=tag_color_map[rect.tag], alpha=0.85)
        ax.add_patch(rect_pieza)

        # TEXTO LIMPIO SIN LÍNEA DE ROTACIÓN
        texto_medidas = f"Corte: {w} x {h} mm"

        ax.text(
            x + w/2, y + h/2, f"{rect.tag}\n{texto_medidas}",
            color='white', weight='bold', fontsize=8, ha='center', va='center',
            bbox=dict(boxstyle="round,pad=0.2", fc="black", ec="none", alpha=0.65)
        )

    # CORTES Y NUMERACIÓN EN AZUL
    for num, c in enumerate(cortes, start=1):
        if c["tipo"] == "V":
            x = c["x"]
            y1, y2 = c["y1"], c["y2"]
            ax.plot([x, x], [y1, y2], color='#0055FF', linestyle='-', linewidth=2.5, alpha=0.9)
            
            ax.text(x, y1 - (b_h*0.03), str(num), color='white', weight='bold', fontsize=9, ha='center', va='center',
                    bbox=dict(boxstyle="circle,pad=0.3", fc="#0055FF", ec="black", lw=1))
            ax.text(x, y2 + (b_h*0.03), str(num), color='white', weight='bold', fontsize=9, ha='center', va='center',
                    bbox=dict(boxstyle="circle,pad=0.3", fc="#0055FF", ec="black", lw=1))

        elif c["tipo"] == "H":
            y = c["y"]
            x1, x2 = c["x1"], c["x2"]
            ax.plot([x1, x2], [y, y], color='#0055FF', linestyle='-', linewidth=2.5, alpha=0.9)
            
            ax.text(x1 - (b_w*0.015), y, str(num), color='white', weight='bold', fontsize=9, ha='center', va='center',
                    bbox=dict(boxstyle="circle,pad=0.3", fc="#0055FF", ec="black", lw=1))
            ax.text(x2 + (b_w*0.015), y, str(num), color='white', weight='bold', fontsize=9, ha='center', va='center',
                    bbox=dict(boxstyle="circle,pad=0.3", fc="#0055FF", ec="black", lw=1))

    # Identificación del Retazo R1
    if len(cortes) > 0:
        v_corte = next((c for c in cortes if c["tipo"] == "V"), None)
        if v_corte:
            x_r1 = (v_corte["x"] + b_w) / 2
            y_r1 = b_h / 2
            ancho_r1 = int(b_w - v_corte["x"])
            if ancho_r1 > 100:
                ax.text(x_r1, y_r1, f"RETAZO R1\n({ancho_r1} x {b_h} mm)", color='#888888', weight='bold', fontsize=12, ha='center', va='center')

    # Acotado exterior
    margin_x = b_w * 0.08
    margin_y = b_h * 0.08

    ax.annotate(
        '', xy=(0, -margin_y*0.4), xytext=(b_w, -margin_y*0.4),
        arrowprops=dict(arrowstyle='<->', color='black', lw=1.5)
    )
    ax.text(b_w/2, -margin_y*0.7, f"Ancho: {b_w} mm", ha='center', va='top', fontsize=10, fontweight='bold')

    ax.annotate(
        '', xy=(-margin_x*0.4, 0), xytext=(-margin_x*0.4, b_h),
        arrowprops=dict(arrowstyle='<->', color='black', lw=1.5)
    )
    ax.text(-margin_x*0.7, b_h/2, f"Alto: {b_h} mm", ha='right', va='center', rotation=90, fontsize=10, fontweight='bold')

    aprovechamiento = (area_usada / (b_w * b_h)) * 100
    merma = 100 - aprovechamiento

    ax.set_xlim(-margin_x*1.5, b_w + margin_x*0.5)
    ax.set_ylim(-margin_y*1.5, b_h + margin_y*0.5)
    ax.set_aspect('equal')
    
    titulo_tipo = f"RETAZO DE ALMACÉN: {info['nombre']}" if es_retazo else f"PLANCHA MADRE #{index_num}"
    plt.title(f"{titulo_tipo} ({b_w}x{b_h} mm) — Aprovechamiento: {aprovechamiento:.2f}% | Merma: {merma:.2f}%", fontweight='bold', pad=15)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf, aprovechamiento, merma

# ---------------------------------------------------------
# FUNCIÓN PARA GENERAR REPORTE EN PDF
# ---------------------------------------------------------
def generar_pdf_informe(planchas_usadas, imagenes_list):
    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1A237E'), alignment=1
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#555555'), alignment=1
    )

    story.append(Paragraph("<b>INFORME TÉCNICO DE OPTIMIZACIÓN DE CORTE DE VIDRIO</b>", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Plano de Corte Guillotina y Hoja de Ruta para Taller", subtitle_style))
    story.append(Spacer(1, 15))

    # Resumen general en tabla
    data_resumen = [["Plancha / Retazo", "Dimensiones (mm)", "Aprovechamiento", "Merma"]]
    for idx, (p_data, (img_buf, ap, me)) in enumerate(zip(planchas_usadas, imagenes_list), start=1):
        info = p_data["info"]
        data_resumen.append([
            info["nombre"],
            f"{info['w']} x {info['h']}",
            f"{ap:.2f}%",
            f"{me:.2f}%"
        ])

    t_resumen = Table(data_resumen, colWidths=[150, 130, 120, 120])
    t_resumen.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A237E')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F9F9F9')]),
    ]))
    story.append(t_resumen)
    story.append(Spacer(1, 15))

    # Agregar imágenes de los planos técnicos al PDF
    for idx, (p_data, (img_buf, ap, me)) in enumerate(zip(planchas_usadas, imagenes_list), start=1):
        img_buf.seek(0)
        story.append(Paragraph(f"<b>Plano de Corte #{idx}: {p_data['info']['nombre']}</b>", styles['Heading2']))
        story.append(Spacer(1, 6))
        story.append(RLImage(img_buf, width=520, height=310))
        story.append(Spacer(1, 15))

    doc.build(story)
    pdf_buf.seek(0)
    return pdf_buf

# ---------------------------------------------------------
# EJECUCIÓN Y BOTONES
# ---------------------------------------------------------
if st.button("🚀 Optimizar Cortes y Generar Informe", type="primary"):
    with st.spinner("Calculando plano óptimo..."):
        planchas_usadas, no_colocadas = optimizar_corte_completo(
            plancha_w, plancha_h, cantidad_planchas, permitir_rotacion, edited_data, retazos_editados
        )

        if len(planchas_usadas) == 0:
            st.error("No se pudo ubicar ninguna pieza. Verifica las medidas introducidas.")
        else:
            st.success(f"¡Optimización completada con éxito! Se usaron **{len(planchas_usadas)}** vidrio(s) en total.")

            if len(no_colocadas) > 0:
                st.warning(f"⚠️ Atención: Quedaron **{len(no_colocadas)}** pieza(s) sin cortar por falta de espacio.")

            count_madre = 1
            imagenes_list = []

            for p_data in planchas_usadas:
                img_buf, ap, me = generar_imagen_plano(p_data, count_madre)
                imagenes_list.append((img_buf, ap, me))
                
                if p_data["info"]["tipo"] == "Plancha Madre":
                    count_madre += 1

                st.image(img_buf, use_container_width=True)

            # BOTÓN DE EXPORTAR EN PDF
            st.markdown("---")
            pdf_data = generar_pdf_informe(planchas_usadas, imagenes_list)
            st.download_button(
                label="📄 Descargar Informe Completo en PDF",
                data=pdf_data,
                file_name="Informe_Optimizacion_Corte_Vidrio.pdf",
                mime="application/pdf",
                type="primary"
            )
