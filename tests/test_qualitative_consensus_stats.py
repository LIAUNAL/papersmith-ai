"""Pure statistics of consensus rounds and MICMAC (paper-type-lines S8; T8-Q2, decision K4).

Every expected value is computed by hand in the docstrings below, never by the
module under test.
"""

from __future__ import annotations

import sys
import unittest
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skills._core.qualitative import consensus_stats as stats  # noqa: E402

NAMES = ["A", "B", "C", "D"]
# A -> B is P (potential), counted as 4 by default.
MATRIX = [[0, 4, 3, 1],
          [2, 0, 3, 1],
          [0, 1, 0, 0],
          [0, 1, 0, 0]]


class Quantiles(unittest.TestCase):
    def test_type_7_interpolates_between_order_statistics(self) -> None:
        """[1, 2, 3, 4], n = 4. q1: h = 3 * 0.25 = 0.75 -> 1 + 0.75 (2 - 1) = 1.75;
        median: h = 1.5 -> 2 + 0.5 = 2.5; q3: h = 2.25 -> 3 + 0.25 = 3.25."""
        self.assertEqual(stats.quantile([4, 1, 3, 2], Fraction(1, 4)), Fraction(7, 4))
        self.assertEqual(stats.quantile([4, 1, 3, 2], Fraction(1, 2)), Fraction(5, 2))
        self.assertEqual(stats.quantile([4, 1, 3, 2], Fraction(3, 4)), Fraction(13, 4))
        self.assertIn("type 7", stats.QUANTILE_METHOD)

    def test_a_single_rating_is_every_quantile(self) -> None:
        summary = stats.item_summary([5], agree_from=4, threshold=70)
        self.assertEqual((summary["q1"], summary["median"], summary["q3"], summary["iqr"]), (5, 5, 5, 0))
        self.assertEqual((summary["agreement_percent"], summary["consensus"]), (100, True))

    def test_no_rating_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            stats.item_summary([], agree_from=4, threshold=70)


class Agreement(unittest.TestCase):
    def test_hand_computed_item(self) -> None:
        """Ratings 1 2 3 4 5 5 4 3 4 on 1-5, agree from 4: agree = #{4, 5, 5, 4, 4} = 5, n = 9,
        100 * 5 / 9 = 55.5556 % < 70 -> no consensus. Sorted 1 2 3 3 4 4 4 5 5: median x[4] = 4,
        q1 h = 8 * 0.25 = 2 -> x[2] = 3, q3 h = 6 -> x[6] = 4, IQR 1."""
        summary = stats.item_summary([1, 2, 3, 4, 5, 5, 4, 3, 4], agree_from=4, threshold=70)
        self.assertEqual(summary, {"n": 9, "agree": 5, "agreement_percent": 55.5556, "median": 4, "q1": 3,
                                   "q3": 4, "iqr": 1, "consensus": False})

    def test_the_threshold_is_inclusive(self) -> None:
        """[1, 2, 3, 4] agree from 3: 2 of 4 = 50 %; 50 reaches it, 50.01 does not."""
        self.assertTrue(stats.item_summary([1, 2, 3, 4], 3, 50)["consensus"])
        self.assertFalse(stats.item_summary([1, 2, 3, 4], 3, 50.01)["consensus"])
        summary = stats.item_summary([1, 2, 3, 4], 3, 50)
        self.assertEqual((summary["median"], summary["q1"], summary["q3"], summary["iqr"]), (2.5, 1.75, 3.25, 1.5))

    def test_the_comparison_is_exact_not_floating(self) -> None:
        """7 of 9 = 77.777...%: below 77.78, above 77.7 (fractions, no rounding first)."""
        ratings = [4] * 7 + [1, 1]
        self.assertEqual(stats.item_summary(ratings, 4, 77.7)["agreement_percent"], 77.7778)
        self.assertFalse(stats.item_summary(ratings, 4, 77.78)["consensus"])
        self.assertTrue(stats.item_summary(ratings, 4, 77.7)["consensus"])

    def test_a_round_groups_by_item_in_first_appearance_order(self) -> None:
        responses = [("m1", "I2", 5), ("m1", "I1", 2), ("m2", "I2", 4), ("m2", "I1", 5), ("m3", "I2", 1)]
        summary = stats.round_summary(responses, agree_from=4, threshold=60)
        self.assertEqual([row["item"] for row in summary], ["I2", "I1"])
        # I2: 5 4 1 -> 2 of 3 = 66.6667 % >= 60; sorted 1 4 5: median 4, q1 h = 0.5 -> 2.5, q3 h = 1.5 -> 4.5.
        self.assertEqual(summary[0], {"item": "I2", "n": 3, "agree": 2, "agreement_percent": 66.6667, "median": 4,
                                      "q1": 2.5, "q3": 4.5, "iqr": 2, "consensus": True})
        # I1: 2 5 -> 1 of 2 = 50 %; median 3.5, q1 h = 0.25 -> 2.75, q3 h = 0.75 -> 4.25.
        self.assertEqual(summary[1], {"item": "I1", "n": 2, "agree": 1, "agreement_percent": 50, "median": 3.5,
                                      "q1": 2.75, "q3": 4.25, "iqr": 1.5, "consensus": False})

    def test_change_from_the_previous_round(self) -> None:
        """Round 1: 55.5556 %, median 4, IQR 1, no consensus; round 2: 100 %, median 5, IQR 0.25
        (4 5 5 5: q1 h = 0.75 -> 4.75, q3 = 5). Change: +44.4444, +1, -0.75."""
        before = stats.item_summary([1, 2, 3, 4, 5, 5, 4, 3, 4], 4, 70)
        after = stats.item_summary([4, 5, 5, 5], 4, 70)
        self.assertEqual(stats.change(after, before), {"agreement_percent": 44.4444, "median": 1, "iqr": -0.75,
                                                       "consensus_previous": False})


class Micmac(unittest.TestCase):
    def test_hand_computed_four_variables_until_stable(self) -> None:
        """M (P = 4):            row sums (influence)   column sums (dependence)
             A [0 4 3 1]          A 8                    A 0+2+0+0 = 2
             B [2 0 3 1]          B 6                    B 4+0+1+1 = 6
             C [0 1 0 0]          C 1                    C 3+3+0+0 = 6
             D [0 1 0 0]          D 1                    D 1+1+0+0 = 2
        total 16, mean 4. Quadrants: A 8 > 4, 2 <= 4 influential; B 6, 6 relay; C 1, 6 dependent;
        D 1, 2 autonomous. Ranks: influence A1 B2 C3 D3; dependence B1 C1 A3 D3.

        M^2 rows: A = 4B + 3C + D = [8 4 12 4] (28); B = 2A + 3C + D = [0 12 6 2] (20);
        C = D = row B of M = [2 0 3 1] (6). Columns 12 16 24 8, total 60.
        Influence ranks A1 B2 C3 D3 (stable); dependence C1 B2 A3 D4 (moved): not stable.

        M^3 rows: A = 8A + 4B + 12C + 4D = [8 48 36 12] (104); B = 12B + 6C + 2D = [24 8 36 12] (80);
        C = D = 2A + 3C + D = [0 12 6 2] (20). Columns 32 80 84 28, total 224, mean 56.
        Influence A1 B2 C3 D3, dependence C1 B2 A3 D4: both equal power 2, stable at k = 3.
        Quadrants at k = 3: A 104 > 56, 32 influential; B 80, 80 relay; C 20, 84 dependent;
        D 20, 28 autonomous."""
        result = stats.micmac(NAMES, MATRIX)
        self.assertEqual((result["power"], result["power_mode"], result["stable"]), (3, "until-stable", True))
        self.assertEqual(result["stability"], [
            {"power": 2, "influence_stable": True, "dependence_stable": False},
            {"power": 3, "influence_stable": True, "dependence_stable": True}])
        direct, indirect = result["direct"], result["indirect"]
        self.assertEqual((direct["total"], direct["mean"], indirect["total"], indirect["mean"]), (16, 4, 224, 56))
        self.assertEqual([(v["name"], v["influence"], v["dependence"], v["influence_rank"], v["dependence_rank"],
                           v["quadrant"]) for v in direct["variables"]],
                         [("A", 8, 2, 1, 3, "influential"), ("B", 6, 6, 2, 1, "relay"),
                          ("C", 1, 6, 3, 1, "dependent"), ("D", 1, 2, 3, 3, "autonomous")])
        self.assertEqual([(v["influence"], v["dependence"], v["influence_rank"], v["dependence_rank"], v["quadrant"])
                          for v in indirect["variables"]],
                         [(104, 32, 1, 3, "influential"), (80, 80, 2, 2, "relay"), (20, 84, 3, 1, "dependent"),
                          (20, 28, 3, 4, "autonomous")])

    def test_a_fixed_power_reports_its_own_stability(self) -> None:
        """k = 2: M^2 sums 28 20 6 6 and 12 16 24 8 (see above); the dependence ranking moved."""
        result = stats.micmac(NAMES, MATRIX, power=2)
        self.assertEqual((result["power"], result["power_mode"], result["stable"]), (2, "fixed", False))
        self.assertEqual([(v["influence"], v["dependence"]) for v in result["indirect"]["variables"]],
                         [(28, 12), (20, 16), (6, 24), (6, 8)])

    def test_an_unstable_ranking_stops_at_the_maximum_power(self) -> None:
        """A 2-cycle A -> B (1), B -> A (2): odd powers are off-diagonal (B influences more),
        even powers diagonal (equal sums, both rank 1), so the ranking changes at every power;
        the search stops at MAX_POWER, unstable."""
        result = stats.micmac(["A", "B"], [[0, 1], [2, 0]])
        self.assertEqual((result["power"], result["stable"]), (stats.MAX_POWER, False))
        self.assertEqual(len(result["stability"]), stats.MAX_POWER - 1)

    def test_ranks_and_quadrants_at_the_mean(self) -> None:
        self.assertEqual(stats.competition_ranks([8, 6, 1, 1]), [1, 2, 3, 3])
        self.assertEqual(stats.competition_ranks([5, 5, 2]), [1, 1, 3])
        # 4 * 4 == 16: exactly at the mean counts as low.
        self.assertEqual(stats.quadrant(4, 4, 16, 4), "autonomous")
        self.assertEqual(stats.quadrant(5, 4, 16, 4), "influential")

    def test_invalid_matrices_are_refused(self) -> None:
        for names, matrix, power in ((["A"], [[0]], None), (["A", "B"], [[0, 1]], None),
                                     (["A", "B"], [[0, -1], [1, 0]], None), (["A", "B"], [[0, 1], [1, 0]], 1),
                                     (["A", "B"], [[0, 1], [1, 0]], 11)):
            with self.subTest(matrix=matrix, power=power), self.assertRaises(ValueError):
                stats.micmac(names, matrix, power)


if __name__ == "__main__":
    unittest.main()
