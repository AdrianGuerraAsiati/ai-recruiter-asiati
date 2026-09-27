"""Shared domain exceptions for training services."""


class TrainingNotFound(Exception):
    pass


class TrainingStateError(Exception):
    pass


class TrainingAssignmentError(Exception):
    pass
