"""Idempotent production seed for the October 7 requested vacancy set.

The script is intentionally safe to re-run: it only creates a vacancy when no
existing Talent job matches the canonical title or one of its source aliases.
New jobs are created through the domain service so Odoo publication follows the
same production path as jobs created from the UI.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone

from app.db import SessionLocal
from app.domains.jobs import service
from app.models import Job, UserProfile


OWNER_EMAILS = (
    "talentohumano@asiati.com.co",
    "sistemas@asiati.com.co",
)


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _profile(
    *,
    minimum_years_experience: float | None = None,
    responsibilities=(),
    domain_knowledge=(),
    education=(),
    technical_competencies=(),
    required_technologies=(),
    preferred_technologies=(),
    languages=(),
    assumptions_to_validate=(),
):
    return {
        "required_technologies": list(required_technologies),
        "preferred_technologies": list(preferred_technologies),
        "required_certifications": [],
        "preferred_certifications": [],
        "minimum_years_experience": minimum_years_experience,
        "specific_experience": [],
        "responsibilities": list(responsibilities),
        "domain_knowledge": list(domain_knowledge),
        "education": list(education),
        "languages": list(languages),
        "technical_competencies": list(technical_competencies),
        "assumptions_to_validate": list(assumptions_to_validate),
    }


JOBS = [
    {
        "title": "Country Manager Chile",
        "aliases": ["COUNTRY MANAGER CHILE"],
        "country_code": "CL",
        "description": """Objetivo del cargo
Liderar la operación de ASIATI en Chile, integrando crecimiento comercial, ejecución operativa, rentabilidad y desarrollo del equipo local. Será responsable de convertir la estrategia corporativa en resultados sostenibles para el país.

Responsabilidades principales
- Definir y ejecutar el plan de negocio para Chile, con metas de ingresos, margen, servicio y crecimiento.
- Liderar relaciones con clientes estratégicos, oportunidades comerciales y negociaciones de alto impacto.
- Coordinar las áreas operativas, administrativas y financieras del país.
- Monitorear KPIs, presupuesto, riesgos y cumplimiento de compromisos contractuales.
- Desarrollar al equipo local y asegurar alineación con los estándares corporativos de ASIATI.

Perfil buscado
Profesional con experiencia comprobada liderando unidades de negocio, operaciones o equipos multidisciplinarios. Se valorará experiencia en servicios, logística, retail o entornos B2B, capacidad analítica, orientación comercial y manejo de indicadores.""",
        "profile": _profile(
            minimum_years_experience=5,
            responsibilities=("Dirección integral de la operación país", "Gestión comercial y de clientes estratégicos", "Control de presupuesto y rentabilidad", "Liderazgo de equipos"),
            domain_knowledge=("Gestión de unidades de negocio", "Operaciones B2B", "Mercado chileno"),
            education=("Profesional en Administración, Ingeniería, Economía o áreas afines"),
            technical_competencies=("Planeación estratégica", "Gestión de P&L", "KPIs", "Negociación"),
        ),
    },
    {
        "title": "Líder de Operaciones Logísticas y Financieras",
        "aliases": ["LÍDER DE OPERACIONES LOGÍSTICAS Y FINANCIERA"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Asegurar una operación logística eficiente y financieramente controlada, conectando ejecución, costos, inventarios, proveedores y seguimiento presupuestal para mejorar la rentabilidad y el nivel de servicio.

Responsabilidades principales
- Coordinar procesos logísticos, abastecimiento, inventarios, despachos y cumplimiento operativo.
- Controlar costos, conciliaciones, presupuestos y desviaciones asociadas a la operación.
- Construir y hacer seguimiento a indicadores de productividad, servicio y rentabilidad.
- Articular proveedores, áreas financieras y equipos operativos.
- Identificar oportunidades de mejora y estandarizar procesos críticos.

Perfil buscado
Profesional con experiencia en operaciones logísticas y control financiero, dominio de Excel y capacidad para transformar datos operativos en decisiones de negocio.""",
        "profile": _profile(
            minimum_years_experience=3,
            responsibilities=("Gestión logística", "Control financiero operativo", "Seguimiento de costos e inventarios", "Gestión de proveedores"),
            domain_knowledge=("Logística", "Costos", "Presupuestos", "Inventarios"),
            education=("Profesional en Ingeniería Industrial, Logística, Administración, Finanzas o áreas afines"),
            required_technologies=("Excel"),
            technical_competencies=("Análisis financiero", "KPIs operativos", "Mejora de procesos"),
        ),
    },
    {
        "title": "CFO",
        "aliases": ["CFO"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Dirigir la estrategia financiera de la organización, asegurando liquidez, rentabilidad, control, cumplimiento y calidad de la información para soportar las decisiones de crecimiento de ASIATI.

Responsabilidades principales
- Liderar planeación financiera, presupuesto, flujo de caja, tesorería y control de gestión.
- Presentar análisis financieros y escenarios de decisión a la alta dirección.
- Supervisar contabilidad, impuestos, cierres, auditoría y cumplimiento financiero.
- Diseñar políticas de control interno, gestión de riesgos y optimización de capital.
- Acompañar decisiones de inversión, financiación y expansión.

Perfil buscado
Ejecutivo financiero con trayectoria liderando equipos y procesos de alta complejidad. Se requiere visión estratégica, criterio de riesgo, solidez analítica y capacidad para conectar finanzas con operación y crecimiento.""",
        "profile": _profile(
            minimum_years_experience=8,
            responsibilities=("Dirección financiera", "Planeación y presupuesto", "Tesorería y liquidez", "Control interno y riesgos", "Reportes a alta dirección"),
            domain_knowledge=("FP&A", "Contabilidad", "Tesorería", "Impuestos", "Finanzas corporativas"),
            education=("Profesional en Finanzas, Contaduría, Economía, Administración o áreas afines", "Posgrado financiero o gerencial deseable"),
            technical_competencies=("Modelación financiera", "Gestión de P&L", "Presupuestos", "Control financiero"),
        ),
    },
    {
        "title": "Administrativo Chile",
        "aliases": ["ADMINISTRATIVO CHILE"],
        "country_code": "CL",
        "description": """Objetivo del cargo
Brindar soporte administrativo confiable a la operación en Chile, manteniendo organizada la documentación, los registros, las solicitudes internas y el seguimiento de proveedores y procesos de soporte.

Responsabilidades principales
- Gestionar documentación, archivos, solicitudes y controles administrativos.
- Apoyar compras, proveedores, facturación y seguimiento de novedades.
- Mantener bases de datos e indicadores administrativos actualizados.
- Coordinar requerimientos con áreas internas y proveedores.
- Asegurar trazabilidad y cumplimiento de los procedimientos definidos.

Perfil buscado
Persona organizada, orientada al detalle y con experiencia en soporte administrativo. Se valora dominio de Excel, buena comunicación y capacidad para manejar varias prioridades simultáneamente.""",
        "profile": _profile(
            minimum_years_experience=1,
            responsibilities=("Gestión documental", "Soporte administrativo", "Seguimiento de proveedores y solicitudes"),
            domain_knowledge=("Procesos administrativos",),
            education=("Técnico, tecnólogo o profesional en áreas administrativas o afines"),
            required_technologies=("Excel"),
            technical_competencies=("Organización documental", "Seguimiento de tareas", "Manejo de información"),
        ),
    },
    {
        "title": "Auxiliar Administrativo Chin-Chin",
        "aliases": ["AUXILIAR ADMINISTRATIO CHIN-CHIN", "AUXILIAR ADMINISTRATIVO CHIN CHIN"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Apoyar la operación administrativa de Chin-Chin mediante el registro oportuno de información, control documental, seguimiento de novedades y soporte a las necesidades diarias del punto o unidad asignada.

Responsabilidades principales
- Registrar y actualizar información operativa y administrativa.
- Organizar soportes, documentos, facturas y novedades.
- Apoyar controles de inventario, caja o proveedores cuando el proceso lo requiera.
- Atender solicitudes internas y realizar seguimiento hasta su cierre.
- Mantener orden y trazabilidad de los archivos del área.

Perfil buscado
Técnico o tecnólogo con orientación al servicio, orden, atención al detalle y manejo básico/intermedio de herramientas ofimáticas.""",
        "profile": _profile(
            minimum_years_experience=1,
            responsibilities=("Registro administrativo", "Gestión documental", "Apoyo a inventarios y novedades"),
            domain_knowledge=("Operación administrativa",),
            education=("Técnico o tecnólogo en Administración, Contabilidad o áreas afines"),
            required_technologies=("Excel"),
            technical_competencies=("Digitación", "Organización", "Control documental"),
            assumptions_to_validate=("Validar alcance operativo específico de la unidad Chin-Chin"),
        ),
    },
    {
        "title": "Head of Marketing Global",
        "aliases": ["HEAT OF MARKETING GLOBAL", "HEAD OF MARKETING GLOBAL"],
        "country_code": None,
        "description": """Objetivo del cargo
Diseñar y liderar la estrategia global de marketing de ASIATI, fortaleciendo posicionamiento, generación de demanda, marca y crecimiento mediante una operación integrada entre contenido, performance, analítica y equipos comerciales.

Responsabilidades principales
- Definir estrategia, prioridades, presupuesto y KPIs de marketing para los distintos mercados.
- Liderar posicionamiento de marca, campañas, contenido, canales digitales y generación de demanda.
- Construir un modelo de medición de adquisición, conversión, CAC, retorno y contribución al pipeline.
- Coordinar agencias, proveedores y equipos internos.
- Alinear marketing con ventas, producto y objetivos de expansión.

Perfil buscado
Líder de marketing con experiencia construyendo estrategia multicanal y equipos de alto desempeño, fuerte orientación a datos y capacidad para operar en diferentes mercados.""",
        "profile": _profile(
            minimum_years_experience=5,
            responsibilities=("Estrategia global de marketing", "Generación de demanda", "Gestión de marca", "Liderazgo de equipo y proveedores"),
            domain_knowledge=("Marketing B2B/B2C", "Performance marketing", "Branding", "Growth"),
            education=("Profesional en Marketing, Comunicación, Administración o áreas afines"),
            preferred_technologies=("CRM", "Google Analytics", "Plataformas de pauta"),
            technical_competencies=("Analítica de marketing", "Gestión de presupuesto", "Funnel y conversión"),
        ),
    },
    {
        "title": "Jefe de Operaciones",
        "aliases": ["JEFE DE OPERACIONES"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Dirigir la ejecución operativa asegurando cumplimiento, productividad, calidad de servicio y uso eficiente de recursos, con foco permanente en indicadores y mejora continua.

Responsabilidades principales
- Planear y supervisar la operación diaria y la capacidad del equipo.
- Asegurar cumplimiento de SLAs, procedimientos, productividad y calidad.
- Gestionar indicadores, novedades, riesgos y planes de acción.
- Liderar personal operativo y desarrollar estándares de trabajo.
- Coordinar con clientes y áreas de soporte la solución de desviaciones.

Perfil buscado
Líder operativo con experiencia gestionando equipos, indicadores y procesos de alta ejecución. Se valora experiencia en logística, servicios, retail u operaciones distribuidas.""",
        "profile": _profile(
            minimum_years_experience=4,
            responsibilities=("Dirección de operaciones", "Gestión de equipos", "Cumplimiento de SLA", "Mejora continua"),
            domain_knowledge=("Operaciones", "Productividad", "Calidad de servicio"),
            education=("Profesional en Ingeniería, Administración, Logística o áreas afines"),
            technical_competencies=("KPIs", "Planeación operativa", "Gestión de capacidad", "Análisis de causa raíz"),
        ),
    },
    {
        "title": "Administrador de Punto de Venta",
        "aliases": ["ADMINISTRADOR PUNTO DE VENTA"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Administrar integralmente el punto de venta, garantizando cumplimiento de metas comerciales, servicio al cliente, control de caja e inventario y correcta ejecución de los estándares operativos.

Responsabilidades principales
- Liderar al equipo del punto y organizar turnos y prioridades.
- Cumplir metas de venta, conversión, ticket promedio y servicio.
- Controlar caja, inventarios, recepción de mercancía y novedades.
- Garantizar presentación, orden y cumplimiento de procedimientos.
- Gestionar indicadores y reportar oportunidades o desviaciones.

Perfil buscado
Persona con experiencia administrando tiendas o puntos de venta, liderazgo cercano, orientación comercial y disciplina operativa.""",
        "profile": _profile(
            minimum_years_experience=2,
            responsibilities=("Administración de punto de venta", "Liderazgo de equipo", "Control de caja e inventario", "Cumplimiento comercial"),
            domain_knowledge=("Retail", "Servicio al cliente", "Inventarios"),
            education=("Técnico, tecnólogo o profesional en áreas comerciales, administrativas o afines"),
            technical_competencies=("Indicadores de venta", "Control de inventario", "Manejo de caja"),
        ),
    },
    {
        "title": "BDE",
        "aliases": ["BDE"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Impulsar el desarrollo de nuevas oportunidades de negocio, construyendo un pipeline comercial saludable desde la prospección hasta la calificación y avance de oportunidades con clientes potenciales.

Responsabilidades principales
- Identificar, investigar y contactar prospectos con potencial comercial.
- Calificar oportunidades y mantener información confiable en el CRM.
- Coordinar reuniones, propuestas y seguimientos con el equipo comercial.
- Medir actividad, conversión, pipeline y resultados de prospección.
- Aportar inteligencia de mercado y retroalimentación sobre necesidades de clientes.

Perfil buscado
Perfil comercial consultivo, disciplinado en seguimiento, comunicación y construcción de relaciones. Se valora experiencia en ventas B2B, prospección y gestión de CRM.""",
        "profile": _profile(
            minimum_years_experience=2,
            responsibilities=("Prospección", "Desarrollo de oportunidades", "Gestión de pipeline", "Seguimiento comercial"),
            domain_knowledge=("Ventas B2B", "Desarrollo de negocios"),
            education=("Técnico, tecnólogo o profesional en áreas comerciales, administrativas o afines"),
            preferred_technologies=("CRM",),
            technical_competencies=("Prospección", "Calificación de leads", "Negociación", "Seguimiento comercial"),
            assumptions_to_validate=("Confirmar el alcance interno exacto asociado al acrónimo BDE"),
        ),
    },
    {
        "title": "Vendedores de Tienda",
        "aliases": ["VENDEDORES DE TIENDA"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Brindar una experiencia de compra cercana y efectiva, asesorando a cada cliente y contribuyendo al cumplimiento de las metas comerciales del punto de venta.

Responsabilidades principales
- Recibir, orientar y asesorar clientes según sus necesidades.
- Ejecutar el proceso de venta y apoyar el cumplimiento de metas.
- Mantener productos, exhibiciones y espacios en condiciones adecuadas.
- Apoyar inventarios, recepción de mercancía y novedades del punto.
- Cumplir protocolos de servicio, caja y operación cuando aplique.

Perfil buscado
Persona con actitud comercial, servicio al cliente, comunicación clara y disposición para trabajar por metas. La experiencia previa en retail es deseable, no excluyente para perfiles con alto potencial.""",
        "profile": _profile(
            minimum_years_experience=0,
            responsibilities=("Atención y asesoría al cliente", "Venta en punto", "Apoyo de inventarios y exhibición"),
            domain_knowledge=("Retail", "Servicio al cliente"),
            education=("Bachiller; formación técnica comercial es deseable"),
            technical_competencies=("Venta consultiva", "Servicio al cliente", "Comunicación"),
        ),
    },
    {
        "title": "Head de Selección y Talento Humano",
        "aliases": ["HEAT SELECCIÓN Y TH", "HEAD SELECCIÓN Y TH"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Liderar la estrategia de selección y gestión de talento humano, asegurando atracción oportuna de perfiles, calidad de contratación, experiencia del candidato y evolución de los procesos de personas.

Responsabilidades principales
- Dirigir reclutamiento, selección, entrevistas y seguimiento de vacantes.
- Definir indicadores de cobertura, tiempo de contratación, calidad y fuentes.
- Liderar onboarding, documentación y coordinación de procesos de ingreso.
- Desarrollar políticas, procesos y herramientas de talento humano.
- Acompañar líderes en decisiones de estructura, desempeño y desarrollo.

Perfil buscado
Profesional de Talento Humano con experiencia liderando selección de múltiples perfiles y equipos, alta orientación a métricas y capacidad para combinar experiencia humana con automatización y tecnología.""",
        "profile": _profile(
            minimum_years_experience=5,
            responsibilities=("Dirección de selección", "Gestión de indicadores de talento", "Onboarding", "Liderazgo de procesos de RRHH"),
            domain_knowledge=("Recruiting", "Talent acquisition", "Gestión humana"),
            education=("Profesional en Psicología, Administración, Ingeniería Industrial o áreas afines"),
            preferred_technologies=("ATS",),
            technical_competencies=("Entrevista por competencias", "Métricas de selección", "Diseño de procesos"),
        ),
    },
    {
        "title": "Community Manager (2)",
        "aliases": ["COMMUNITY MANAGER (2)"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Gestionar y hacer crecer las comunidades digitales de la marca mediante contenido relevante, interacción oportuna y seguimiento de métricas. Esta vacante contempla 2 posiciones.

Responsabilidades principales
- Planear, publicar y dar seguimiento al calendario de contenidos.
- Gestionar conversaciones, mensajes y comentarios en canales sociales.
- Redactar copys alineados con el tono y objetivos de marca.
- Monitorear tendencias, reputación y oportunidades de conversación.
- Analizar resultados y proponer mejoras a partir de métricas de alcance, interacción y crecimiento.

Perfil buscado
Perfil creativo y organizado, con excelente redacción, criterio visual y experiencia gestionando comunidades y redes sociales.""",
        "profile": _profile(
            minimum_years_experience=1,
            responsibilities=("Gestión de redes sociales", "Creación y publicación de contenido", "Community engagement", "Reporte de métricas"),
            domain_knowledge=("Social media", "Contenido digital", "Reputación de marca"),
            education=("Técnico, tecnólogo o profesional en Comunicación, Marketing, Publicidad o áreas afines"),
            preferred_technologies=("Meta Business Suite", "Herramientas de diseño de contenido"),
            technical_competencies=("Copywriting", "Analítica de redes", "Gestión de comunidad"),
        ),
    },
    {
        "title": "Regente de Farmacia",
        "aliases": ["REGENTE DE FARMACIA"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Garantizar la correcta operación técnica y administrativa del servicio farmacéutico, promoviendo el manejo seguro de medicamentos, el cumplimiento normativo y una atención responsable al usuario.

Responsabilidades principales
- Supervisar recepción, almacenamiento, control y dispensación de medicamentos.
- Mantener inventarios, registros, condiciones de almacenamiento y trazabilidad.
- Aplicar procedimientos y requisitos regulatorios vigentes.
- Gestionar novedades, vencimientos, devoluciones y controles internos.
- Orientar al equipo y usuarios dentro del alcance permitido por la regulación.

Perfil buscado
Tecnólogo en Regencia de Farmacia con los requisitos habilitantes vigentes que correspondan a la sede de operación, alta responsabilidad, rigor documental y orientación al servicio.""",
        "profile": _profile(
            minimum_years_experience=1,
            responsibilities=("Gestión del servicio farmacéutico", "Control de inventarios y medicamentos", "Cumplimiento normativo"),
            domain_knowledge=("Servicio farmacéutico", "Medicamentos", "Buenas prácticas de almacenamiento"),
            education=("Tecnología en Regencia de Farmacia o título habilitante equivalente"),
            technical_competencies=("Trazabilidad", "Control de vencimientos", "Gestión documental"),
            assumptions_to_validate=("Validar inscripción, registro o requisitos habilitantes vigentes para la sede específica"),
        ),
    },
    {
        "title": "Coordinador Financiero",
        "aliases": ["COORDINADOR FINANCIERO"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Coordinar la operación financiera y asegurar información oportuna para tesorería, presupuesto, conciliaciones, pagos y control de gestión.

Responsabilidades principales
- Coordinar flujo de caja, pagos, recaudos y conciliaciones.
- Hacer seguimiento al presupuesto y explicar desviaciones.
- Preparar reportes financieros y operativos para la toma de decisiones.
- Asegurar controles, soportes y cierres oportunos.
- Articular requerimientos con contabilidad, operaciones, proveedores y dirección.

Perfil buscado
Profesional financiero con sólida capacidad analítica, orden, criterio de control y experiencia coordinando procesos y entregables financieros.""",
        "profile": _profile(
            minimum_years_experience=3,
            responsibilities=("Tesorería", "Presupuesto", "Conciliaciones", "Reportes financieros", "Control de gestión"),
            domain_knowledge=("Finanzas", "Contabilidad", "Tesorería"),
            education=("Profesional en Finanzas, Contaduría, Economía, Administración o áreas afines"),
            required_technologies=("Excel"),
            technical_competencies=("Análisis financiero", "Flujo de caja", "Presupuestos"),
        ),
    },
    {
        "title": "CCO",
        "aliases": ["CCO"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Liderar el frente ejecutivo asociado a crecimiento, estrategia comercial y desarrollo de relaciones de alto valor, conectando las prioridades de mercado con la capacidad operativa y financiera de la organización.

Responsabilidades principales
- Definir prioridades de crecimiento y objetivos comerciales.
- Liderar oportunidades, negociaciones y relaciones estratégicas.
- Gestionar pipeline, forecast, rentabilidad y desempeño comercial.
- Coordinar marketing, ventas, operaciones y dirección alrededor de las metas de crecimiento.
- Desarrollar modelos de seguimiento y toma de decisiones basados en datos.

Perfil buscado
Ejecutivo senior con trayectoria comercial, pensamiento estratégico, capacidad de negociación y experiencia liderando equipos y crecimiento en entornos B2B.""",
        "profile": _profile(
            minimum_years_experience=7,
            responsibilities=("Estrategia comercial", "Crecimiento", "Negociación estratégica", "Gestión de pipeline y forecast", "Liderazgo ejecutivo"),
            domain_knowledge=("Ventas B2B", "Estrategia comercial", "Desarrollo de negocios"),
            education=("Profesional en Administración, Ingeniería, Economía, Marketing o áreas afines"),
            technical_competencies=("Forecast comercial", "Gestión de P&L", "Negociación", "CRM"),
            assumptions_to_validate=("Confirmar la denominación y alcance corporativo exacto asociado al acrónimo CCO"),
        ),
    },
    {
        "title": "Cajeros",
        "aliases": ["CAJEROS"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Garantizar una atención ágil y confiable en el proceso de pago, asegurando exactitud en caja, buen servicio y cumplimiento de los procedimientos del punto.

Responsabilidades principales
- Registrar ventas y recibir diferentes medios de pago.
- Realizar apertura, cierre y arqueos de caja según procedimiento.
- Atender al cliente con agilidad, respeto y orientación al servicio.
- Reportar diferencias, novedades o incidentes de manera oportuna.
- Apoyar actividades operativas del punto cuando sea requerido.

Perfil buscado
Persona responsable, cuidadosa con el manejo de dinero, orientada al cliente y con disponibilidad para trabajar en los horarios definidos por la operación.""",
        "profile": _profile(
            minimum_years_experience=0,
            responsibilities=("Manejo de caja", "Procesamiento de pagos", "Servicio al cliente", "Arqueos"),
            domain_knowledge=("Operación de punto de venta",),
            education=("Bachiller; formación técnica es deseable"),
            technical_competencies=("Exactitud numérica", "Manejo de efectivo", "Servicio al cliente"),
        ),
    },
    {
        "title": "SAC (2)",
        "aliases": ["SAC (2)"],
        "country_code": "CO",
        "description": """Objetivo del cargo
Atender y gestionar solicitudes de clientes de forma clara, oportuna y resolutiva, asegurando trazabilidad y una experiencia consistente. Esta vacante contempla 2 posiciones.

Responsabilidades principales
- Recibir, registrar y gestionar solicitudes, consultas, novedades o reclamos.
- Hacer seguimiento a cada caso hasta su resolución o escalamiento.
- Mantener información completa y actualizada en las herramientas de seguimiento.
- Coordinar soluciones con las áreas responsables.
- Identificar causas recurrentes y oportunidades de mejora en la experiencia del cliente.

Perfil buscado
Persona orientada al servicio, empática, organizada y con comunicación escrita y verbal clara. Se valora experiencia en atención al cliente, mesas de servicio o canales de soporte.""",
        "profile": _profile(
            minimum_years_experience=1,
            responsibilities=("Atención al cliente", "Gestión y seguimiento de casos", "Escalamiento de novedades"),
            domain_knowledge=("Servicio al cliente", "Gestión de casos"),
            education=("Bachiller, técnico o tecnólogo; formación en servicio o áreas administrativas es deseable"),
            technical_competencies=("Comunicación", "Trazabilidad de casos", "Servicio al cliente"),
            assumptions_to_validate=("Confirmar el alcance operativo exacto asociado al acrónimo SAC"),
        ),
    },
]


def _resolve_owner_sub(db) -> str:
    for email in OWNER_EMAILS:
        profile = (
            db.query(UserProfile)
            .filter(UserProfile.email.ilike(email))
            .one_or_none()
        )
        if profile is not None and str(profile.cognito_sub or "").strip():
            return str(profile.cognito_sub).strip()

    existing = (
        db.query(Job.owner_sub)
        .filter(Job.owner_sub.isnot(None))
        .order_by(Job.created_at.desc())
        .first()
    )
    if existing and str(existing[0] or "").strip():
        return str(existing[0]).strip()

    raise RuntimeError("No recruiter owner_sub is available for vacancy creation.")


def seed_jobs(db) -> dict:
    owner_sub = _resolve_owner_sub(db)
    existing_jobs = db.query(Job).all()
    existing_by_title = {_norm(job.title): job for job in existing_jobs}

    created = []
    skipped = []
    failed = []

    for spec in JOBS:
        candidate_keys = {_norm(spec["title"])}
        candidate_keys.update(_norm(value) for value in spec.get("aliases", ()))
        found = next(
            (existing_by_title[key] for key in candidate_keys if key in existing_by_title),
            None,
        )
        if found is not None:
            skipped.append({"title": spec["title"], "job_id": found.id})
            continue

        try:
            now = datetime.now(timezone.utc)
            job = service.create_job(
                db,
                title=spec["title"],
                description=spec["description"],
                indeed_description=spec["description"],
                ai_description=spec["description"],
                active_description_source="ai",
                evaluation_profile=spec["profile"],
                owner_sub=owner_sub,
                status="ACTIVE",
                country_code=spec["country_code"],
                company_name=None,
                city=None,
                employment_type="FULL_TIME",
                response_time_business_days=2,
                phone_call_count=1,
                onsite_interview_count=1,
                offer_wait_days=4,
                offer_wait_reference="AFTER_INTERVIEW",
                public_slug=None,
                published_at=now,
            )
            existing_by_title[_norm(job.title)] = job
            created.append({
                "title": job.title,
                "job_id": job.id,
                "country_code": job.country_code,
            })
        except Exception as exc:
            db.rollback()
            failed.append({
                "title": spec["title"],
                "error": type(exc).__name__,
            })

    return {
        "status": "OK" if not failed else "PARTIAL",
        "requested": len(JOBS),
        "created": len(created),
        "skipped_existing": len(skipped),
        "failed": len(failed),
        "created_jobs": created,
        "skipped_jobs": skipped,
        "failures": failed,
    }


def main() -> None:
    with SessionLocal() as db:
        result = seed_jobs(db)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
