"""Single source of truth for application stage groups.

The product has two vocabularies for the same pipeline: the legacy one
(SCREENING, INTERVIEW, SELECTED, OFFER) and the Odoo hr.applicant stages used by
the candidate detail page (INITIAL_QUALIFICATION, FIRST_INTERVIEW,
SECOND_INTERVIEW, CONTRACT_PROPOSAL, CONTRACT_SIGNED). Every rule that depends
on "where" an application is must use these groups so both vocabularies behave
the same.
"""

from __future__ import annotations

# Stage at which a contract can be prepared and linked to the application.
CONTRACT_READY_STATUSES = frozenset({"SELECTED", "OFFER", "CONTRACT_PROPOSAL"})

# Stages at which interviews/calls can be scheduled in the recruitment calendar.
# Screening (SCREENING / INITIAL_QUALIFICATION) stays out on purpose: the
# candidate must be advanced to an interview stage first.
CALENDAR_ELIGIBLE_STATUSES = frozenset(
    {
        "INTERVIEW",
        "FIRST_INTERVIEW",
        "SECOND_INTERVIEW",
        "SELECTED",
        "OFFER",
        "CONTRACT_PROPOSAL",
        "CONTRACT_SIGNED",
        "HIRED",
    }
)

# Forward progress of the active pipeline. Inactive outcomes (REJECTED,
# WITHDRAWN, ON_HOLD) are intentionally absent: they rank below every stage.
_STAGE_RANK = {
    "APPLIED": 0,
    "SCREENING": 1,
    "INITIAL_QUALIFICATION": 1,
    "INTERVIEW": 2,
    "FIRST_INTERVIEW": 2,
    "SECOND_INTERVIEW": 3,
    "SELECTED": 4,
    "OFFER": 4,
    "CONTRACT_PROPOSAL": 4,
    "CONTRACT_SIGNED": 5,
    "HIRED": 6,
}


def stage_rank(status: str | None) -> int:
    return _STAGE_RANK.get(str(status or "").strip().upper(), -1)


def is_contract_ready(status: str | None) -> bool:
    return str(status or "").strip().upper() in CONTRACT_READY_STATUSES


def is_at_or_beyond(status: str | None, target: str) -> bool:
    """True when ``status`` is an active stage at or after ``target``."""
    return stage_rank(status) >= stage_rank(target) >= 0
