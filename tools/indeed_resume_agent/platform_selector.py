from __future__ import annotations

import os
from collections.abc import Mapping

from .platforms import get_platform, normalize_platform, platform_labels


def select_platform(*, environ: Mapping[str, str] | None = None) -> str | None:
    """Select the recruiting provider before its runtime is initialized.

    ASIATI_RESUME_AGENT_PLATFORM can pin a provider for automated/local tests.
    Otherwise a small native selector is shown before any provider browser is
    started, keeping Indeed and Computrabajo sessions isolated by runtime.
    """

    env = os.environ if environ is None else environ
    configured = str(env.get("ASIATI_RESUME_AGENT_PLATFORM", "")).strip()
    if configured:
        return normalize_platform(configured)

    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("ASIATI Recruiter Agent")
    root.geometry("430x235")
    root.resizable(False, False)
    root.configure(background="#F4F7FB")

    result: dict[str, str | None] = {"platform": None}
    selected_label = tk.StringVar(value=get_platform("indeed").label)

    shell = tk.Frame(root, background="#F4F7FB", padx=28, pady=24)
    shell.pack(fill="both", expand=True)

    tk.Label(
        shell,
        text="ASIATI Recruiter Agent",
        background="#F4F7FB",
        foreground="#172033",
        font=("Segoe UI", 18, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        shell,
        text="Selecciona la plataforma de reclutamiento que vas a operar.",
        background="#F4F7FB",
        foreground="#667085",
        font=("Segoe UI", 9),
        anchor="w",
    ).pack(fill="x", pady=(4, 18))

    tk.Label(
        shell,
        text="PLATAFORMA",
        background="#F4F7FB",
        foreground="#667085",
        font=("Segoe UI", 8, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(0, 5))

    combo = ttk.Combobox(
        shell,
        textvariable=selected_label,
        values=platform_labels(),
        state="readonly",
        font=("Segoe UI", 10),
    )
    combo.pack(fill="x", ipady=5)

    def confirm() -> None:
        try:
            result["platform"] = normalize_platform(selected_label.get())
        except ValueError as exc:
            messagebox.showerror("ASIATI Recruiter Agent", str(exc), parent=root)
            return
        root.destroy()

    def cancel() -> None:
        result["platform"] = None
        root.destroy()

    button = tk.Button(
        shell,
        text="Continuar",
        command=confirm,
        background="#2457D6",
        foreground="#FFFFFF",
        activebackground="#1E4EBB",
        activeforeground="#FFFFFF",
        relief="flat",
        bd=0,
        font=("Segoe UI", 9, "bold"),
        padx=16,
        pady=9,
        cursor="hand2",
    )
    button.pack(fill="x", pady=(18, 0))

    root.protocol("WM_DELETE_WINDOW", cancel)
    root.bind("<Return>", lambda _event: confirm())
    root.after_idle(combo.focus_set)
    root.mainloop()
    return result["platform"]
