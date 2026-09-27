"""Merged TikZ template catalog. Import ALL; edit the per-subject modules."""

from .advanced_functions import templates as advanced_functions
from .calculus import templates as calculus
from .vectors import templates as vectors
from .data_management import templates as data_management
from .trig_geometry import templates as trig_geometry

ALL = (
    advanced_functions +
    calculus +
    vectors +
    data_management +
    trig_geometry
)
