"""Regression checks for NBA decision quote evaluation (no network needed)."""
import unittest
from paper_betting.place_espn_bets import best_prices

class DecisionQuoteTests(unittest.TestCase):
    def setUp(self):
        self.pred={"home_win_probability":0.70,"away_win_probability":0.30}
        self.game={"home":"Home","away":"Away","books":[
            {"bookmaker":"Book A","home_decimal":1.30,"away_decimal":4.0},
            {"bookmaker":"Book B","home_decimal":1.45,"away_decimal":3.0}]}

    def test_best_ev_can_be_underdog(self):
        quotes=best_prices(self.pred,self.game)
        self.assertEqual(quotes[0]["selection"],"Away")
        self.assertAlmostEqual(quotes[0]["ev"],0.2)
        winner=max((q for q in quotes if q["side"]=="home"),key=lambda q:q["decimal_odds"])
        self.assertEqual(winner["bookmaker"],"Book B")

    def test_unlabelled_and_invalid_odds_rejected(self):
        game={"home":"Home","away":"Away","books":[
            {"bookmaker":"Book A","home_decimal":1.8},
            {"bookmaker":"unknown","home_decimal":2.0,"away_decimal":2.0},
            {"bookmaker":"Book B","home_decimal":True,"away_decimal":1.0}]}
        quotes=best_prices(self.pred,game)
        self.assertEqual(len(quotes),1)
        self.assertEqual(quotes[0]["selection"],"Home")

if __name__=="__main__":
    unittest.main()
