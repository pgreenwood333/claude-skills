"""Offline tests for the tier pricing helpers and `set-sub-price`. No network: every App Store Connect call is
mocked from fixtures/sub_price_points.json and the price-ladder cache points at a temp file.

  python3 -m unittest test_set_sub_price -v      (run from this folder)
"""
import contextlib, io, json, os, sys, tempfile, time, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asc  # noqa: E402

FX = json.load(open(os.path.join(HERE, "fixtures", "sub_price_points.json")))
SID = FX["sub_id"]


def pid(t, step):
    return asc._pid_encode({"s": SID, "t": t, "p": step})


def point(t, step, price):
    return {"id": pid(t, step), "attributes": {"customerPrice": f"{price:.2f}"},
            "relationships": {"territory": {"data": {"id": t}}}}


def fake_get_all(path, **params):
    if path == f"/v1/subscriptions/{SID}/pricePoints" and params.get("filter[territory]") == "USA":
        return [point("USA", s, p) for s, p in FX["usa_points"].items()]
    if path.endswith("/equalizations"):
        assert path == f"/v1/subscriptionPricePoints/{pid('USA', '10110')}/equalizations", path
        return [point(t, FX["equalized_steps"][t], p) for t, p in FX["equalizations_for_49_99"].items()]
    raise AssertionError(f"unexpected GET {path} {params}")


def fake_get(path, **params):
    if path == f"/v1/subscriptions/{SID}":
        return {"data": {"id": SID, "attributes": {"productId": "example_quarterly", "state": "READY_TO_SUBMIT",
                                                   "subscriptionPeriod": "THREE_MONTHS"}}}
    raise AssertionError(f"unexpected GET {path}")


TIERS = {"BRA": 0.4, "ALB": 0.4, "EGY": 0.6}


class PureHelpers(unittest.TestCase):
    def test_tier_targets(self):
        local = {"USA": 49.99, "GBR": 49.99, "BRA": 279.9, "EGY": 1499.99}
        got = asc.tier_targets(local, {**TIERS, "XXX": 0.4})   # XXX: tiered but not offered -> skipped
        self.assertEqual(set(got), {"BRA", "EGY"})              # tier 1 not listed, ALB not in local
        self.assertAlmostEqual(got["BRA"], 167.94)               # 40% off
        self.assertAlmostEqual(got["EGY"], 599.996)              # 60% off

    def test_step_rounds_down(self):
        lad = FX["ladders"]["BRA"]
        self.assertEqual(asc.step_at_or_under(lad, 167.94), "10051")     # 164.90, not 169.90
        self.assertEqual(asc.step_at_or_under(lad, 174.9), "10053")      # exact match kept

    def test_step_float_fuzz_and_zero(self):
        self.assertEqual(asc.step_at_or_under({"a": 29.994}, 49.99 * 0.6), "a")   # 29.993999... still matches
        self.assertIsNone(asc.step_at_or_under({"z": 0.0, "b": 10.0}, 5.0))       # 0 is never chosen
        self.assertIsNone(asc.step_at_or_under(FX["ladders"]["ALB"], 3540.0))     # all above target


class WithMocks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"fetched": time.time(), "sub": FX["ladders"]}, self.tmp); self.tmp.close()
        self.posts = []

        def fake_req(method, path, body=None, params=None, ok=None):
            if method == "GET":
                raise AssertionError(f"unexpected raw GET {path}")
            if asc.DRY:
                raise AssertionError(f"write attempted during a dry run: {method} {path}")
            self.posts.append((method, path, body))
            return {"data": {"id": f"P{len(self.posts)}"}}
        self.patches = [mock.patch.object(asc, "LADDER_CACHE", self.tmp.name),
                        mock.patch.object(asc, "get_all", fake_get_all),
                        mock.patch.object(asc, "get", fake_get),
                        mock.patch.object(asc, "req", fake_req),
                        mock.patch.object(asc, "load_tiers", lambda mode: {} if mode == "equalized" else dict(TIERS))]
        for p in self.patches:
            p.start()
        asc.DRY = False

    def tearDown(self):
        for p in self.patches:
            p.stop()
        os.unlink(self.tmp.name)
        asc.DRY = False

    def run_cli(self, *args):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["asc.py", *args]), contextlib.redirect_stdout(out):
            asc.main()
        return out.getvalue()

    def test_plan(self):
        plan = asc.tiered_plan(f"/v1/subscriptions/{SID}/pricePoints", asc.sub_equalizer, "49.99", TIERS)
        self.assertEqual({t: v["point"] for t, v in plan.items()}, {
            "USA": pid("USA", "10110"), "GBR": pid("GBR", "10110"), "DEU": pid("DEU", "10110"),
            "BRA": pid("BRA", "10051"),   # 279.90 * 0.6 = 167.94 -> 164.90
            "EGY": pid("EGY", "10060"),   # 1499.99 * 0.4 = 599.996 -> 599.99 (600.00 is above)
            "ALB": pid("ALB", "10099"),   # nothing under 3540 -> stays at the equalized point
        })
        self.assertEqual((plan["BRA"]["tier"], plan["EGY"]["tier"], plan["GBR"]["tier"]), (2, 3, 1))
        self.assertEqual(plan["BRA"]["price"], 164.9)

    def test_tiered_points_matches_plan(self):
        pts = asc.tiered_points(f"/v1/subscriptions/{SID}/pricePoints", asc.sub_equalizer, "49.99", TIERS)
        self.assertEqual(pts["BRA"], pid("BRA", "10051"))

    def test_default_is_dry_run(self):
        out = self.run_cli("set-sub-price", "--sub-id", SID, "--usd", "49.99")
        self.assertEqual(self.posts, [])
        self.assertIn("Dry run: nothing was sent to App Store Connect.", out)
        self.assertIn("Re-run with --apply", out)
        self.assertIn("6 territories: 3 tier 1, 2 tier 2, 1 tier 3.", out)
        self.assertRegex(out, r"BRA\s+2\s+279\.90\s+164\.90")

    def test_global_dry_run_beats_apply(self):
        self.run_cli("--dry-run", "set-sub-price", "--sub-id", SID, "--usd", "49.99", "--apply")
        self.assertEqual(self.posts, [])

    def test_apply_posts_one_price_per_territory(self):
        out = self.run_cli("set-sub-price", "--sub-id", SID, "--usd", "49.99", "--start-date", "2026-12-01", "--apply")
        self.assertEqual(len(self.posts), 6)
        for method, path, body in self.posts:
            self.assertEqual((method, path), ("POST", "/v1/subscriptionPrices"))
            d = body["data"]
            self.assertEqual(d["attributes"], {"preserveCurrentPrice": False, "startDate": "2026-12-01"})
            self.assertEqual(d["relationships"]["subscription"]["data"], {"type": "subscriptions", "id": SID})
        sent = {b["data"]["relationships"]["subscriptionPricePoint"]["data"]["id"] for _, _, b in self.posts}
        self.assertIn(pid("BRA", "10051"), sent)
        self.assertIn("Priced 6 of 6 territories.", out)

    def test_apply_without_start_date_omits_it(self):
        self.run_cli("set-sub-price", "--sub-id", SID, "--usd", "49.99", "--territories", "USA,BRA", "--apply")
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(self.posts[0][2]["data"]["attributes"], {"preserveCurrentPrice": False})

    def test_bad_start_date(self):
        with self.assertRaises(SystemExit):
            self.run_cli("set-sub-price", "--sub-id", SID, "--usd", "49.99", "--start-date", "12/01/2026")

    def test_price_not_a_point(self):
        with self.assertRaises(SystemExit):
            self.run_cli("set-sub-price", "--sub-id", SID, "--usd", "48.00")


if __name__ == "__main__":
    unittest.main()
