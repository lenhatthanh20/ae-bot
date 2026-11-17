"""Contract of prompt.md: it must match the EA payload, the EA limits and the bridge schema."""
import pathlib
import re
import unittest

import server

ROOT = pathlib.Path(__file__).resolve().parent
PROMPT = (ROOT / "prompt.md").read_text(encoding="utf-8")
EA = (ROOT.parent / "mt5" / "AIGold.mq5").read_text(encoding="utf-8")
README = (ROOT.parent / "README.md").read_text(encoding="utf-8")


def section(title):
    """Text of one '## title' section."""
    m = re.search(rf"^## {title}\b.*?(?=^## |\Z)", PROMPT, re.M | re.S)
    assert m, f"no section '## {title}'"
    return m.group(0)


def ea_input(name):
    return float(re.search(rf"input \w+\s+{name}\s*=\s*([\d.]+)", EA).group(1))


class Sections(unittest.TestCase):
    def test_sections_in_order(self):
        titles = re.findall(r"^## (.+)$", PROMPT, re.M)
        want = ["Data", "Strategy", "Stop and target", "Confidence", "Output"]
        self.assertEqual([t for t in titles if any(t.startswith(w) for w in want)],
                         [next(t for t in titles if t.startswith(w)) for w in want])

    def test_strategy_groups_and_mirror(self):
        s = section("Strategy")
        for group in ("Bias", "Pullback", "Trigger", "Vetoes"):
            self.assertIn(group, s)
        self.assertRegex(PROMPT, r"SELL is the mirror")

    def test_removed_words(self):
        for word in ("divergence", "Asia", "London", "New York", "round number", "20-bar average",
                     "engulfing", "rejection candle"):
            self.assertNotIn(word.lower(), PROMPT.lower(), word)

    def test_none_is_default_and_loss_is_the_cost(self):
        self.assertRegex(PROMPT, r"NONE is the default")
        self.assertRegex(PROMPT, r"(?i)losing trade")


class SellForms(unittest.TestCase):
    """SELL tests are written out. A generic 'swap the signs' rule breaks every x - y test."""

    def test_no_generic_swap_rule(self):
        self.assertNotIn("swap", PROMPT.lower())

    def test_difference_tests_have_explicit_sell_forms(self):
        for form in ("ema50[0] - ema20[0] >= 0.3 x atr",   # bias gap
                     "ema20[0] - bid > 1.0 x atr",         # stretched
                     "close[0] - bid > 0.3 x atr",         # already ran
                     "(HH3 - bid) / atr + 0.2",            # stop recipe
                     "bid - sl_atr x 1.2 x atr",           # target
                     "target < LL20 - 0.5 x atr",          # no room
                     "close[0] - low[0] <= (high[0] - low[0]) / 3"):  # close in the bottom third
            self.assertIn(form, PROMPT, form)

    def test_every_rule_has_a_buy_and_a_sell_form(self):
        rules = section("Strategy") + section("Stop and target") + section("Confidence")
        buys = re.findall(r"^\s*- (?:`\w+` )?BUY: ", rules, re.M)
        sells = re.findall(r"^\s*- (?:`\w+` )?SELL: ", rules, re.M)
        self.assertEqual(len(buys), len(sells))
        self.assertGreaterEqual(len(buys), 20)


class Data(unittest.TestCase):
    def test_matches_build_body(self):
        d = section("Data")
        keys = re.findall(r"(\w+)=%", re.search(r'StringFormat\("(bar=[^"]+)"', EA).group(1))
        self.assertEqual(keys, ["bar", "sym", "tf", "bid", "ask", "atr"])
        cols = re.search(r'"# tf\\n([\w,]+)\\n"', EA).group(1).split(",")
        for name in keys + cols + ["# tf", "# M15", "# H1", "oldest first", "CLOSED", "server time"]:
            self.assertIn(name, d, name)

    def test_row_windows_fit_the_payload(self):
        # [k] = k rows before the last row; the deepest lookback must exist in the smallest section
        deepest = max(int(k) for k in re.findall(r"\[(\d+)\]", PROMPT))
        self.assertLess(deepest, ea_input("InpHtfBars"))
        self.assertLess(deepest, ea_input("InpBars"))


class StopAndTarget(unittest.TestCase):
    def test_fixed_rr_and_clamped_stop_fit_the_ea(self):
        s = section("Stop and target")
        self.assertRegex(s, r"tp_rr.{0,40}always 1\.2")
        self.assertRegex(s, r"1\.0.{0,10}2\.0")
        self.assertGreaterEqual(1.2, ea_input("InpMinRR"))
        self.assertEqual((ea_input("InpSlMinAtr"), ea_input("InpSlMaxAtr")), (1.0, 2.0))
        self.assertLessEqual(2.0 * 1.2, ea_input("InpMaxTpAtr"))


class Confidence(unittest.TestCase):
    def test_counted_with_five_named_extras(self):
        c = section("Confidence")
        self.assertRegex(c, r"50 \+ 10")
        extras = re.findall(r"^- `(\w+)` BUY: ", c, re.M)
        self.assertEqual(len(extras), 5, extras)
        self.assertEqual(extras, re.findall(r"^- `(\w+)` SELL: ", c, re.M))
        self.assertIn("sweep", extras)
        for line in (l for l in c.splitlines() if l.startswith("- `sweep`")):
            self.assertIn("[0]..[2]", line)
            self.assertIn("[3]..[12]", line)
        self.assertIn(str(int(ea_input("InpMinConfidence"))), c)
        # the reason template lists extras by these names
        self.assertRegex(section("Output"), r"extras: ")


class Output(unittest.TestCase):
    def test_fields_match_schema_in_order(self):
        o = section("Output")
        fields = re.findall(r"^- (\w+):", o, re.M)
        self.assertEqual(fields, list(server.SCHEMA["properties"]))

    def test_reason_limit_and_none_values(self):
        o = section("Output")
        self.assertIn("300 characters", o)
        self.assertRegex(o, r"NONE.{0,40}sl_atr 0, tp_rr 0, confidence 0")
        for template in re.findall(r"^\s+`(.+)`$", o, re.M):
            self.assertLessEqual(len(template), 300)


class Readme(unittest.TestCase):
    def test_prompt_bullet_names_the_new_rules(self):
        bullet = re.search(r"^- `bridge/prompt\.md`:.*?(?=^- )", README, re.M | re.S).group(0)
        for text in ("ema20", "1.2", "50 + 10"):
            self.assertIn(text, bullet, text)
        self.assertNotIn("engulfing", bullet)


if __name__ == "__main__":
    unittest.main()
