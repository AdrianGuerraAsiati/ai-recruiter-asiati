from __future__ import annotations

import os
import queue
import threading


def run_computrabajo_ui(*, browser, api_factory=None) -> None:
    """Candidate-only automatic synchronization using the separate browser session."""

    import tkinter as tk
    from tkinter import ttk
    from .computrabajo_sync import sync_all_candidates

    root = tk.Tk()
    root.title("ASIATI Recruiter Agent · Computrabajo")
    root.geometry("760x590")
    root.minsize(680, 440)
    root.configure(background="#F4F7FB")

    commands: queue.Queue[str] = queue.Queue()
    updates: queue.Queue[tuple[str, str]] = queue.Queue()
    stop_event = threading.Event()
    cancel_event = threading.Event()

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

    discover_button = ttk.Button(actions, text="Detectar candidatos de esta página", command=lambda: commands.put("discover"))
    discover_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(5, 0))

    logout_button = ttk.Button(actions, text="Cerrar sesión", command=lambda: commands.put("logout"))
    logout_button.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(5, 0))

    def confirm_sync() -> None:
        if api_factory is None:
            status_var.set("No hay conexión configurada con Talent.")
            return
        try:
            api = api_factory()
        except Exception:
            status_var.set("No se pudo obtener la credencial de Talent.")
            return
        cancel_event.clear()
        account = os.getenv("ASIATI_COMPUTRABAJO_SOURCE_ACCOUNT", "ASIATI").strip()
        commands.put(("sync_all", api, account))

    sync_button = ttk.Button(
        actions, text="Sincronizar todos los candidatos", command=confirm_sync,
    )
    sync_button.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(5, 0))

    cancel_button = ttk.Button(
        actions, text="Detener sincronización",
        command=lambda: cancel_event.set(), state="disabled",
    )
    cancel_button.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(5, 0))

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
            "Solo se importan candidatos. Las ofertas se consultan como navegación "
            "del portal, pero no se crean ni vinculan vacantes en Talent. "
            "Si la paginación no se puede verificar, la ejecución se informa como parcial."
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

            if isinstance(command, tuple) and command[0] == "sync_all":
                _, api, account = command
                updates.put(("busy", "Buscando candidatos en todas las páginas disponibles…"))
                try:
                    report = sync_all_candidates(
                        browser=browser, api=api, source_account=account,
                        stop_requested=lambda: stop_event.is_set() or cancel_event.is_set(),
                        discovery_progress=lambda stats: updates.put((
                            "busy", f"Explorando Computrabajo: {stats['pages']} páginas, "
                            f"{stats['offers_found']} listados y "
                            f"{stats['candidates_found']} candidatos detectados…"
                        )),
                        progress=lambda index, result: updates.put((
                            "busy", f"Procesados {index}/{result['total']} · "
                            f"{result['created']} nuevos, {result['existing']} existentes, "
                            f"{result['skipped']} ya sincronizados, "
                            f"{result['failed']} fallidos"
                        )),
                    )
                    status = "Atención: ejecución parcial" if (
                        report["partial"] or report["cancelled"] or report["failed"]
                    ) else "Sincronización completada"
                    error_counts = sorted(
                        report.get("error_counts", {}).items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                    details = ", ".join(
                        f"{code}: {count}" for code, count in error_counts[:3]
                    )
                    warning = (
                        f" Motivos: {details}." if details else ""
                    )
                    uncovered = report.get("unresolved_pagination", 0)
                    listings = report.get("offers_found", 0)
                    profiles = report.get("candidate_pages", 0)
                    coverage = (f" {listings} listados detectados, "
                                f"{profiles} páginas de aspirantes.")
                    coverage += (f" {uncovered} paginaciones sin confirmar."
                                 if uncovered else "")
                    blocked = report.get("blocked_pages", 0)
                    blocked_label = (
                        f" {blocked} páginas restringidas por Computrabajo."
                        if blocked else ""
                    )
                    updates.put(("ready", f"{status}. "
                        f"{report['pages']} páginas revisadas; "
                        f"{report['created']} nuevos, {report['existing']} existentes, "
                        f"{report['skipped']} omitidos y {report['failed']} errores."
                        + coverage + blocked_label + warning))
                except Exception as exc:
                    code = str(exc)
                    if code == "COMPUTRABAJO_OFFER_EXPIRED_ACCESS_DENIED":
                        message = ("Computrabajo restringe candidatos de ofertas vencidas. "
                                   "No se importaron CV de esas ofertas; consulta una publicación "
                                   "a la que tu cuenta tenga acceso.")
                    elif code in {"COMPUTRABAJO_LOGIN_OR_LIST_REQUIRED",
                                  "COMPUTRABAJO_NO_CANDIDATES_DISCOVERED"}:
                        message = ("No se encontraron candidatos accesibles. "
                                   "Confirma que has iniciado sesión y que la cuenta "
                                   "puede ver aspirantes.")
                    else:
                        message = ("Sincronización incompleta (" + type(exc).__name__ +
                                   "). Revisa el acceso a Computrabajo y Talent.")
                    updates.put(("error", message))
                finally:
                    api.close()
                continue

            if command == "logout":
                updates.put(("busy", "Cerrando sesión local de Computrabajo…"))
                try:
                    browser.logout()
                    updates.put(("ready", "Sesión local cerrada. Al abrir Computrabajo necesitarás iniciar sesión."))
                except Exception:
                    updates.put(("error", "No se pudo limpiar la sesión. Cierra el navegador y vuelve a intentarlo."))
                continue

            if command == "discover":
                updates.put(("busy", "Leyendo candidatos visibles en la página…"))
                try:
                    candidates = browser.discover_visible_candidates()
                    updates.put(("ready", f"Detectados {len(candidates)} candidatos en esta página. Sin envío a Talent todavía."))
                except Exception:
                    updates.put(("error", "Abre primero una página de candidatos de Computrabajo."))
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
                sync_button.configure(state="disabled" if busy else "normal")
                cancel_button.configure(state="normal" if busy else "disabled")
                logout_button.configure(state="disabled" if busy else "normal")
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
        cancel_event.set()
        stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(200, drain_updates)
    root.mainloop()
    stop_event.set()
    thread.join(timeout=2.0)
