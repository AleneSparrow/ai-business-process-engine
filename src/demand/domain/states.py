"""Campaign setup and prospect-journey states for Flywheel Demand."""

from enum import StrEnum


class CampaignState(StrEnum):
    """Tenant-facing strategy funnel: audience → positioning → assets → live."""

    MARKET_ANALYSIS = "MARKET_ANALYSIS"
    SEGMENTS_READY = "SEGMENTS_READY"
    POSITIONED = "POSITIONED"
    MOTION_SELECTED = "MOTION_SELECTED"
    ASSETS_READY = "ASSETS_READY"
    LIVE = "LIVE"
    PAUSED = "PAUSED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class ProspectState(StrEnum):
    """Audience-facing acquisition funnel, ending at an inbound inquiry.

    Skip-ahead is allowed: real journeys are not linear. The only required
    destination before the process engine is ``INQUIRED`` — the person
    reached out themselves. ``HANDED_OFF`` is the Product 1 boundary.
    """

    UNKNOWN = "UNKNOWN"
    AWARE = "AWARE"
    ENGAGED = "ENGAGED"
    SUBSCRIBED = "SUBSCRIBED"
    NURTURING = "NURTURING"
    INTENT = "INTENT"
    INQUIRED = "INQUIRED"
    HANDED_OFF = "HANDED_OFF"
    SUPPRESSED = "SUPPRESSED"
    EXPIRED = "EXPIRED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
