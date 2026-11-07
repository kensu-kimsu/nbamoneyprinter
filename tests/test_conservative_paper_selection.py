"""Regression tests for conservative NBA paper-only selection policy."""
import unittest
from paper_betting.place_espn_bets import best_prices, eligible_quote

class ConservativeSelectionTests(unittest.TestCase):
    def quote(self,side="home",probability=.65,odds=1.80):
        return {"side":side,"probability":probability,"decimal_odds":odds,
                "ev":probability*odds-1}

    def test_eligible_favorite(self):
        self.assertIsNone(eligible_quote(self.quote(), "home"))

    def test_opposite_side_rejected_even_with_high_ev(self):
        self.assertEqual(eligible_quote(self.quote(side="away",probability=.4,odds=4), "home"),
                         "not_model_predicted_winner")

    def test_longshot_rejected(self):
        self.assertEqual(eligible_quote(self.quote(probability=.65,odds=2.2), "home"),
                         "odds_above_2_decimal")

    def test_low_confidence_rejected(self):
        self.assertEqual(eligible_quote(self.quote(probability=.58,odds=1.95), "home"),
                         "model_confidence_below_60_percent")

    def test_low_ev_rejected(self):
        self.assertEqual(eligible_quote(self.quote(probability=.65,odds=1.60), "home"),
                         "below_8_percent_ev")

    def test_high_ev_opposite_side_not_selected(self):
        pred={"home_win_probability":.7,"away_win_probability":.3}
        game={"home":"Home","away":"Away","books":[
            {"bookmaker":"A","home_decimal":1.55,"away_decimal":5.0}]}
        quotes=best_prices(pred,game)
        self.assertEqual(quotes[0]["side"],"away")
        winner=max((q for q in quotes if q["side"]=="home"),key=lambda q:q["ev"])
        self.assertIsNone(eligible_quote(winner,"home"))

if __name__=="__main__":
    unittest.main()
