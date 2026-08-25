"""Derive a business's default time zone from the postal codes it serves.

Why this exists
---------------
The onboarding wizard never asked for a time zone, so `build_business_dna`
stamped every new business `America/New_York` regardless of where it was. That
zone is printed to the customer in every slot offer and every booking
confirmation (`commercial_service.py` renders `%Z`), so a business three zones
away quoted every appointment wrong until its owner separately found Settings
and corrected it -- which is exactly the "individual setup" the product exists
to avoid.

The information was already on hand: the wizard asks for the ZIP codes the
business serves. This module turns those into a zone.

What this is and is not
-----------------------
It is a DEFAULT, not a determination. The table below is coarse by design: it
maps 3-digit ZIP prefixes to the dominant zone of the state or sub-state region
they belong to, including the well-known split-state exceptions (western
Kentucky, the Florida panhandle, El Paso, western Kansas/Nebraska/Dakotas,
northern Idaho, the western Upper Peninsula). It will occasionally put a
business in the wrong zone near a boundary.

That is acceptable because it replaces a value that is wrong for roughly 60% of
the country, and because the owner can change it in Settings in one click. What
it must never do is silently produce something worse than the old constant, so
anything it cannot place falls back to `America/New_York` -- the previous
behaviour, unchanged.

Zones are IANA identifiers, resolvable by `zoneinfo`, and every one of them is
selectable in the Settings dropdown.
"""

EASTERN = "America/New_York"
CENTRAL = "America/Chicago"
MOUNTAIN = "America/Denver"
ARIZONA = "America/Phoenix"
PACIFIC = "America/Los_Angeles"
ALASKA = "America/Anchorage"
HAWAII = "Pacific/Honolulu"
PUERTO_RICO = "America/Puerto_Rico"

DEFAULT_TIMEZONE = EASTERN

# (low prefix, high prefix, zone). The ranges are DISJOINT: split states are
# written as separate ranges rather than as exceptions layered over a broad
# one, so the result does not depend on scan order and reordering this table
# cannot silently change anyone's zone. The grouping below is for reading.
_PREFIX_RANGES: tuple[tuple[int, int, str], ...] = (
    # --- exceptions inside otherwise-uniform states ---
    (324, 325, CENTRAL),    # Florida panhandle (Pensacola, Panama City)
    (370, 376, CENTRAL),    # middle/western Tennessee
    (380, 385, CENTRAL),    # western Tennessee
    (400, 427, CENTRAL),    # Kentucky: western half is Central; see note below
    (498, 499, CENTRAL),    # western Upper Peninsula, Michigan
    (574, 577, MOUNTAIN),   # western South Dakota
    (586, 588, MOUNTAIN),   # western North Dakota
    (677, 679, MOUNTAIN),   # western Kansas
    (691, 693, MOUNTAIN),   # western Nebraska
    (798, 799, MOUNTAIN),   # El Paso, Texas
    (835, 835, PACIFIC),    # Lewiston, Idaho -- panhandle, Pacific
    (838, 838, PACIFIC),    # Coeur d'Alene / Moscow -- panhandle, Pacific
    (885, 885, MOUNTAIN),   # El Paso exchange
    (977, 979, MOUNTAIN),   # eastern Oregon (Ontario area)
    # --- territories ---
    (6, 9, PUERTO_RICO),    # Puerto Rico and the US Virgin Islands
    # --- broad state ranges ---
    (5, 5, EASTERN),        # New York (Fishkill)
    (10, 27, EASTERN),      # Massachusetts
    (28, 29, EASTERN),      # Rhode Island
    (30, 38, EASTERN),      # New Hampshire
    (39, 49, EASTERN),      # Maine
    (50, 59, EASTERN),      # Vermont
    (60, 69, EASTERN),      # Connecticut
    (70, 89, EASTERN),      # New Jersey
    (100, 149, EASTERN),    # New York
    (150, 196, EASTERN),    # Pennsylvania
    (197, 199, EASTERN),    # Delaware
    (200, 205, EASTERN),    # District of Columbia
    (206, 219, EASTERN),    # Maryland
    (220, 246, EASTERN),    # Virginia
    (247, 268, EASTERN),    # West Virginia
    (270, 289, EASTERN),    # North Carolina
    (290, 299, EASTERN),    # South Carolina
    (300, 319, EASTERN),    # Georgia
    (320, 323, EASTERN),    # Florida, north-east
    (326, 349, EASTERN),    # Florida, the rest
    (350, 369, CENTRAL),    # Alabama
    (377, 379, EASTERN),    # eastern Tennessee (Knoxville, Chattanooga area)
    (386, 397, CENTRAL),    # Mississippi
    (398, 399, EASTERN),    # Georgia
    (430, 459, EASTERN),    # Ohio
    (460, 479, EASTERN),    # Indiana (Indianapolis and most of the state)
    (480, 497, EASTERN),    # Michigan
    (500, 528, CENTRAL),    # Iowa
    (530, 549, CENTRAL),    # Wisconsin
    (550, 567, CENTRAL),    # Minnesota
    (570, 573, CENTRAL),    # eastern South Dakota
    (580, 585, CENTRAL),    # eastern North Dakota
    (590, 599, MOUNTAIN),   # Montana
    (600, 629, CENTRAL),    # Illinois
    (630, 658, CENTRAL),    # Missouri
    (660, 676, CENTRAL),    # eastern Kansas
    (680, 690, CENTRAL),    # eastern Nebraska
    (700, 714, CENTRAL),    # Louisiana
    (716, 729, CENTRAL),    # Arkansas
    (730, 749, CENTRAL),    # Oklahoma
    (750, 797, CENTRAL),    # Texas
    (800, 816, MOUNTAIN),   # Colorado
    (820, 831, MOUNTAIN),   # Wyoming
    (832, 834, MOUNTAIN),   # southern Idaho
    (836, 837, MOUNTAIN),   # Boise and southern Idaho
    (840, 847, MOUNTAIN),   # Utah
    (850, 865, ARIZONA),    # Arizona -- no daylight saving
    (870, 884, MOUNTAIN),   # New Mexico
    (889, 898, PACIFIC),    # Nevada
    (900, 961, PACIFIC),    # California
    (967, 968, HAWAII),     # Hawaii
    (970, 976, PACIFIC),    # Oregon
    (980, 994, PACIFIC),    # Washington
    (995, 999, ALASKA),     # Alaska
)

# Kentucky note: the state is genuinely split roughly in half, and the 400-427
# block does not separate cleanly by prefix. Central is the wider half by area
# and by number of ZIP codes, so it is the better default of the two; Louisville
# and Lexington businesses will need the one click in Settings.


def timezone_for_postal_code(postal_code: str) -> str | None:
    """Zone for one US ZIP, or None when it cannot be placed."""
    digits = "".join(character for character in postal_code if character.isdigit())
    if len(digits) < 5:
        return None
    prefix = int(digits[:3])
    for low, high, zone in _PREFIX_RANGES:
        if low <= prefix <= high:
            return zone
    return None


def timezone_for_service_area(postal_codes: object) -> str:
    """Default zone for a business, from every ZIP it says it serves.

    A business whose area spans two zones (they exist -- Chicago suburbs reach
    into Indiana) gets the zone most of its ZIP codes fall in; ties go to the
    first one seen, which is the first the owner typed. No ZIP codes at all, or
    none that can be placed, keeps the previous constant.
    """
    if not isinstance(postal_codes, (list, tuple)):
        return DEFAULT_TIMEZONE
    counts: dict[str, int] = {}
    for postal_code in postal_codes:
        if not isinstance(postal_code, str):
            continue
        zone = timezone_for_postal_code(postal_code)
        if zone is not None:
            counts[zone] = counts.get(zone, 0) + 1
    if not counts:
        return DEFAULT_TIMEZONE
    return max(counts, key=lambda zone: counts[zone])
