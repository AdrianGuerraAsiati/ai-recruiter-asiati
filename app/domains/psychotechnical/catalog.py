"""Versioned ASIATI psychotechnical catalog.

The source material for this catalog is the internal ASIATI psychotechnical pack:
- GTH-F-016 Prueba Sentido Común, versión 00 (2025-06-05)
- GTH-F-017 Prueba de Temperamento, versión 00 (2025-06-05)
- Prueba de Atención al Detalle, versión 00 (2025-05-27)
- Cuestionario VALANTI + workbook de resultados suministrado por ASIATI

Results are descriptive and advisory. They must not automatically reject, select,
rank, or recommend candidates.
"""

from __future__ import annotations


COMMON_SENSE = "COMMON_SENSE_GTH_F016"
TEMPERAMENT = "TEMPERAMENT_GTH_F017"
VALANTI = "VALANTI_ASIATI"
ATTENTION = "ATTENTION_DETAIL_V00"

DEFAULT_TEST_KEY = COMMON_SENSE


def _option(option_id: str, label: str) -> dict:
    return {"id": option_id, "label": label}


COMMON_SENSE_QUESTIONS = [
    {
        "id": "SC01",
        "prompt": "Estás en recepción y llega una persona que dice ser amigo del gerente, pero no tiene cita agendada ni se ha identificado formalmente. ¿Qué haces?",
        "options": [
            _option("A", "Le permites el ingreso para evitar que se moleste."),
            _option("B", "Le indicas que debe agendar una cita previa."),
            _option("C", "Verificas con el área correspondiente o con el gerente si puede ingresar."),
            _option("D", "Lo dejas entrar y anotas y haces el debido registro."),
        ],
        "correct": "C",
    },
    {
        "id": "SC02",
        "prompt": "Te entregan información confidencial por error. No está dirigida a ti, pero sabes que es delicada. ¿Qué haces?",
        "options": [
            _option("A", "La reenvías a tus compañeros para preguntar qué hacer."),
            _option("B", "La borras sin decir nada."),
            _option("C", "Informas a tu jefe directo o al remitente."),
            _option("D", "La conservas por si te sirve en el futuro."),
        ],
        "correct": "C",
    },
    {
        "id": "SC03",
        "prompt": "Un compañero deja la impresora dañada y no avisa. Te das cuenta porque la necesitas. ¿Qué haces?",
        "options": [
            _option("A", "Lo comentas por el grupo de trabajo."),
            _option("B", "Lo ignoras, no es tu responsabilidad."),
            _option("C", "Reportas el daño al área correspondiente e informas que no funciona."),
            _option("D", "La arreglas tú y cooperas con la organización."),
        ],
        "correct": "C",
    },
    {
        "id": "SC04",
        "prompt": "Recibes una orden urgente de tu jefe que implica un cambio temporal en tus funciones. ¿Qué haces?",
        "options": [
            _option("A", "La rechazas porque no está en tu contrato."),
            _option("B", "Aceptas con disposición mientras lo comunicas formalmente."),
            _option("C", "Solo la cumples si te dan algo a cambio."),
            _option("D", "La haces, pero de mala gana y sin compromiso."),
        ],
        "correct": "B",
    },
    {
        "id": "SC05",
        "prompt": "Sabes que un compañero está cometiendo una falta grave que puede afectar a la empresa. ¿Qué haces?",
        "options": [
            _option("A", "Lo enfrentas directamente y evitas que cometa el daño."),
            _option("B", "No haces nada para evitar conflictos."),
            _option("C", "Informas de forma confidencial al área responsable o a tu superior inmediato."),
            _option("D", "Esperas a que alguien más lo reporte."),
        ],
        "correct": "C",
    },
    {
        "id": "SC06",
        "prompt": "Notas que una compañera está enviando mensajes ofensivos por el chat interno. ¿Qué haces?",
        "options": [
            _option("A", "La confrontas."),
            _option("B", "Haces captura de pantalla y la compartes con otros compañeros."),
            _option("C", "Informas de manera confidencial al área de Talento Humano o a tu jefe directo."),
            _option("D", "Ignoras la situación para no involucrarte."),
        ],
        "correct": "C",
    },
    {
        "id": "SC07",
        "prompt": "Llega una factura de proveedor duplicada por error. Nadie más parece notarlo. ¿Qué haces?",
        "options": [
            _option("A", "Apruebas la factura para evitar atrasos."),
            _option("B", "La ignoras y dejas que alguien más lo descubra."),
            _option("C", "Verificas con el proveedor y reportas el hallazgo a tu jefe."),
            _option("D", "Guardas la factura duplicada por si se necesita."),
        ],
        "correct": "C",
    },
    {
        "id": "SC08",
        "prompt": "Tienes una reunión virtual, pero hay ruido fuerte en tu entorno. ¿Qué haces?",
        "options": [
            _option("A", "Entras normalmente y te excusas por el ruido."),
            _option("B", "Cancelas la reunión."),
            _option("C", "Usas audífonos y silencias el micrófono cuando no hablas."),
            _option("D", "Entras a la reunión sin preocuparte por el ruido."),
        ],
        "correct": "C",
    },
    {
        "id": "SC09",
        "prompt": "Te asignan una tarea urgente fuera de tu horario laboral. ¿Qué haces?",
        "options": [
            _option("A", "La rechazas sin explicación."),
            _option("B", "La haces si te pagan extra."),
            _option("C", "Evalúas la urgencia y, si es crítica, la asumes con comunicación clara."),
            _option("D", "Esperas a que otro la tome."),
        ],
        "correct": "C",
    },
    {
        "id": "SC10",
        "prompt": "Un cliente importante solicita algo que no está en tu alcance. ¿Qué haces?",
        "options": [
            _option("A", "Le prometes que lo resolverás."),
            _option("B", "Lo ignoras para evitar quedar mal."),
            _option("C", "Le explicas con respeto y escalas la solicitud al área correspondiente."),
            _option("D", "Le dices que no es tu problema."),
        ],
        "correct": "C",
    },
]


TEMPERAMENT_PROMPTS = [
    ("Cuando enfrento un problema complejo en el trabajo, suelo:", "Buscar una solución inmediata, aunque no sea perfecta.", "Consultar con el equipo antes de actuar.", "Analizar todas las variables antes de decidir.", "Esperar indicaciones antes de actuar."),
    ("En una reunión con muchas personas desconocidas, tiendo a:", "Tomar la palabra y liderar la conversación.", "Observar y hablar sólo si me preguntan.", "Mantener una actitud neutral y colaborativa.", "Sentirme incómodo y evitar participar."),
    ("Si tengo que entregar un proyecto urgente, yo:", "Trabajo intensamente hasta terminarlo, incluso si no es perfecto.", "Pido ayuda a colegas para dividir tareas.", "Planifico meticulosamente para no cometer errores.", "Me esfuerzo pero me distraigo con facilidad."),
    ("Cuando alguien me critica en el trabajo, yo:", "Contesto rápidamente defendiendo mi punto.", "Escucho pero no respondo mucho.", "Reflexiono antes de responder.", "Me lo tomo muy personal y me afecta."),
    ("Prefiero trabajar en ambientes que son:", "Desafiantes y con decisiones rápidas.", "Estables y sin conflictos.", "Organizados y meticulosos.", "Sociales y dinámicos."),
    ("Cuando empiezo un nuevo proyecto, suelo:", "Tomar el liderazgo desde el inicio.", "Integrarme al ritmo del grupo.", "Estudiar bien todos los detalles antes de actuar.", "Entusiasmarme mucho al principio, pero perder interés con el tiempo."),
    ("Si tengo que cambiar mis planes de trabajo repentinamente, yo:", "Me frustro pero intento adaptarme rápido.", "Me adapto sin mucho problema.", "Me incomoda y me cuesta cambiar de enfoque.", "Lo tomo como algo emocionante."),
    ("Durante una jornada intensa, yo:", "Mantengo mi nivel de energía y decisión.", "Prefiero un ritmo constante sin presión.", "Me fatigo si no hay estructura.", "Me distraigo con facilidad."),
    ("Cuando hay conflictos en el equipo, yo:", "Enfrento directamente el problema.", "Busco mantener la paz evitando confrontaciones.", "Trato de entender el origen con lógica.", "Me altero emocionalmente."),
    ("Si tengo que explicar una idea compleja, yo:", "Uso ejemplos prácticos y rápidos.", "Simplifico para que nadie se sienta excluido.", "Organizo bien los puntos antes de hablar.", "Improviso según el momento."),
    ("Cuando tengo que trabajar bajo presión, suelo:", "Tomar el control del equipo para cumplir los plazos.", "Mantenerme sereno y seguir el proceso habitual.", "Reorganizar mis tareas meticulosamente.", "Buscar apoyo emocional en mis compañeros."),
    ("Ante un nuevo reto profesional, mi primera reacción es:", "Aceptarlo de inmediato como una oportunidad.", "Considerar si tengo el apoyo necesario.", "Evaluar riesgos y planificar antes de actuar.", "Entusiasmarme pero distraerme con facilidad."),
    ("En una discusión laboral, yo suelo:", "Defender mi punto con firmeza.", "Tratar de calmar a las partes.", "Escuchar y responder con lógica.", "Evitar el conflicto y cambiar de tema."),
    ("Prefiero tareas que requieren:", "Acción inmediata y toma de decisiones.", "Coordinación con otros sin urgencia.", "Análisis profundo y precisión.", "Creatividad y contacto social."),
    ("Cuando recibo instrucciones poco claras, yo:", "Actúo según mi criterio.", "Espero a que alguien más lo aclare.", "Pregunto detalles antes de empezar.", "Me preocupo y me siento inseguro."),
    ("Al presentar una idea ante líderes, yo:", "Soy directo y seguro.", "Me ajusto al grupo y no sobresalgo.", "Me preparo a fondo con datos y argumentos.", "Improviso y apelo al carisma."),
    ("Si algo cambia en el equipo de trabajo, yo:", "Reorganizo de inmediato para mantener el ritmo.", "Me adapto sin grandes reacciones.", "Necesito tiempo para ajustar mi planificación.", "Me siento motivado por la novedad."),
    ("Cuando una tarea requiere mucha atención al detalle, yo:", "La cumplo rápido aunque no esté perfecta.", "Pido apoyo para no equivocarme.", "Me enfoco completamente hasta que quede perfecta.", "Me cuesta mantener la concentración por mucho tiempo."),
    ("Si un colega comete un error, yo:", "Lo señalo inmediatamente para corregirlo.", "Le ofrezco ayuda con discreción.", "Analizo la causa antes de opinar.", "Lo defiendo frente a otros para no crear tensión."),
    ("Mi ritmo de trabajo habitual es:", "Rápido y orientado a resultados.", "Constante y sin presiones.", "Lento pero muy preciso.", "Cambiante según el ambiente y el ánimo."),
    ("Cuando tengo libertad total para decidir, yo:", "Actúo con rapidez y asumo consecuencias.", "Prefiero consensuar con otros antes.", "Elaboro un plan detallado antes de actuar.", "Me cuesta decidir por temor a equivocarme."),
    ("En un entorno laboral competitivo, yo:", "Trato de destacar y ser el mejor.", "Me mantengo al margen sin presión.", "Compito sólo si tengo los recursos suficientes.", "Me siento incómodo y prefiero ambientes más sociales."),
    ("Cuando alguien necesita ayuda, yo:", "Ayudo si no interfiere con mis objetivos.", "Siempre colaboro aunque no me lo pidan.", "Evalúo si puedo ayudar sin comprometer mi trabajo.", "Me involucro emocionalmente en su problema."),
    ("En mi tiempo libre, prefiero actividades:", "Desafiantes y energéticas.", "Tranquilas y rutinarias.", "Estructuradas y formativas.", "Divertidas y sociales."),
    ("Cuando estoy liderando un proyecto, yo:", "Me enfoco en resultados y eficiencia.", "Mantengo al grupo cohesionado.", "Verifico cada paso para asegurar calidad.", "Motivo al equipo con entusiasmo."),
    ("Mi mayor fortaleza en el trabajo es:", "Mi capacidad de tomar decisiones.", "Mi paciencia y cooperación.", "Mi precisión y planificación.", "Mi energía y simpatía."),
    ("Si alguien cuestiona mi forma de trabajar, yo:", "Me defiendo con argumentos.", "Acepto la crítica sin reaccionar.", "Analizo si tiene razón antes de responder.", "Me molesto y me afecta."),
    ("Para resolver un conflicto interpersonal, yo:", "Tomo una posición clara y directa.", "Busco que todos estén de acuerdo.", "Escucho y propongo una solución racional.", "Me alejo del conflicto para no involucrarme."),
    ("Cuando inicio una nueva actividad laboral, yo:", "Me lanzo con decisión.", "Me adapto a lo que otros hacen.", "Necesito entender cada parte antes de comenzar.", "Me entusiasmo pero pierdo enfoque."),
    ("Si mi jefe me da una tarea difícil, yo:", "Asumo el reto con determinación.", "Busco apoyo para entender mejor.", "Planifico paso a paso para ejecutarla bien.", "Me preocupo pero la enfrento con entusiasmo."),
]

TEMPERAMENT_QUESTIONS = [
    {
        "id": f"TP{index:02d}",
        "prompt": prompt,
        "options": [
            _option("A", a),
            _option("B", b),
            _option("C", c),
            _option("D", d),
        ],
    }
    for index, (prompt, a, b, c, d) in enumerate(TEMPERAMENT_PROMPTS, start=1)
]


VALANTI_PAIRS = [
    ("Muestro dedicación a las personas que amo", "Actúo con perseverancia"),
    ("Soy tolerante", "Prefiero actuar con ética"),
    ('Al pensar, utilizo mi intuición o "sexto sentido"', "Me siento una persona digna"),
    ("Logro buena concentración mental", "Perdono todas las ofensas de cualquier persona"),
    ("Normalmente razono mucho", "Me destaco por el liderazgo en mis acciones"),
    ("Pienso con integridad", "Me coloco objetivos y metas en mi vida personal"),
    ("Soy una persona de iniciativa", "En mi trabajo normalmente soy curioso"),
    ("Doy amor", "Para pensar hago síntesis de las distintas ideas"),
    ("Me siento en calma", "Pienso con veracidad"),
    ("Irrespetar la propiedad", "Sentir inquietud"),
    ("Ser irresponsable", "Ser desconsiderado hacia cualquier persona"),
    ("Caer en contradicciones al pensar", "Sentir intolerancia"),
    ("Ser violento", "Actuar con cobardía"),
    ("Sentirse presumido", "Generar divisiones y discordia entre los seres humanos"),
    ("Ser cruel", "Sentir ira"),
    ("Pensar con confusión", "Tener odio en el corazón"),
    ("Decir blasfemias", "Ser escandaloso"),
    ("Crear desigualdades entre los seres humanos", "Apasionarse por una idea"),
    ("Sentirse inconstante", "Crear rivalidad hacia otros"),
    ("Pensamientos irracionales", "Traicionar a un desconocido"),
    ("Ostentar las riquezas materiales", "Sentirse infeliz"),
    ("Entorpecer la cooperación entre los seres humanos", "La maldad"),
    ("Odiar a cualquier ser de la naturaleza", "Hacer distinciones entre las personas"),
    ("Sentirse intranquilo", "Ser infiel"),
    ("Tener la mente dispersa", "Mostrar apatía al pensar"),
    ("La injusticia", "Sentirse angustiado"),
    ("Vengarse de los que odian a todo el mundo", "Vengarse del que hace daño a un familiar"),
    ("Usar abusivamente el poder", "Distraerse"),
    ("Ser desagradecido con los que ayudan", "Ser egoísta con todos"),
    ("Cualquier forma de irrespeto", "Odiar"),
]

VALANTI_QUESTIONS = [
    {
        "id": f"VA{index:02d}",
        "kind": "paired_allocation",
        "part": 1 if index <= 9 else 2,
        "left": left,
        "right": right,
        "options": [
            _option("3-0", "3 - 0"),
            _option("0-3", "0 - 3"),
            _option("2-1", "2 - 1"),
            _option("1-2", "1 - 2"),
        ],
    }
    for index, (left, right) in enumerate(VALANTI_PAIRS, start=1)
]


ATTENTION_ALPHANUMERIC = [
    ("A09RT3", ["A09PT3", "A90RT3", "A09RT3", "A09TR3"]),
    ("HT83T7", ["HT88T7", "HF8ET7", "HT8ET7", "HT83T7"]),
    ("S8GT89", ["S3GT89", "S8GT89", "S8DT89", "S8GT39"]),
    ("DT896S", ["DT396S", "DT869S", "DL896S", "DT896S"]),
    ("IL31T2", ["IL31T2", "IL31L2", "IL3LT2", "IL13T2"]),
    ("KI3841", ["KI384I", "KI4831", "KI3841", "K1384I"]),
    ("34GJ76", ["34GL76", "34GJ67", "34JG76", "34GJ76"]),
    ("Z89RL3", ["Z89RL3", "Z39RL3", "Z89LR3", "Z89RLE"]),
    ("LII8T3", ["L1I8T3", "L1I3T3", "LI18T3", "LII8T3"]),
    ("S383TI", ["S833TI", "S388TI", "S383TI", "S383TL"]),
    ("DT886I", ["DI8861", "DT889I", "DT886I", "DT896I"]),
    ("IJ32P2", ["IJ32P2", "IJ31P2", "IL2LP2", "IJI3PI2"]),
    ("PI338I", ["PI383I", "PI838I", "PI3381", "PI338I"]),
    ("JKGJ76", ["JKGL75", "JKGJ67", "JKG7J6", "JKGJ76"]),
    ("P86IL3", ["P86IL8", "P36IL3", "P86IL3", "P96IL3"]),
    ("L11ST1", ["L1IST1", "L1S1T1", "L1TS11", "L11ST1"]),
    ("T1TSTI", ["T1TSIT", "T1TSTI", "TITSTI", "T1TSTI"]),
    ("2091II", ["209I1I", "209I11", "2901II", "2091II"]),
    ("KLJIP2", ["KLJ1P2", "KLJ1P2", "KL1IP2", "KLJIP2"]),
    ("TI31II", ["TI31II", "T031I", "TI01II", "T13I1"]),
]

ATTENTION_LETTERS = [
    ("pymtcqoxaq", "pygtcqoxaq"),
    ("edfhpatnmd", "edfhpatnmd"),
    ("wybhqcfbai", "wybhqcfbai"),
    ("hvmbplocfd", "hvmbpldcfd"),
    ("zkgxitvlkd", "zkgxitvlkk"),
    ("mxywssazjl", "mxywssazjl"),
    ("nctfmjifgu", "nctrmjifgu"),
    ("mbldwefmif", "mbldwefmif"),
    ("pnqtvlpgwn", "ptqtvlpgwn"),
    ("ottwyoebpw", "ottwyoebpw"),
    ("ktczfijsxf", "ktczfitsxf"),
    ("ejdhhdzbez", "ejdhhdobez"),
    ("hpthmlfcsk", "hpthmifcsk"),
    ("zdxszmwhni", "zdxhzmwhni"),
    ("alqslnmchc", "alqslnmcqc"),
    ("dqtatuxkiu", "dqtatuxkiu"),
    ("evnkhjfidy", "evnkhjfify"),
    ("bhlpequjcq", "bhlpeqnjcq"),
    ("grwskjuvmm", "grwskjuvmm"),
    ("ajpuoymscp", "ajpuoymscp"),
    ("ddnyaitavy", "ddnyaitavy"),
    ("cqbrafbxgk", "cqcrafbxgk"),
    ("ihfbmbpafm", "ihfbmbpafm"),
    ("ffrdxpsdme", "ffrexpsdme"),
    ("cdnjipebjq", "cdnjipebbq"),
]

# The paper instrument uses silhouette rows. For screen delivery this stage uses
# compact visual strings with the same task: identify the exact match.
ATTENTION_FIGURES = [
    ("◀◆○◆", ["◀◆○◇", "◀◆○◆", "◀◇○◆", "◆◀○◆"]),
    ("△●□▲", ["△●□▲", "△○□▲", "▲●□△", "△●■▲"]),
    ("○◇◇●", ["○◇◆●", "○◇◇●", "○◆◇●", "●◇◇○"]),
    ("⇢⇢↗⇢", ["⇢⇢↗⇢", "⇢↗⇢⇢", "⇢⇢↘⇢", "↗⇢⇢⇢"]),
    ("⌁△⌁○", ["⌁△⌁●", "⌁△⌁○", "⌁▽⌁○", "○△⌁⌁"]),
    ("▲│▼│", ["▲│▼│", "▲┃▼│", "▼│▲│", "▲│▽│"]),
    ("♞◇♞○", ["♞◇♘○", "♞◇♞○", "♞◆♞○", "○◇♞♞"]),
]


def _attention_questions() -> list[dict]:
    questions = []
    for index, (target, options) in enumerate(ATTENTION_ALPHANUMERIC, start=1):
        questions.append(
            {
                "id": f"AT-A{index:02d}",
                "kind": "single_choice",
                "section": "ALPHANUMERIC",
                "section_label": "Alfanumérico",
                "target": target,
                "prompt": f"Selecciona el código idéntico a {target}.",
                "options": [
                    _option(chr(65 + option_index), label)
                    for option_index, label in enumerate(options)
                ],
                "correct": chr(65 + options.index(target)),
            }
        )

    for index, (left, right) in enumerate(ATTENTION_LETTERS, start=1):
        questions.append(
            {
                "id": f"AT-L{index:02d}",
                "kind": "single_choice",
                "section": "LETTERS",
                "section_label": "Letras",
                "target": f"{left}  /  {right}",
                "prompt": "¿Las dos cadenas son exactamente iguales?",
                "options": [
                    _option("0", "0 · Iguales"),
                    _option("1", "1 · Diferentes"),
                ],
                "correct": "0" if left == right else "1",
            }
        )

    for index, (target, options) in enumerate(ATTENTION_FIGURES, start=1):
        questions.append(
            {
                "id": f"AT-F{index:02d}",
                "kind": "single_choice",
                "section": "FIGURES",
                "section_label": "Figuras · versión digital",
                "target": target,
                "prompt": f"Selecciona la figura idéntica a {target}.",
                "options": [
                    _option(chr(65 + option_index), label)
                    for option_index, label in enumerate(options)
                ],
                "correct": chr(65 + options.index(target)),
            }
        )
    return questions


ATTENTION_QUESTIONS = _attention_questions()


TESTS = {
    COMMON_SENSE: {
        "key": COMMON_SENSE,
        "name": "Sentido común organizacional",
        "code": "GTH-F-016",
        "source_version": "00",
        "kind": "single_choice",
        "question_count": len(COMMON_SENSE_QUESTIONS),
        "duration_minutes": 12,
        "description": "Situaciones laborales para observar criterio organizacional y responsabilidad.",
        "questions": COMMON_SENSE_QUESTIONS,
    },
    TEMPERAMENT: {
        "key": TEMPERAMENT,
        "name": "Temperamento laboral",
        "code": "GTH-F-017",
        "source_version": "00",
        "kind": "single_choice_profile",
        "question_count": len(TEMPERAMENT_QUESTIONS),
        "duration_minutes": 18,
        "description": "Cuestionario descriptivo de estilos laborales basado en el formato interno GTH-F-017.",
        "questions": TEMPERAMENT_QUESTIONS,
    },
    VALANTI: {
        "key": VALANTI,
        "name": "VALANTI",
        "code": "VALANTI",
        "source_version": "ASIATI",
        "kind": "paired_allocation",
        "question_count": len(VALANTI_QUESTIONS),
        "duration_minutes": 20,
        "description": "Cuestionario de valores. Cada par distribuye tres puntos entre dos frases.",
        "questions": VALANTI_QUESTIONS,
    },
    ATTENTION: {
        "key": ATTENTION,
        "name": "Atención al detalle",
        "code": "ATENCIÓN-DETALLE",
        "source_version": "00",
        "kind": "timed_attention",
        "question_count": len(ATTENTION_QUESTIONS),
        "duration_minutes": 8,
        "duration_seconds": 440,
        "description": "Versión digital basada en las tres tareas ASIATI: alfanumérico, letras y figuras.",
        "questions": ATTENTION_QUESTIONS,
    },
}


def require_test(test_key: str) -> dict:
    test = TESTS.get(str(test_key or "").strip())
    if test is None:
        raise KeyError(test_key)
    return test


def catalog_payload() -> list[dict]:
    return [
        {
            "key": test["key"],
            "name": test["name"],
            "code": test["code"],
            "source_version": test["source_version"],
            "kind": test["kind"],
            "question_count": test["question_count"],
            "duration_minutes": test["duration_minutes"],
            "description": test["description"],
        }
        for test in TESTS.values()
    ]


def public_questions(test_key: str) -> list[dict]:
    test = require_test(test_key)
    public = []
    for question in test["questions"]:
        item = {
            key: value
            for key, value in question.items()
            if key not in {"correct"}
        }
        public.append(item)
    return public
