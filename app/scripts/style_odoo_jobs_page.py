"""Apply the ASIATI visual treatment to Odoo's public recruitment page."""

from __future__ import annotations

import json

from app.domains.odoo_sync import integration
from app.integrations.odoo.client import OdooClientError


VIEW_KEY = "asiati_talent.jobs_modern"
BASE_VIEW_KEY = "website_hr_recruitment.index"
VIEW_NAME = "ASIATI Talent · Jobs modern layout"

STYLE_ARCH = r"""
<data>
    <xpath expr="//div[@id='wrap']" position="inside">
        <style id="asiati-talent-jobs-modern-css" type="text/css">
            .o_website_hr_recruitment_jobs_list {
                --asiati-navy: #0f3d56;
                --asiati-teal: #126d78;
                --asiati-yellow: #f4df00;
                --asiati-ink: #152238;
                --asiati-muted: #607086;
                --asiati-surface: #ffffff;
                --asiati-soft: #f5f8fa;
                background: linear-gradient(180deg, #ffffff 0%, #f7f9fb 24%, #f4f7f9 100%);
            }

            .o_website_hr_recruitment_jobs_list .oe_website_jobs {
                max-width: 1240px;
                padding-top: 1rem;
                padding-bottom: 2.5rem;
            }

            .o_website_hr_recruitment_jobs_list .o_wevent_index_topbar_filters {
                gap: .85rem;
                padding: 1rem 1.1rem;
                margin-top: 1.4rem !important;
                margin-bottom: 1.35rem !important;
                border: 1px solid rgba(15, 61, 86, .10);
                border-radius: 18px;
                background: rgba(255, 255, 255, .94);
                box-shadow: 0 10px 30px rgba(18, 45, 64, .07);
                backdrop-filter: blur(10px);
            }

            .o_website_hr_recruitment_jobs_list .o_wevent_index_topbar_filters h1 {
                color: var(--asiati-ink);
                font-size: clamp(1.35rem, 2vw, 1.8rem);
                font-weight: 750;
                letter-spacing: -.025em;
            }

            .o_website_hr_recruitment_jobs_list .o_wevent_index_topbar_filters .form-control,
            .o_website_hr_recruitment_jobs_list .o_wevent_index_topbar_filters .btn,
            .o_website_hr_recruitment_jobs_list .o_wevent_index_topbar_filters .dropdown-toggle {
                min-height: 44px;
                border-radius: 12px;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid > .row {
                flex-direction: row !important;
                align-items: stretch;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid > .row > .col-lg {
                display: flex;
                width: 50%;
                flex: 0 0 50%;
                margin-bottom: 1rem !important;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid .card {
                position: relative;
                width: 100%;
                overflow: hidden;
                border: 1px solid rgba(15, 61, 86, .11);
                border-radius: 18px;
                background: var(--asiati-surface);
                box-shadow: 0 8px 24px rgba(18, 45, 64, .06);
                transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid .card::before {
                content: "";
                position: absolute;
                inset: 0 auto 0 0;
                width: 4px;
                background: linear-gradient(180deg, var(--asiati-teal), var(--asiati-yellow));
                opacity: .95;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid .card:hover {
                transform: translateY(-3px);
                border-color: rgba(18, 109, 120, .28);
                box-shadow: 0 16px 34px rgba(18, 45, 64, .12);
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid .card-body {
                display: flex;
                min-height: 250px;
                flex-direction: column;
                padding: 1.35rem 1.4rem 1.2rem 1.55rem !important;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid h3 {
                margin: 0;
                color: var(--asiati-ink);
                font-size: 1.18rem;
                font-weight: 800;
                line-height: 1.23;
                letter-spacing: -.015em;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid h5 {
                width: fit-content;
                margin-top: .55rem;
                margin-bottom: .55rem;
                padding: .28rem .58rem;
                border-radius: 999px;
                color: var(--asiati-teal);
                background: #e8f6f2;
                font-size: .75rem;
                font-weight: 700;
            }

            .o_website_hr_recruitment_jobs_list .o_job_card_description {
                display: -webkit-box;
                min-height: 4.25rem;
                margin-top: .2rem;
                margin-bottom: 1rem !important;
                overflow: hidden;
                color: var(--asiati-muted) !important;
                font-size: .86rem;
                line-height: 1.55;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 3;
            }

            .o_website_hr_recruitment_jobs_list .o_job_infos {
                gap: .34rem;
                margin-top: auto;
                padding-top: .85rem;
                border-top: 1px solid rgba(15, 61, 86, .08);
                color: #42566d;
                font-size: .8rem;
            }

            .o_website_hr_recruitment_jobs_list .o_job_infos .oi {
                color: var(--asiati-teal) !important;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid_right {
                padding-left: 1.2rem;
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid_right > section {
                position: sticky;
                top: 92px;
                overflow: hidden;
                border: 1px solid rgba(15, 61, 86, .10);
                border-radius: 18px;
                background: #fff;
                box-shadow: 0 10px 30px rgba(18, 45, 64, .07);
            }

            .o_website_hr_recruitment_jobs_list #jobs_grid_right img {
                width: 100%;
                border-radius: 14px;
                object-fit: cover;
            }

            .o_website_hr_recruitment_jobs_list .pagination .page-link {
                border-radius: 10px;
                color: var(--asiati-navy);
            }

            .o_website_hr_recruitment_jobs_list .pagination .active > .page-link {
                border-color: var(--asiati-navy);
                background: var(--asiati-navy);
                color: #fff;
            }

            @media (max-width: 1199.98px) {
                .o_website_hr_recruitment_jobs_list #jobs_grid > .row > .col-lg {
                    width: 100%;
                    flex-basis: 100%;
                }

                .o_website_hr_recruitment_jobs_list #jobs_grid .card-body {
                    min-height: 220px;
                }
            }

            @media (max-width: 991.98px) {
                .o_website_hr_recruitment_jobs_list .oe_website_jobs {
                    padding-inline: 1rem;
                }

                .o_website_hr_recruitment_jobs_list #jobs_grid_right {
                    padding-left: calc(var(--bs-gutter-x) * .5);
                    margin-top: .5rem;
                }

                .o_website_hr_recruitment_jobs_list #jobs_grid_right > section {
                    position: static;
                }
            }

            @media (max-width: 575.98px) {
                .o_website_hr_recruitment_jobs_list .o_wevent_index_topbar_filters {
                    padding: .85rem;
                    border-radius: 14px;
                }

                .o_website_hr_recruitment_jobs_list #jobs_grid .card {
                    border-radius: 14px;
                }

                .o_website_hr_recruitment_jobs_list #jobs_grid .card-body {
                    min-height: auto;
                    padding: 1.1rem 1rem 1rem 1.2rem !important;
                }

                .o_website_hr_recruitment_jobs_list #jobs_grid h3 {
                    font-size: 1.05rem;
                }
            }
        </style>
    </xpath>
</data>
""".strip()


def _base_view(client) -> dict:
    rows = client.search_read(
        "ir.ui.view",
        [["key", "=", BASE_VIEW_KEY]],
        fields=["id", "name", "key", "type", "active"],
        limit=2,
    )
    if len(rows) != 1:
        raise RuntimeError(
            f"Expected exactly one {BASE_VIEW_KEY} view, found {len(rows)}."
        )
    return dict(rows[0])


def apply_jobs_style(client=None) -> dict:
    transport = client or integration.build_odoo_client()
    base_view = _base_view(transport)
    existing = transport.search_read(
        "ir.ui.view",
        [["key", "=", VIEW_KEY]],
        fields=["id", "name", "key", "active", "inherit_id"],
        limit=2,
    )

    values = {
        "name": VIEW_NAME,
        "type": "qweb",
        "key": VIEW_KEY,
        "inherit_id": int(base_view["id"]),
        "mode": "extension",
        "active": True,
        "priority": 90,
        "arch_db": STYLE_ARCH,
    }

    if len(existing) > 1:
        raise RuntimeError(f"Multiple Odoo views use key {VIEW_KEY}.")
    if existing:
        view_id = int(existing[0]["id"])
        if not transport.write("ir.ui.view", [view_id], values):
            raise RuntimeError("Odoo did not confirm the jobs style update.")
        action = "UPDATED"
    else:
        view_id = transport.create("ir.ui.view", values)
        action = "CREATED"

    return {
        "status": "OK",
        "action": action,
        "view_id": view_id,
        "view_key": VIEW_KEY,
        "base_view_id": int(base_view["id"]),
    }


def main() -> None:
    try:
        result = apply_jobs_style()
    except (integration.OdooDisabled, integration.OdooNotConfigured, OdooClientError, RuntimeError) as exc:
        print(json.dumps({
            "status": "DEFERRED",
            "reason": str(exc),
        }, ensure_ascii=False))
        return

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
