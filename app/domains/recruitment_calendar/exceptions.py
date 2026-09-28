"""Recruitment calendar domain errors."""


class RecruitmentCalendarError(Exception):
    """Base recruitment calendar error."""


class RecruitmentEventNotFound(RecruitmentCalendarError):
    pass


class RecruitmentEventValidationError(RecruitmentCalendarError):
    pass


class RecruitmentApplicationNotEligible(RecruitmentCalendarError):
    pass
