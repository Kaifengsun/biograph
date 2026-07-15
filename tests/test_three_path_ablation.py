import unittest

from analyze_three_path_ablation import paired_test, rrf_rank


class ThreePathAblationTests(unittest.TestCase):
    def test_rrf_rewards_items_present_in_both_rankings(self):
        ranking = rrf_rank([["a", "b"], ["b", "c"]])
        self.assertEqual(ranking[0], "b")

    def test_paired_binary_test_records_improvements_and_regressions(self):
        result = paired_test(
            [1, 1, 0, 1],
            [0, 1, 1, 0],
            "hit_at_5",
            iterations=1000,
            seed=7,
            label="test",
        )
        self.assertEqual(result["improvements"], 2)
        self.assertEqual(result["regressions"], 1)
        self.assertEqual(result["discordant_pairs"], 3)
        self.assertEqual(result["test"], "exact_paired_mcnemar_binomial")

    def test_paired_continuous_identical_values_return_p_one(self):
        result = paired_test(
            [0.5, 1.0],
            [0.5, 1.0],
            "mrr",
            iterations=1000,
            seed=7,
            label="test",
        )
        self.assertEqual(result["delta_mean"], 0.0)
        self.assertEqual(result["p_value_raw"], 1.0)


if __name__ == "__main__":
    unittest.main()
