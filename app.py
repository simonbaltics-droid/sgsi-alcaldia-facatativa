import io
import os
import sqlite3
import hashlib
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image

# Importaciones de ReportLab para generación de reportes PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage

# --- 1. CONFIGURACIÓN DE PÁGINA E IMÁGENES INSTITUCIONALES ---
FAVICON_PATH = "assets/escudo_alcaldia_150.jpg"
BANNER_PATH = "assets/banner_facatativa_complete.png"
ESCUDO_PATH = "assets/escudo_alcaldia.jpg"

if os.path.exists(FAVICON_PATH):
    st.set_page_config(
        page_title="SGSI & Activos - Alcaldía de Facatativá", 
        layout="wide", 
        page_icon=FAVICON_PATH
    )
else:
    st.set_page_config(
        page_title="SGSI & Activos - Alcaldía de Facatativá", 
        layout="wide", 
        page_icon="🏛️"
    )

# --- 2. BASE DE DATOS Y AUTENTICACIÓN ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def init_db():
    conn = sqlite3.connect('activos_facatativa.db')
    c = conn.cursor()
    
    # Tabla Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY,
            password TEXT,
            rol TEXT
        )
    ''')
    c.execute("SELECT count(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO usuarios VALUES ('admin', ?, 'admin')", (make_hashes('admin123'),))
        c.execute("INSERT INTO usuarios VALUES ('consulta', ?, 'consulta')", (make_hashes('consulta123'),))
    
    # Tabla Activos
    c.execute('''
        CREATE TABLE IF NOT EXISTS activos (
            id TEXT PRIMARY KEY, dependencia TEXT, proceso TEXT, nombre TEXT, tipo TEXT,
            descripcion TEXT, formato TEXT, ubicacion_fisica TEXT, ubicacion_logica TEXT,
            propietario TEXT, custodio TEXT, funcionario_cargo TEXT, confidencialidad TEXT,
            integridad TEXT, disponibilidad TEXT, criticidad TEXT, etiqueta TEXT,
            datos_personales TEXT, tipo_dato_personal TEXT, iccn TEXT, observaciones TEXT
        )
    ''')

    # Tabla Matriz de Riesgos (SGSI ISO 27001)
    c.execute('''
        CREATE TABLE IF NOT EXISTS riesgos (
            id_activo TEXT PRIMARY KEY,
            amenaza TEXT,
            vulnerabilidad TEXT,
            probabilidad INTEGER,
            impacto INTEGER,
            riesgo_inherente INTEGER,
            nivel_riesgo TEXT,
            control_aplicable TEXT,
            efectividad TEXT,
            tratamiento TEXT,
            responsable TEXT,
            fecha_compromiso TEXT,
            estado TEXT,
            FOREIGN KEY (id_activo) REFERENCES activos(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def calcular_criticidad_etiqueta(conf, integ, disp):
    map_c = {"Información Pública Reservada": ("Alta", "IPR"), "Información Pública Clasificada": ("Media", "IPC"), "Información Pública": ("Baja", "IPB")}
    map_i = {"Alta": "A", "Media": "M", "Baja": "B"}
    map_d = {"Alta": "1", "Media": "2", "Baja": "3"}

    c_val, c_etq = map_c.get(conf, ("Alta", "IPR"))
    i_etq = map_i.get(integ, "A")
    d_etq = map_d.get(disp, "1")

    etiqueta = f"{c_etq}-{i_etq}-{d_etq}"
    niveles = [c_val, integ, disp]
    altas = niveles.count("Alta")
    medias = niveles.count("Media")

    if altas >= 2:
        criticidad = "ALTA"
    elif altas == 1 or medias >= 1:
        criticidad = "MEDIA"
    else:
        criticidad = "BAJA"

    return criticidad, etiqueta

# --- 3. GENERACIÓN DE REPORTE PDF OFICIAL ---
def generar_pdf_reporte(df_activos):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    if os.path.exists(BANNER_PATH):
        img_banner = RLImage(BANNER_PATH, width=220, height=60)
        img_banner.hAlign = 'CENTER'
        story.append(img_banner)
        story.append(Spacer(1, 10))

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=14, textColor=colors.HexColor("#800000"), alignment=1, spaceAfter=5)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#333333"), alignment=1, spaceAfter=15)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=8, leading=10)
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.white, fontName="Helvetica-Bold")

    story.append(Paragraph("<b>ALCALDÍA MUNICIPAL DE FACATATIVÁ</b>", title_style))
    story.append(Paragraph("Sistema de Gestión de Seguridad de la Información (ISO 27001)<br/><b>Informe Ejecutivo de Inventario de Activos y Hallazgos</b>", subtitle_style))

    total_activos = len(df_activos)
    crit_alta = len(df_activos[df_activos['criticidad'] == 'ALTA'])
    crit_media = len(df_activos[df_activos['criticidad'] == 'MEDIA'])
    crit_baja = len(df_activos[df_activos['criticidad'] == 'BAJA'])

    resumen_text = f"<b>Total Activos Registrados:</b> {total_activos} | <b>Criticidad ALTA:</b> {crit_alta} | <b>MEDIA:</b> {crit_media} | <b>BAJA:</b> {crit_baja}"
    story.append(Paragraph(resumen_text, styles['Normal']))
    story.append(Spacer(1, 15))

    data = [[
        Paragraph("<b>ID / Nombre</b>", header_style),
        Paragraph("<b>Dependencia</b>", header_style),
        Paragraph("<b>Tipo</b>", header_style),
        Paragraph("<b>Criticidad</b>", header_style),
        Paragraph("<b>Observaciones de Entrevista</b>", header_style)
    ]]

    for _, row in df_activos.iterrows():
        obs = str(row['observaciones']) if pd.notnull(row['observaciones']) and str(row['observaciones']).strip() != "" else "Sin observaciones."
        data.append([
            Paragraph(f"<b>{row['id']}</b><br/>{row['nombre']}", body_style),
            Paragraph(str(row['dependencia']), body_style),
            Paragraph(str(row['tipo']), body_style),
            Paragraph(str(row['criticidad']), body_style),
            Paragraph(obs, body_style)
        ])

    table = Table(data, colWidths=[100, 100, 80, 60, 210])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#800000")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9F9F9")]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))

    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer

# --- 4. CONTROL DE SESIÓN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ''
    st.session_state['rol'] = ''

if not st.session_state['logged_in']:
    if os.path.exists(BANNER_PATH):
        st.image(BANNER_PATH, width=380)
    st.title("🏛️ Alcaldía Municipal de Facatativá")
    st.subheader("Sistema de Gestión de Activos de Información y SGSI (ISO 27001)")
    
    with st.form("login_form"):
        user = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Iniciar Sesión"):
            conn = sqlite3.connect('activos_facatativa.db')
            c = conn.cursor()
            c.execute("SELECT password, rol FROM usuarios WHERE username = ?", (user,))
            result = c.fetchone()
            conn.close()
            
            if result and check_hashes(password, result[0]):
                st.session_state['logged_in'] = True
                st.session_state['username'] = user
                st.session_state['rol'] = result[1]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    st.info("Credenciales: Admin (`admin` / `admin123`) | Consulta (`consulta` / `consulta123`)")
    st.stop()

# --- 5. BARRA LATERAL (SIDEBAR) ---
if os.path.exists(ESCUDO_PATH):
    st.sidebar.image(ESCUDO_PATH, use_container_width=True)

st.sidebar.title(f"👤 {st.session_state['username'].capitalize()}")
st.sidebar.caption(f"Rol Activo: **{st.session_state['rol'].upper()}**")

if st.sidebar.button("Cerrar Sesión"):
    st.session_state['logged_in'] = False
    st.rerun()

menu = ["📊 Dashboard Ejecutivo", "🔍 Consulta y Búsqueda", "🛡️ Matriz SGSI & Riesgos (ISO 27001)"]
if st.session_state['rol'] == 'admin':
    menu.insert(1, "📥 Carga Masiva de Entrevistas")
    menu.insert(2, "📝 Registro Manual de Activos")

opcion = st.sidebar.radio("Navegación", menu)

# --- ENCABEZADO PRINCIPAL ---
if os.path.exists(BANNER_PATH):
    st.image(BANNER_PATH, width=360)
st.title("Gestión de Activos & SGSI")
st.markdown("---")

# --- MÓDULO 0: DASHBOARD VISUAL INTERACTIVO ---
if opcion == "📊 Dashboard Ejecutivo":
    st.header("📊 Dashboard de Control e Indicadores Clave SGSI")
    
    conn = sqlite3.connect('activos_facatativa.db')
    df = pd.read_sql_query("SELECT * FROM activos", conn)
    df_r = pd.read_sql_query("SELECT * FROM riesgos", conn)
    conn.close()

    if not df.empty:
        # Métricas Rápidas
        tot = len(df)
        c_alta = len(df[df['criticidad'] == 'ALTA'])
        c_med = len(df[df['criticidad'] == 'MEDIA'])
        c_dp = len(df[df['datos_personales'] == 'Sí'])
        c_iccn = len(df[df['iccn'] == 'Sí'])

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Activos", tot)
        m2.metric("Criticidad ALTA", c_alta, delta=f"{(c_alta/tot)*100:.1f}%", delta_color="inverse")
        m3.metric("Criticidad MEDIA", c_med)
        m4.metric("Con Datos Personales", c_dp)
        m5.metric("Infraestructura Crítica", c_iccn)

        st.markdown("---")

        # Gráficos
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.subheader("Distribución por Criticidad")
            fig_crit = px.pie(
                df, names='criticidad', title='Criticidad de Activos',
                color='criticidad',
                color_discrete_map={'ALTA': '#D9534F', 'MEDIA': '#F0AD4E', 'BAJA': '#5CB85C'},
                hole=0.4
            )
            st.plotly_chart(fig_crit, use_container_width=True)

        with col_g2:
            st.subheader("Activos por Dependencia")
            df_dep = df['dependencia'].value_counts().reset_index()
            df_dep.columns = ['Dependencia', 'Cantidad']
            fig_dep = px.bar(
                df_dep, x='Cantidad', y='Dependencia', orientation='h',
                title='Inventario por Dependencia', text='Cantidad',
                color='Cantidad', color_continuous_scale='Reds'
            )
            st.plotly_chart(fig_dep, use_container_width=True)

        col_g3, col_g4 = st.columns(2)
        
        with col_g3:
            st.subheader("Distribución por Tipo de Activo")
            df_tipo = df['tipo'].value_counts().reset_index()
            df_tipo.columns = ['Tipo', 'Cantidad']
            fig_tipo = px.pie(df_tipo, values='Cantidad', names='Tipo', title='Tipología de Activos', hole=0.3)
            st.plotly_chart(fig_tipo, use_container_width=True)

        with col_g4:
            st.subheader("Tratamiento de Riesgos Evaluación SGSI")
            if not df_r.empty and 'tratamiento' in df_r.columns:
                df_trat = df_r['tratamiento'].value_counts().reset_index()
                df_trat.columns = ['Estrategia', 'Cantidad']
                fig_trat = px.bar(df_trat, x='Estrategia', y='Cantidad', color='Estrategia', title='Estrategias de Tratamiento')
                st.plotly_chart(fig_trat, use_container_width=True)
            else:
                st.info("Aún no se han evaluado riesgos en la Matriz SGSI para generar este gráfico.")
    else:
        st.info("No hay información registrada en la base de datos para generar métricas.")

# --- MÓDULO 1: CARGA MASIVA ---
elif opcion == "📥 Carga Masiva de Entrevistas":
    st.header("📥 Carga Masiva de Datos de Entrevistas")
    uploaded_file = st.file_uploader("Cargar Plantilla (.xlsx o .csv)", type=["xlsx", "csv"])

    if uploaded_file:
        try:
            df_upload = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.write("Preview de datos a procesar:")
            st.dataframe(df_upload.head(5))

            if st.button("Procesar y Guardar en Base de Datos"):
                conn = sqlite3.connect('activos_facatativa.db')
                c = conn.cursor()
                registros = 0
                for _, row in df_upload.iterrows():
                    crit, etq = calcular_criticidad_etiqueta(
                        row.get('CONFIDENCIALIDAD', 'Información Pública Reservada'),
                        row.get('INTEGRIDAD', 'Alta'),
                        row.get('DISPONIBILIDAD', 'Alta')
                    )
                    c.execute('''
                        INSERT OR REPLACE INTO activos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ''', (
                        str(row.get('ID_ACTIVO', '')), str(row.get('DEPENDENCIA', '')), str(row.get('PROCESO', '')),
                        str(row.get('NOMBRE_ACTIVO', '')), str(row.get('TIPO_ACTIVO', '')), str(row.get('DESCRIPCION', '')),
                        str(row.get('FORMATO_SOPORTE', '')), str(row.get('UBICACION_FISICA', '')), str(row.get('UBICACION_LOGICA', '')),
                        str(row.get('PROPIETARIO', '')), str(row.get('CUSTODIO', '')), str(row.get('FUNCIONARIO_CARGO', '')),
                        str(row.get('CONFIDENCIALIDAD', '')), str(row.get('INTEGRIDAD', '')), str(row.get('DISPONIBILIDAD', '')),
                        crit, etq, str(row.get('DATOS_PERSONALES', 'No')), str(row.get('TIPO_DATO_PERSONAL', 'N/A')),
                        str(row.get('ICCN', 'No')), str(row.get('OBSERVACIONES', ''))
                    ))
                    registros += 1
                conn.commit()
                conn.close()
                st.success(f"¡Se procesaron y cargaron correctamente {registros} activos!")
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")

# --- MÓDULO 2: REGISTRO MANUAL ---
elif opcion == "📝 Registro Manual de Activos":
    st.header("📝 Formulario Individual de Activos")
    with st.form("form_registro_individual"):
        col1, col2 = st.columns(2)
        with col1:
            id_act = st.text_input("ID Activo (TRD)", "TIC-001")
            dep = st.selectbox("Dependencia", ["Secretaría General", "Secretaría de Hacienda", "Secretaría de Planeación", "Oficina de TIC", "Secretaría de Gobierno"])
            proc = st.text_input("Proceso", "Gestión de Tecnología")
            nom = st.text_input("Nombre del Activo", "Servidor Web Alcaldía")
            tipo = st.selectbox("Tipo de Activo", ["Información", "Software", "Hardware", "Servicios", "Recurso Humano", "Instalaciones", "Redes"])
            desc = st.text_area("Descripción")
            formato = st.selectbox("Formato / Soporte", ["Digital", "Físico", "Mixto"])
            ub_fis = st.text_input("Ubicación Física", "Datacenter Puesto 1")
            ub_log = st.text_input("Ubicación Lógica", "192.168.1.10")
        with col2:
            prop = st.text_input("Propietario (Cargo)", "Jefe de TIC")
            cust = st.text_input("Custodio", "Administrador de Red")
            func = st.text_input("Funcionario a Cargo", "Ingeniero de Soporte")
            conf = st.selectbox("Confidencialidad", ["Información Pública Reservada", "Información Pública Clasificada", "Información Pública"])
            integ = st.selectbox("Integridad", ["Alta", "Media", "Baja"])
            disp = st.selectbox("Disponibilidad", ["Alta", "Media", "Baja"])
            dp = st.selectbox("¿Contiene Datos Personales?", ["No", "Sí"])
            tdp = st.selectbox("Tipo Dato Personal", ["N/A", "Público", "Semiprivado", "Privado", "Sensible"])
            iccn = st.selectbox("¿Afecta ICCN?", ["No", "Sí"])
        
        obs = st.text_area("Observaciones de la Entrevista", placeholder="Escriba hallazgos recabados en la entrevista...")

        if st.form_submit_button("Guardar Activo"):
            crit, etq = calcular_criticidad_etiqueta(conf, integ, disp)
            conn = sqlite3.connect('activos_facatativa.db')
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO activos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (id_act, dep, proc, nom, tipo, desc, formato, ub_fis, ub_log, prop, cust, func, conf, integ, disp, crit, etq, dp, tdp, iccn, obs))
            conn.commit()
            conn.close()
            st.success(f"Activo guardado exitosamente. Criticidad: {crit} | Etiqueta: {etq}")

# --- MÓDULO 3: CONSULTA Y BÚSQUEDA ---
elif opcion == "🔍 Consulta y Búsqueda":
    st.header("🔍 Inventario de Activos de Información")
    conn = sqlite3.connect('activos_facatativa.db')
    df = pd.read_sql_query("SELECT * FROM activos", conn)
    conn.close()

    if not df.empty:
        # Buscador por texto libre
        busqueda = st.text_input("🔎 Buscar por palabra clave (Nombre, Descripción u Observaciones):")

        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1: f_dep = st.multiselect("Filtrar por Dependencia", df['dependencia'].unique())
        with col_f2: f_tipo = st.multiselect("Filtrar por Tipo", df['tipo'].unique())
        with col_f3: f_crit = st.multiselect("Filtrar por Criticidad", df['criticidad'].unique())

        df_filtered = df.copy()

        if busqueda:
            mask = df_filtered['nombre'].str.contains(busqueda, case=False, na=False) | \
                   df_filtered['descripcion'].str.contains(busqueda, case=False, na=False) | \
                   df_filtered['observaciones'].str.contains(busqueda, case=False, na=False)
            df_filtered = df_filtered[mask]

        if f_dep: df_filtered = df_filtered[df_filtered['dependencia'].isin(f_dep)]
        if f_tipo: df_filtered = df_filtered[df_filtered['tipo'].isin(f_tipo)]
        if f_crit: df_filtered = df_filtered[df_filtered['criticidad'].isin(f_crit)]

        st.dataframe(df_filtered, use_container_width=True)

        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            st.download_button(
                label="📊 Exportar Consulta a CSV",
                data=df_filtered.to_csv(index=False).encode('utf-8'),
                file_name='Inventario_Activos_Facatativa.csv',
                mime='text/csv'
            )
        with col_exp2:
            pdf_data = generar_pdf_reporte(df_filtered)
            st.download_button(
                label="📄 Generar Reporte PDF Oficial",
                data=pdf_data,
                file_name='Reporte_Ejecutivo_Activos_Facatativa.pdf',
                mime='application/pdf'
            )
    else:
        st.info("No hay activos registrados en la base de datos.")

# --- MÓDULO 4: MATRIZ SGSI & RIESGOS (MEJORAS DE NEGOCIO Y GESTIÓN) ---
elif opcion == "🛡️ Matriz SGSI & Riesgos (ISO 27001)":
    st.header("🛡️ Gestión de Riesgos y Plan de Tratamiento (ISO 27001)")
    
    AMENAZAS = [
        "A.01 - Accesos no autorizados a sistemas o datos",
        "A.02 - Infección por código malicioso (Ransomware / Malware)",
        "A.03 - Interrupción de servicios públicos o de conectividad",
        "A.04 - Fuga de información por personal interno o contratistas",
        "A.05 - Falla física de hardware o centro de datos",
        "A.06 - Errores de digitación o procesamiento de información"
    ]

    VULNERABILIDADES = [
        "V.01 - Ausencia de copias de seguridad (Backups) periódicas",
        "V.02 - Falta de parches de actualización en sistemas operativos",
        "V.03 - Ausencia de acuerdos de confidencialidad en contratos",
        "V.04 - Contraseñas débiles o compartidas entre funcionarios",
        "V.05 - Ausencia de controles de acceso físico"
    ]

    CONTROLES = [
        "A.5.1 - Políticas de seguridad de la información",
        "A.7.2 - Concientización y capacitación en ciberseguridad",
        "A.8.1 - Dispositivos de usuario y control de accesos",
        "A.8.12 - Prevención de fuga de datos (DLP)",
        "A.8.13 - Copias de seguridad de la información"
    ]

    conn = sqlite3.connect('activos_facatativa.db')
    df_activos = pd.read_sql_query("SELECT * FROM activos WHERE criticidad IN ('ALTA', 'MEDIA')", conn)
    conn.close()

    if not df_activos.empty:
        st.subheader("1. Evaluación de Riesgo e Identificación de Controles")
        
        # Mapeo de activos
        opciones_activos = {f"{row['id']} - {row['nombre']} ({row['dependencia']})": row['id'] for _, row in df_activos.iterrows()}
        act_seleccionado_label = st.selectbox("Seleccione el Activo a Evaluar:", list(opciones_activos.keys()))
        act_id = opciones_activos[act_seleccionado_label]

        with st.form("form_evaluacion_riesgo"):
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                amenaza = st.selectbox("Amenaza Asociada", AMENAZAS)
                vulnerabilidad = st.selectbox("Vulnerabilidad Asociada", VULNERABILIDADES)
                prob = st.slider("Probabilidad (1: Muy Baja - 5: Muy Alta)", 1, 5, 3)
                imp = st.slider("Impacto (1: Insignificante - 5: Catastrófico)", 1, 5, 4)
                
                r_inh = prob * imp
                if r_inh >= 15:
                    n_riesgo = "CRÍTICO"
                elif r_inh >= 10:
                    n_riesgo = "ALTO"
                elif r_inh >= 5:
                    n_riesgo = "MEDIO"
                else:
                    n_riesgo = "BAJO"
                
                st.warning(f"Riesgo Inherente: **{r_inh} / 25** (Nivel: **{n_riesgo}**)")

            with col_r2:
                ctrl = st.selectbox("Control Aplicable (ISO 27001 Anexo A)", CONTROLES)
                efect = st.select_slider("Efectividad del Control", options=["Sin Control", "Débil", "Moderado", "Fuerte"])
                trat = st.selectbox("Opción de Tratamiento", ["Reducir el Riesgo", "Aceptar el Riesgo", "Transferir el Riesgo", "Evitar el Riesgo"])
                resp = st.text_input("Responsable de Implementación", "Oficina de TIC")
                f_comp = st.date_input("Fecha Compromiso de Implementación")
                est = st.selectbox("Estado del Plan", ["Pendiente", "En Proceso", "Implementado"])

            if st.form_submit_button("Guardar Evaluación de Riesgo"):
                conn = sqlite3.connect('activos_facatativa.db')
                c = conn.cursor()
                c.execute('''
                    INSERT OR REPLACE INTO riesgos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (act_id, amenaza, vulnerabilidad, prob, imp, r_inh, n_riesgo, ctrl, efect, trat, resp, str(f_comp), est))
                conn.commit()
                conn.close()
                st.success(f"Evaluación de riesgo guardada correctamente para el activo {act_id}.")

        st.markdown("---")
        st.subheader("2. Matriz Consolidada de Riesgos Registrados")
        
        conn = sqlite3.connect('activos_facatativa.db')
        df_matriz = pd.read_sql_query('''
            SELECT r.*, a.nombre as nombre_activo, a.dependencia 
            FROM riesgos r 
            JOIN activos a ON r.id_activo = a.id
        ''', conn)
        conn.close()

        if not df_matriz.empty:
            st.dataframe(df_matriz, use_container_width=True)
            
            # Exportar Matriz de Riesgos a Excel
            buffer_excel = io.BytesIO()
            with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                df_matriz.to_excel(writer, index=False, sheet_name='Matriz_Riesgos')
            buffer_excel.seek(0)

            st.download_button(
                label="📊 Exportar Matriz de Riesgos a Excel (.xlsx)",
                data=buffer_excel,
                file_name="Matriz_Riesgos_SGSI_Facatativa.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Aún no hay evaluaciones guardadas en la matriz de riesgos.")
    else:
        st.info("No hay activos registrados con criticidad ALTA o MEDIA para evaluar riesgos.")