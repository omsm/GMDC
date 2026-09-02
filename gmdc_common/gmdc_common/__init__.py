"""
Shared building blocks for the GMDC checkpoint applications.

Used by every stage of the site flow:

    Mines entry -> Tare WB -> Tracking point-1 -> Vadaghat (gross check WB)
                -> Tracking point-2 -> Final gross WB -> Mines exit

Application-specific workflow, state/event enums and API payload shaping stay
in each app; this package holds the device drivers, transport clients and the
generic state-machine engine they all share.
"""

__version__ = "0.1.0"
