import polars as pl
from datetime import datetime, timedelta
from types import MappingProxyType

def _make_eligibility_checker():
    # Make the thresholds read-only via MappingProxyType
    road_upgrade_thresholds = MappingProxyType({
        (4, 3): 20,
        (3, 2): 30,
        (2, 1): 35,
    })

    def _is_road_upgrade_eligible(
        df: pl.DataFrame,
        current_cat: int,
        # Use ~1 year in days to approximate 12 months
        lookback_period: timedelta = timedelta(days=365),
    ) -> bool:
        """
        Returns True if the rider meets the upgrade requirements from `current_cat`
        to the next category, based on the example thresholds.
        
        Raises a ValueError if upgrading from Cat 5 to Cat 4 is attempted.
        """

        # Disallow Cat 5 -> Cat 4
        if current_cat == 5 and (current_cat - 1) == 4:
            raise ValueError("Upgrading from Cat 5 to Cat 4 is not allowed in this rule set.")

        next_cat = current_cat - 1
        if next_cat < 1:
            # Already Cat 1 or above, no further upgrade
            return False

        # Get the points threshold for this cat upgrade
        threshold = _is_road_upgrade_eligible.get((current_cat, next_cat))
        if threshold is None:
            return False

        now = datetime.now()
        earliest_date = now - lookback_period

        df_filtered = df.filter(
            (pl.col("cat") == current_cat) &
            (pl.col("event_date") >= earliest_date)
        )

        # Everything is now points-based
        total_points = df_filtered["points"].sum()
        return total_points >= threshold

    return _is_road_upgrade_eligible

# Create a single instance of the checker with the read-only dictionary in its closure
_is_road_upgrade_eligible = _make_eligibility_checker()

# or upgrades from Category 4 to Category 3, USA Cycling awards upgrade points based on individual stage performances in stage races, but not for General Classification (GC) standings. This means that as a Category 4 rider, you can accumulate points by placing well in each stage of a stage race; however, your overall GC placement in the stage race does not contribute additional upgrade points. The policy specifies that GC points are applicable only for upgrades from Category 3 to Category 2 and from Category 2 to Category 1.