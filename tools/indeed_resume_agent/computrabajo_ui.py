from __future__ import annotations

import queue
import threading


def run_computrabajo_ui(*, browser) -> None:
    """Computrabajo shell kept separate from the production Indeed workflow.

    The browser/session boundary is ready now. Automatic candidate and vacancy
    collectors stay disabled until we validate the authenticated Computrabajo
    DOM and add provider-specific contracts/tests instead of guessing selectors.
    """

    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("ASIATI Recruiter Agent · Computrabajo")
    root.geometry("760x520")
    root.minsize(680, 440)
    root.configure(background="#F4F7FB")

    commands: queue.Queue[str] = queue.Queue()
    updates: queue.Queue[tuple[str, str]] = queue.Queue()
    stop_event = threading.Event()

    shell = tk.Frame(root, background="#F4F7FB", padx=24, pady=22)
    shell.pack(fill="both", expand=True)

    tk.Label(
        shell,
        text="ASIATI Recruiter Agent",
        background="#F4F7FB",
        foreground="#172033",
        font=("Segoe UI", 19, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        shell,
        text="Computrabajo · candidatos y CVs",
        background="#F4F7FB",
        foreground="#667085",
        font=("Segoe UI", 9),
        anchor="w",
    ).pack(fill="x", pady=(2, 14))

    provider = tk.Frame(
        shell,
        background="#FFFFFF",
        highlightthickness=1,
        highlightbackground="#D7DFEA",
        padx=14,
        pady=11,
    )
    provider.pack(fill="x", pady=(0, 10))
    tk.Label(
        provider,
        text="PLATAFORMA ACTIVA",
        background="#FFFFFF",
        foreground="#667085",
        font=("Segoe UI", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        provider,
        text="Computrabajo",
        background="#FFFFFF",
        foreground="#172033",
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(2, 0))

    status_var = tk.StringVar(value="Sesión lista para abrir Computrabajo.")
    status = tk.Frame(
        shell,
        background="#EEF4FF",
        highlightthickness=1,
        highlightbackground="#B2CCFF",
        padx=14,
        pady=11,
    )
    status.pack(fill="x", pady=(0, 10))
    tk.Label(
        status,
        text="ESTADO ACTUAL",
        background="#EEF4FF",
        foreground="#2457D6",
        font=("Segoe UI", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        status,
        textvariable=status_var,
        background="#EEF4FF",
        foreground="#172033",
        font=("Segoe UI", 9),
        justify="left",
        wraplength=680,
        anchor="w",
    ).pack(fill="x", pady=(3, 0))

    actions = ttk.LabelFrame(shell, text="Operación", padding=12)
    actions.pack(fill="x", pady=(0, 10))
    actions.columnconfigure(0, weight=1)
    actions.columnconfigure(1, weight=1)
    actions.columnconfigure(2, weight=1)

    open_button = ttk.Button(
        actions,
        text=f"Abrir Computrabajo ({browser.browser_label})",
        command=lambda: commands.put("open"),
    )
    open_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=4)

    diagnostic_start_button = ttk.Button(
        actions,
        text="Iniciar diagnóstico",
        command=lambda: commands.put("diagnostic_start"),
    )
    diagnostic_start_button.grid(
        row=0,
        column=1,
        sticky="ew",
        padx=5,
        pady=4,
    )

    diagnostic_stop_button = ttk.Button(
        actions,
        text="Guardar diagnóstico",
        command=lambda: commands.put("diagnostic_stop"),
        state="disabled",
    )
    diagnostic_stop_button.grid(
        row=0,
        column=2,
        sticky="ew",
        padx=(5, 0),
        pady=4,
    )

    inspect_button = ttk.Button(actions, text="Analizar pantalla actual", command=lambda: commands.put("inspect"))
    inspect_button.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 0))

    pdf_button = ttk.Button(actions, text="Guardar perfil abierto como PDF", command=lambda: commands.put("profile_pdf"))
    pdf_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(5, 0))

    discover_button = ttk.Button(actions, text="Detectar candidatos de esta vacante", command=lambda: commands.put("discover"))
    discover_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(5, 0))

    sync_button = ttk.Button(
        actions,
        text="Sincronizar candidatos",
        state="disabled",
    )
    sync_button.grid(
        row=2,
        column=0,
        columnspan=3,
        sticky="ew",
        pady=(5, 0),
    )

    note = tk.Frame(
        shell,
        background="#FFFAEB",
        highlightthickness=1,
        highlightbackground="#FEDF89",
        padx=14,
        pady=11,
    )
    note.pack(fill="x")
    tk.Label(
        note,
        text="SIGUIENTE CAPA",
        background="#FFFAEB",
        foreground="#B54708",
        font=("Segoe UI", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        note,
        text=(
            "Computrabajo ya usa una sesión de navegador separada de Indeed. "
            "La sincronización automática permanece bloqueada hasta validar el DOM "
            "autenticado y definir selectores propios de vacantes, candidatos y "
            "descarga de CV."
        ),
        background="#FFFAEB",
        foreground="#475467",
        font=("Segoe UI", 9),
        justify="left",
        wraplength=680,
        anchor="w",
    ).pack(fill="x", pady=(3, 0))

    def worker_loop() -> None:
        while not stop_event.is_set():
            try:
                command = commands.get(timeout=0.2)
            except queue.Empty:
                continue

            if command == "discover":
                updates.put(("busy", "Leyendo candidatos visibles de la vacante…"))
                try:
                    candidates = browser.discover_visible_candidates()
                    updates.put(("ready", f"Detectados {len(candidates)} candidatos en esta página. Sin envío a Talent todavía."))
                except Exception:
                    updates.put(("error", "Abre primero el listado de candidatos de una vacante."))
                continue

            if command == "profile_pdf":
                try:
                    path = browser.save_visible_profile_pdf()
                    updates.put(("ready", "PDF guardado localmente: " + path))
                except Exception:
                    updates.put(("error", "Abre el detalle de un candidato antes de guardar su perfil como PDF."))
                continue

            if command == "inspect":
                try:
                    info = browser.inspect_current_page()
                    updates.put(("ready", str(info)))
                except Exception:
                    updates.put(("error", "No se pudo analizar la pantalla."))
                continue

            if command == "open":
                updates.put(
                    (
                        "busy",
                        "Abriendo la sesión persistente de Computrabajo…",
                    )
                )
                try:
                    browser.open_portal()
                except Exception:
                    updates.put(
                        (
                            "error",
                            "No fue posible abrir Computrabajo. Revisa "
                            "Chrome/Edge y vuelve a intentar.",
                        )
                    )
                else:
                    updates.put(
                        (
                            "ready",
                            "Computrabajo está abierto. Inicia sesión "
                            "manualmente en la ventana del navegador.",
                        )
                    )
                continue

            if command == "diagnostic_start":
                updates.put(
                    (
                        "diagnostic_busy",
                        "Iniciando diagnóstico de Computrabajo…",
                    )
                )
                try:
                    browser.start_diagnostic()
                except Exception:
                    updates.put(
                        (
                            "error",
                            "No fue posible iniciar el diagnóstico de "
                            "Computrabajo.",
                        )
                    )
                else:
                    updates.put(
                        (
                            "diagnostic",
                            "Diagnóstico activo. Navega normalmente por "
                            "vacantes y candidatos; al terminar pulsa "
                            "Guardar diagnóstico.",
                        )
                    )
                continue

            if command == "diagnostic_stop":
                updates.put(
                    (
                        "diagnostic_busy",
                        "Guardando diagnóstico local…",
                    )
                )
                try:
                    path = browser.stop_diagnostic()
                except Exception:
                    path = None
                if path:
                    updates.put(
                        (
                            "ready",
                            f"Diagnóstico guardado: {path}",
                        )
                    )
                else:
                    updates.put(
                        (
                            "error",
                            "No fue posible guardar el diagnóstico de "
                            "Computrabajo.",
                        )
                    )

    thread = threading.Thread(
        target=worker_loop,
        name="asiati-computrabajo-ui",
        daemon=True,
    )
    thread.start()

    def drain_updates() -> None:
        try:
            while True:
                state, message = updates.get_nowait()
                status_var.set(message)
                busy = state in {"busy", "diagnostic_busy"}
                discover_button.configure(state="disabled" if busy else "normal")
                open_button.configure(
                    state="disabled" if busy else "normal"
                )
                diagnostic_start_button.configure(
                    state=(
                        "disabled"
                        if busy or state == "diagnostic"
                        else "normal"
                    )
                )
                diagnostic_stop_button.configure(
                    state="normal" if state == "diagnostic" else "disabled"
                )
        except queue.Empty:
            pass
        if not stop_event.is_set():
            root.after(200, drain_updates)

    def on_close() -> None:
        stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(200, drain_updates)
    root.mainloop()
    stop_event.set()
    thread.join(timeout=2.0)
