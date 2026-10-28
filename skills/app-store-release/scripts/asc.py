#!/usr/bin/env python3
"""App Store Connect release tool: new version, metadata in every locale, in-app purchases and subscriptions with
prices for every country, EAS build, attach build, submit for review. One command per step; the SKILL.md chains them.

Credentials never live in this file. They are read from ~/.appstoreconnect/config.json:
  {"issuer_id": "...", "key_id": "..."}   and the key at ~/.appstoreconnect/private_keys/AuthKey_<key_id>.p8
(or env ASC_ISSUER_ID / ASC_KEY_ID / ASC_KEY_PATH). The key needs the App Manager role.

Every write command takes --dry-run, which prints the requests instead of sending them.

  python3 asc.py apps
  python3 asc.py status <app> [--version 1.4.0]
  python3 asc.py new-version <app> 1.4.0 [--release manual|after-approval]
  python3 asc.py meta-pull <app> --out meta.json [--version 1.4.0]
  python3 asc.py meta-push <app> --file meta.json [--version 1.4.0]
  python3 asc.py products <app> --file products.json
  python3 asc.py build <expo project dir> [--profile production]
  python3 asc.py build-wait <app> --version 1.4.0 [--build-number 12] [--timeout 5400]
  python3 asc.py attach-build <app> --version 1.4.0 [--build-number 12]
  python3 asc.py check <app> --version 1.4.0
  python3 asc.py submit <app> --version 1.4.0 [--products all|id1,id2]

<app> = numeric Apple ID, bundle ID, or a unique part of the app name.
"""
import argparse, base64, concurrent.futures as cf, hashlib, json, os, subprocess, sys, time

import jwt
import requests

API = "https://api.appstoreconnect.apple.com"
DRY = False
_dry_n = [0]
_tok = {}

VERSION_FIELDS = ("description", "keywords", "whatsNew", "promotionalText", "supportUrl", "marketingUrl")
INFO_FIELDS = ("name", "subtitle", "privacyPolicyUrl", "privacyChoicesUrl")
EDITABLE = ("PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED",
            "WAITING_FOR_REVIEW", "INVALID_BINARY")


# ---------------------------------------------------------------- HTTP

def creds():
    cfg = {}
    p = os.path.expanduser("~/.appstoreconnect/config.json")
    if os.path.exists(p):
        cfg = json.load(open(p))
    issuer = os.environ.get("ASC_ISSUER_ID") or cfg.get("issuer_id")
    kid = os.environ.get("ASC_KEY_ID") or cfg.get("key_id")
    path = os.environ.get("ASC_KEY_PATH") or cfg.get("key_path") or \
        os.path.expanduser(f"~/.appstoreconnect/private_keys/AuthKey_{kid}.p8")
    if not (issuer and kid and os.path.exists(path)):
        sys.exit("Missing credentials: create ~/.appstoreconnect/config.json with issuer_id and key_id "
                 "(key file in ~/.appstoreconnect/private_keys/).")
    return issuer, kid, open(path).read()


def token():
    if _tok.get("exp", 0) - 60 < time.time():
        issuer, kid, key = creds()
        exp = int(time.time()) + 1100
        _tok["t"] = jwt.encode({"iss": issuer, "exp": exp, "aud": "appstoreconnect-v1"}, key,
                               algorithm="ES256", headers={"kid": kid, "typ": "JWT"})
        _tok["exp"] = exp
    return _tok["t"]


def req(method, path, body=None, params=None, ok=(200, 201, 204)):
    url = path if path.startswith("http") else API + path
    if DRY and method != "GET":
        _dry_n[0] += 1
        print(f"[dry-run] {method} {path}\n          {json.dumps(body)[:400] if body else ''}")
        fake = f"DRYRUN-{_dry_n[0]}"
        return {"data": {"id": fake, "type": (body or {}).get("data", {}).get("type", ""),
                         "attributes": {}}}
    for attempt in range(8):
        r = requests.request(method, url, params=params, json=body, timeout=60,
                             headers={"Authorization": f"Bearer {token()}"})
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1) if r.status_code == 429 else 2 + attempt * 3)
            continue
        break
    if r.status_code not in ok:
        detail = ""
        try:
            detail = "; ".join(f"{e.get('title')}: {e.get('detail')}" for e in r.json().get("errors", []))
        except ValueError:
            detail = r.text[:300]
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {detail}")
    return r.json() if r.content else {}


def get(path, **params):
    return req("GET", path, params=params or None)


def get_all(path, **params):
    params.setdefault("limit", 200)
    out, d = [], get(path, **params)
    while True:
        out += d.get("data", [])
        nxt = (d.get("links") or {}).get("next")
        if not nxt:
            return out
        d = req("GET", nxt)


def post(type_, attrs=None, rels=None, path=None, included=None):
    data = {"type": type_}
    if attrs:
        data["attributes"] = attrs
    if rels:
        data["relationships"] = {k: {"data": v} for k, v in rels.items()}
    body = {"data": data}
    if included:
        body["included"] = included
    return req("POST", path or f"/v1/{type_}", body)["data"]


def patch(type_, id_, attrs=None, rels=None, path=None):
    data = {"type": type_, "id": id_}
    if attrs:
        data["attributes"] = attrs
    if rels:
        data["relationships"] = {k: {"data": v} for k, v in rels.items()}
    return req("PATCH", path or f"/v1/{type_}/{id_}", {"data": data}).get("data")


def ref(type_, id_):
    return {"type": type_, "id": id_}


# ---------------------------------------------------------------- lookups

def find_app(q):
    apps = get_all("/v1/apps", **{"fields[apps]": "name,bundleId,sku"})
    for a in apps:
        if q in (a["id"], a["attributes"]["bundleId"]):
            return a
    hits = [a for a in apps if q.lower() in a["attributes"]["name"].lower()]
    if len(hits) == 1:
        return hits[0]
    sys.exit(f"App '{q}' matched {len(hits)} apps: " + ", ".join(a["attributes"]["name"] for a in hits or apps))


def versions(app_id):
    return get_all(f"/v1/apps/{app_id}/appStoreVersions", **{"filter[platform]": "IOS"})


def find_version(app_id, version=None):
    vs = versions(app_id)
    if version:
        for v in vs:
            if v["attributes"]["versionString"] == version:
                return v
        sys.exit(f"No iOS version {version}. Versions: " + ", ".join(v["attributes"]["versionString"] for v in vs))
    for v in vs:
        if v["attributes"]["appStoreState"] in EDITABLE:
            return v
    sys.exit("No editable version; create one with new-version.")


def app_info(app_id):
    infos = get_all(f"/v1/apps/{app_id}/appInfos")
    # the editable appInfo is the one not READY_FOR_DISTRIBUTION when a version is in progress
    for i in infos:
        if i["attributes"].get("appStoreState") != "READY_FOR_DISTRIBUTION":
            return i
    return infos[0]


# ---------------------------------------------------------------- commands

def cmd_apps(a):
    for x in get_all("/v1/apps", **{"fields[apps]": "name,bundleId"}):
        print(f"{x['id']:>12}  {x['attributes']['bundleId']:<40} {x['attributes']['name']}")


def cmd_status(a):
    app = find_app(a.app)
    aid = app["id"]
    print(f"{app['attributes']['name']} ({aid}, {app['attributes']['bundleId']})")
    for v in versions(aid)[:4]:
        at = v["attributes"]
        b = get(f"/v1/appStoreVersions/{v['id']}/build").get("data")
        bn = b["attributes"]["version"] if b else "none"
        print(f"  version {at['versionString']:<8} {at['appStoreState']:<28} build {bn}")
    builds = get("/v1/builds", **{"filter[app]": aid, "sort": "-uploadedDate", "limit": 5,
                                  "include": "preReleaseVersion"})
    pre = {i["id"]: i["attributes"]["version"] for i in builds.get("included", [])}
    for b in builds.get("data", []):
        pv = pre.get(((b["relationships"].get("preReleaseVersion") or {}).get("data") or {}).get("id"), "?")
        print(f"  build {pv} ({b['attributes']['version']}) {b['attributes']['processingState']} "
              f"uploaded {b['attributes']['uploadedDate'][:16]}")
    for g in get_all(f"/v1/apps/{aid}/subscriptionGroups"):
        for s in get_all(f"/v1/subscriptionGroups/{g['id']}/subscriptions"):
            print(f"  sub  {s['attributes']['productId']:<40} {s['attributes']['state']}  "
                  f"(group {g['attributes']['referenceName']})")
    for p in get_all(f"/v1/apps/{aid}/inAppPurchasesV2"):
        print(f"  iap  {p['attributes']['productId']:<40} {p['attributes']['state']}  {p['attributes']['inAppPurchaseType']}")


def cmd_new_version(a):
    app = find_app(a.app)
    for v in versions(app["id"]):
        if v["attributes"]["versionString"] == a.version:
            print(f"Version {a.version} already exists ({v['attributes']['appStoreState']}).")
            return
        if v["attributes"]["appStoreState"] == "PREPARE_FOR_SUBMISSION":
            # Apple allows one in-progress version: rename it instead of failing
            patch("appStoreVersions", v["id"], {"versionString": a.version})
            print(f"Renamed in-progress version {v['attributes']['versionString']} to {a.version}.")
            return
    attrs = {"platform": "IOS", "versionString": a.version,
             "releaseType": "MANUAL" if a.release == "manual" else "AFTER_APPROVAL"}
    v = post("appStoreVersions", attrs, {"app": ref("apps", app["id"])})
    print(f"Created version {a.version} ({v['id']}). Apple copies the previous version's text into it.")


def cmd_meta_pull(a):
    app = find_app(a.app)
    v = find_version(app["id"], a.version)
    out = {"version": v["attributes"]["versionString"], "version_locales": {}, "app_info_locales": {}}
    for loc in get_all(f"/v1/appStoreVersions/{v['id']}/appStoreVersionLocalizations"):
        out["version_locales"][loc["attributes"]["locale"]] = {k: loc["attributes"].get(k) for k in VERSION_FIELDS}
    info = app_info(app["id"])
    for loc in get_all(f"/v1/appInfos/{info['id']}/appInfoLocalizations"):
        out["app_info_locales"][loc["attributes"]["locale"]] = {k: loc["attributes"].get(k) for k in INFO_FIELDS}
    json.dump(out, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(f"Wrote {a.out}: {len(out['version_locales'])} version locales, {len(out['app_info_locales'])} app-info locales.")


def check_lengths(locale, fields):
    limits = {"name": 30, "subtitle": 30, "keywords": 100, "promotionalText": 170, "whatsNew": 4000,
              "description": 4000}
    bad = [f"{locale} {k} is {len(v)} chars (max {limits[k]})" for k, v in fields.items()
           if k in limits and isinstance(v, str) and len(v) > limits[k]]
    return bad


def cmd_meta_push(a):
    app = find_app(a.app)
    v = find_version(app["id"], a.version)
    spec = json.load(open(a.file))
    errors = []
    for loc, f in {**spec.get("version_locales", {}), **spec.get("app_info_locales", {})}.items():
        errors += check_lengths(loc, f)
    if errors:
        sys.exit("Over Apple's limits, nothing sent:\n  " + "\n  ".join(errors))
    have = {l["attributes"]["locale"]: l for l in get_all(f"/v1/appStoreVersions/{v['id']}/appStoreVersionLocalizations")}
    n = 0
    for loc, f in spec.get("version_locales", {}).items():
        f = {k: val for k, val in f.items() if k in VERSION_FIELDS and val is not None}
        if loc in have:
            changed = {k: val for k, val in f.items() if have[loc]["attributes"].get(k) != val}
            if changed:
                patch("appStoreVersionLocalizations", have[loc]["id"], changed); n += 1
        elif f:
            post("appStoreVersionLocalizations", {"locale": loc, **f}, {"appStoreVersion": ref("appStoreVersions", v["id"])}); n += 1
    info = app_info(app["id"])
    have = {l["attributes"]["locale"]: l for l in get_all(f"/v1/appInfos/{info['id']}/appInfoLocalizations")}
    for loc, f in spec.get("app_info_locales", {}).items():
        f = {k: val for k, val in f.items() if k in INFO_FIELDS and val is not None}
        if loc in have:
            changed = {k: val for k, val in f.items() if have[loc]["attributes"].get(k) != val}
            if changed:
                patch("appInfoLocalizations", have[loc]["id"], changed); n += 1
        elif f:
            post("appInfoLocalizations", {"locale": loc, **f}, {"appInfo": ref("appInfos", info["id"])}); n += 1
    print(f"Metadata: {n} locale records created or updated on version {v['attributes']['versionString']}.")


# ---------------------------------------------------------------- products: subscriptions and IAPs

def upload_review_screenshot(kind, owner_type, owner_id, path):
    """kind = subscriptionAppStoreReviewScreenshots | inAppPurchaseAppStoreReviewScreenshots"""
    data = open(path, "rb").read()
    res = post(kind, {"fileName": os.path.basename(path), "fileSize": len(data)},
               {"subscription" if owner_type == "subscriptions" else "inAppPurchaseV2": ref(owner_type, owner_id)})
    if DRY:
        return
    for op in res["attributes"]["uploadOperations"]:
        chunk = data[op["offset"]:op["offset"] + op["length"]]
        requests.request(op["method"], op["url"], data=chunk, timeout=120,
                         headers={h["name"]: h["value"] for h in op["requestHeaders"]}).raise_for_status()
    patch(kind, res["id"], {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()})


def all_territories():
    return [t["id"] for t in get_all("/v1/territories")]


def usd_point(points, price):
    for p in points:
        if float(p["attributes"]["customerPrice"]) == float(price):
            return p
    near = sorted({float(p["attributes"]["customerPrice"]) for p in points}, key=lambda x: abs(x - float(price)))[:4]
    sys.exit(f"No US price point at ${price}. Nearest: {near}")


TIERS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "price_tiers.json")


def load_tiers(mode):
    """{territory: discount} for tiered pricing; empty dict = plain equalized prices everywhere."""
    if mode == "equalized":
        return {}
    t = json.load(open(TIERS_FILE))
    out = {c: t["discount"]["2"] for c in t["tier2"]}
    out.update({c: t["discount"]["3"] for c in t["tier3"]})
    return out


LADDER_CACHE = os.path.expanduser("~/.appstoreconnect/price_ladders.json")


def _pid_decode(pid):
    return json.loads(base64.urlsafe_b64decode(pid + "=" * (-len(pid) % 4)))


def _pid_encode(d):
    return base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).decode().rstrip("=")


def price_ladders(kind, points_url, territories):
    """{territory: {price_step: customer_price}}. Apple's price steps are the same for every product of a kind
    (subscription or iap), so the lists are cached for 30 days; missing countries are fetched in parallel."""
    cache = json.load(open(LADDER_CACHE)) if os.path.exists(LADDER_CACHE) else {}
    if time.time() - cache.get("fetched", 0) > 30 * 86400:
        cache = {"fetched": time.time()}
    lad = cache.setdefault(kind, {})
    missing = [t for t in territories if t not in lad]

    def fetch(chunk):
        got = {}
        for p in get_all(points_url, **{"filter[territory]": ",".join(chunk)}):
            d = _pid_decode(p["id"])
            got.setdefault(d["t"], {})[d["p"]] = float(p["attributes"]["customerPrice"])
        return got
    if missing:
        print(f"  downloading price lists for {len(missing)} countries (cached afterwards)", flush=True)
        with cf.ThreadPoolExecutor(3) as ex:
            for got in ex.map(fetch, [missing[k:k + 3] for k in range(0, len(missing), 3)]):
                lad.update(got)
        json.dump(cache, open(LADDER_CACHE, "w"))
    return lad


def tiered_points(points_url, equalize, usd_price, tiers, kind="sub"):
    """Price point id per territory. Tier 1: Apple's equalized point for the US price. Tier 2/3: that local price
    times (1 - discount), rounded DOWN to the nearest Apple price in the country's own price list."""
    def terr(p):
        return p["relationships"]["territory"]["data"]["id"]
    base = usd_point(get_all(points_url, **{"filter[territory]": "USA"}), usd_price)
    chosen = {"USA": base["id"]}
    local = {"USA": float(base["attributes"]["customerPrice"])}
    for p in equalize(base["id"]):
        chosen[terr(p)] = p["id"]
        local[terr(p)] = float(p["attributes"]["customerPrice"])
    ts = sorted(t for t in tiers if t in chosen)
    if not ts:
        return chosen
    owner = _pid_decode(base["id"])["s"]
    lad = price_ladders(kind, points_url, ts)
    for t in ts:
        target = local[t] * (1 - tiers[t]) + 1e-6
        under = [(price, step) for step, price in lad.get(t, {}).items() if 0 < price <= target]
        if under:
            chosen[t] = _pid_encode({"s": owner, "t": t, "p": max(under)[1]})
    return chosen


def create_subscription(app_id, group_id, s, territories):
    subs = [] if group_id.startswith("DRYRUN") else get_all(f"/v1/subscriptionGroups/{group_id}/subscriptions")
    hit = [x for x in subs if x["attributes"]["productId"] == s["product_id"]]
    if hit:
        print(f"  subscription {s['product_id']} exists ({hit[0]['attributes']['state']}), skipped")
        return
    sub = post("subscriptions", {"name": s.get("reference_name", s["product_id"]), "productId": s["product_id"],
                                 "subscriptionPeriod": s["period"], "groupLevel": s.get("group_level", 1),
                                 "familySharable": s.get("family_sharable", False),
                                 "reviewNote": s.get("review_note", "")},
               {"group": ref("subscriptionGroups", group_id)})
    sid = sub["id"]
    for loc, f in s.get("localizations", {}).items():
        post("subscriptionLocalizations", {"locale": loc, "name": f["name"], "description": f.get("description", "")},
             {"subscription": ref("subscriptions", sid)})
    post("subscriptionAvailabilities", {"availableInNewTerritories": True},
         {"subscription": ref("subscriptions", sid), "availableTerritories": [ref("territories", t) for t in territories]})
    # price: the US price point, then Apple's equalized point for every other country
    if DRY:
        tiers = load_tiers(s.get("pricing", "tiered"))
        print(f"  [dry-run] would price {s['product_id']} at ${s['usd_price']} in the US; "
              + (f"{sum(v == 0.4 for v in tiers.values())} tier-2 countries at 40% off, "
                 f"{sum(v == 0.6 for v in tiers.values())} tier-3 at 60% off, the rest equalized" if tiers
                 else "equalized everywhere"))
    else:
        tiers = load_tiers(s.get("pricing", "tiered"))
        chosen = tiered_points(f"/v1/subscriptions/{sid}/pricePoints", lambda pid: get_all(f"/v1/subscriptionPricePoints/{pid}/equalizations",
                                                       include="territory"), s["usd_price"], tiers)
        for t, pid in chosen.items():
            post("subscriptionPrices", {"preserveCurrentPrice": False},
                 {"subscription": ref("subscriptions", sid), "subscriptionPricePoint": ref("subscriptionPricePoints", pid)})
        print(f"  priced in {len(chosen)} countries ({'tiered' if tiers else 'equalized'})")
    offer = s.get("intro_offer")
    if offer:
        # free trial: one introductory offer per country
        for t in territories:
            post("subscriptionIntroductoryOffers",
                 {"offerMode": offer.get("mode", "FREE_TRIAL"), "duration": offer["duration"],
                  "numberOfPeriods": offer.get("periods", 1)},
                 {"subscription": ref("subscriptions", sid), "territory": ref("territories", t)})
    if s.get("review_screenshot"):
        upload_review_screenshot("subscriptionAppStoreReviewScreenshots", "subscriptions", sid, s["review_screenshot"])
    print(f"  created subscription {s['product_id']}")


def create_iap(app_id, p, territories):
    have = [x for x in get_all(f"/v1/apps/{app_id}/inAppPurchasesV2") if x["attributes"]["productId"] == p["product_id"]]
    if have:
        print(f"  in-app purchase {p['product_id']} exists ({have[0]['attributes']['state']}), skipped")
        return
    iap = post("inAppPurchases", {"name": p.get("reference_name", p["product_id"]), "productId": p["product_id"],
                                  "inAppPurchaseType": p.get("type", "NON_CONSUMABLE"),
                                  "reviewNote": p.get("review_note", ""),
                                  "familySharable": p.get("family_sharable", False)},
               {"app": ref("apps", app_id)}, path="/v2/inAppPurchases")
    iid = iap["id"]
    for loc, f in p.get("localizations", {}).items():
        post("inAppPurchaseLocalizations", {"locale": loc, "name": f["name"], "description": f.get("description", "")},
             {"inAppPurchaseV2": ref("inAppPurchases", iid)})
    post("inAppPurchaseAvailabilities", {"availableInNewTerritories": True},
         {"inAppPurchase": ref("inAppPurchases", iid), "availableTerritories": [ref("territories", t) for t in territories]})
    # one US manual price; Apple equalizes every other country automatically from the base territory
    if DRY:
        tiers = load_tiers(p.get("pricing", "tiered"))
        print(f"  [dry-run] would price {p['product_id']} at ${p['usd_price']} (US base; "
              f"{len(tiers)} tier-2/3 countries discounted)" if tiers else " (US base, equalized everywhere)")
    else:
        tiers = load_tiers(p.get("pricing", "tiered"))
        chosen = tiered_points(f"/v2/inAppPurchases/{iid}/pricePoints", lambda pid: get_all(f"/v1/inAppPurchasePricePoints/{pid}/equalizations",
                                                       include="territory"), p["usd_price"], tiers, kind="iap")
        # US base price; tier 2/3 countries get manual discounted prices; tier 1 follows the base automatically
        manual = {"USA": chosen["USA"]}
        manual.update({t: pt for t, pt in chosen.items() if t in tiers})
        inc = [{"type": "inAppPurchasePrices", "id": f"${{p{i}}}", "attributes": {"startDate": None},
                "relationships": {"inAppPurchasePricePoint": {"data": ref("inAppPurchasePricePoints", pt)}}}
               for i, pt in enumerate(manual.values())]
        req("POST", "/v1/inAppPurchasePriceSchedules", {
            "data": {"type": "inAppPurchasePriceSchedules", "relationships": {
                "inAppPurchase": {"data": ref("inAppPurchases", iid)},
                "baseTerritory": {"data": ref("territories", "USA")},
                "manualPrices": {"data": [ref("inAppPurchasePrices", x["id"]) for x in inc]}}},
            "included": inc})
        print(f"  priced: US base plus {len(manual) - 1} discounted countries")
    if p.get("review_screenshot"):
        upload_review_screenshot("inAppPurchaseAppStoreReviewScreenshots", "inAppPurchases", iid, p["review_screenshot"])
    print(f"  created in-app purchase {p['product_id']}")


def cmd_products(a):
    app = find_app(a.app)
    aid = app["id"]
    spec = json.load(open(a.file))
    territories = all_territories() if not DRY else ["USA"] + [f"T{i}" for i in range(174)]
    groups = {g["attributes"]["referenceName"]: g for g in get_all(f"/v1/apps/{aid}/subscriptionGroups")}
    for g in spec.get("subscription_groups", []):
        grp = groups.get(g["reference_name"])
        if not grp:
            grp = post("subscriptionGroups", {"referenceName": g["reference_name"]}, {"app": ref("apps", aid)})
            for loc, f in g.get("localizations", {}).items():
                post("subscriptionGroupLocalizations", {"locale": loc, "name": f["name"],
                                                        "customAppName": f.get("custom_app_name")},
                     {"subscriptionGroup": ref("subscriptionGroups", grp["id"])})
            print(f"Created subscription group {g['reference_name']}")
        for s in g.get("subscriptions", []):
            create_subscription(aid, grp["id"], s, territories)
    for p in spec.get("in_app_purchases", []):
        create_iap(aid, p, territories)


# ---------------------------------------------------------------- builds

def cmd_project(a):
    """Find the Expo project folder whose ios.bundleIdentifier matches the app."""
    app = find_app(a.app)
    bid = app["attributes"]["bundleId"]
    roots = [os.path.expanduser("~/Projects"), "/Volumes/PGExtHD"] + (a.root or [])
    hits = []
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ("node_modules", "ios", "android", ".git", "DerivedData", "Pods")
                       and not d.startswith(".") and dirpath.count(os.sep) - root.count(os.sep) < 3]
            for f in ("app.json", "app.config.js", "app.config.ts"):
                if f in files:
                    try:
                        if bid in open(os.path.join(dirpath, f), errors="ignore").read():
                            hits.append(dirpath)
                    except OSError:
                        pass
    print("\n".join(sorted(set(hits))) or f"No Expo project found for {bid}")


def cmd_build(a):
    cmd = ["eas", "build", "--platform", "ios", "--profile", a.profile, "--auto-submit", "--non-interactive", "--no-wait"]
    print("Running:", " ".join(cmd), "in", a.project)
    if DRY:
        return
    r = subprocess.run(cmd, cwd=a.project, capture_output=True, text=True)
    print(r.stdout[-3000:], r.stderr[-2000:])
    if r.returncode:
        sys.exit("EAS build failed to start.")


def find_build(app_id, version, number=None):
    params = {"filter[app]": app_id, "filter[preReleaseVersion.version]": version, "sort": "-uploadedDate", "limit": 10}
    if number:
        params["filter[version]"] = str(number)
    data = get("/v1/builds", **params).get("data", [])
    return data[0] if data else None


def cmd_build_wait(a):
    app = find_app(a.app)
    t0 = time.time()
    while time.time() - t0 < a.timeout:
        b = find_build(app["id"], a.version, a.build_number)
        state = b["attributes"]["processingState"] if b else "not uploaded yet"
        print(f"{time.strftime('%H:%M')}  build {a.version} ({a.build_number or 'latest'}): {state}", flush=True)
        if b and state == "VALID":
            if b["attributes"].get("usesNonExemptEncryption") is None:
                # answers the export-compliance question so the build is usable (standard HTTPS only)
                patch("builds", b["id"], {"usesNonExemptEncryption": False})
                print("  set export compliance: no non-exempt encryption")
            return
        if state in ("FAILED", "INVALID"):
            sys.exit(f"Build {state}.")
        time.sleep(60)
    sys.exit("Timed out waiting for the build.")


def cmd_attach_build(a):
    app = find_app(a.app)
    v = find_version(app["id"], a.version)
    b = find_build(app["id"], a.version, a.build_number)
    if not b:
        sys.exit("Build not found; run build-wait first.")
    req("PATCH", f"/v1/appStoreVersions/{v['id']}/relationships/build", {"data": ref("builds", b["id"])})
    print(f"Attached build {b['attributes']['version']} to version {a.version}.")


# ---------------------------------------------------------------- checks and submit

def cmd_check(a, quiet=False):
    app = find_app(a.app)
    v = find_version(app["id"], a.version)
    problems = []
    if not get(f"/v1/appStoreVersions/{v['id']}/build").get("data"):
        problems.append("no build attached")
    for loc in get_all(f"/v1/appStoreVersions/{v['id']}/appStoreVersionLocalizations"):
        at = loc["attributes"]
        miss = [k for k in ("description", "keywords", "whatsNew") if not at.get(k)]
        if miss:
            problems.append(f"{at['locale']}: missing {', '.join(miss)}")
        sets = get_all(f"/v1/appStoreVersionLocalizations/{loc['id']}/appScreenshotSets")
        if not sets and at["locale"] == "en-US":
            problems.append("en-US: no screenshots")
    for g in get_all(f"/v1/apps/{app['id']}/subscriptionGroups"):
        for s in get_all(f"/v1/subscriptionGroups/{g['id']}/subscriptions"):
            if s["attributes"]["state"] == "MISSING_METADATA":
                problems.append(f"subscription {s['attributes']['productId']}: missing metadata "
                                "(localization, price, or review screenshot)")
    for p in get_all(f"/v1/apps/{app['id']}/inAppPurchasesV2"):
        if p["attributes"]["state"] == "MISSING_METADATA":
            problems.append(f"in-app purchase {p['attributes']['productId']}: missing metadata")
    if not quiet:
        print("Ready to submit." if not problems else "Not ready:\n  " + "\n  ".join(problems))
    return problems


def cmd_submit(a):
    app = find_app(a.app)
    aid = app["id"]
    v = find_version(aid, a.version)
    blockers = [p for p in cmd_check(a, quiet=True) if not p.startswith(("subscription", "in-app"))]
    if blockers and not DRY:
        sys.exit("Not submitting:\n  " + "\n  ".join(blockers))
    want = None if a.products in (None, "all") else set(a.products.split(","))
    # products first, so new ones ride along with this version's review
    for g in get_all(f"/v1/apps/{aid}/subscriptionGroups"):
        for s in get_all(f"/v1/subscriptionGroups/{g['id']}/subscriptions"):
            pid = s["attributes"]["productId"]
            if s["attributes"]["state"] == "READY_TO_SUBMIT" and (want is None or pid in want):
                post("subscriptionSubmissions", rels={"subscription": ref("subscriptions", s["id"])})
                print(f"Queued subscription {pid}")
    for p in get_all(f"/v1/apps/{aid}/inAppPurchasesV2"):
        pid = p["attributes"]["productId"]
        if p["attributes"]["state"] == "READY_TO_SUBMIT" and (want is None or pid in want):
            post("inAppPurchaseSubmissions", rels={"inAppPurchaseV2": ref("inAppPurchases", p["id"])})
            print(f"Queued in-app purchase {pid}")
    subs = get_all("/v1/reviewSubmissions", **{"filter[app]": aid, "filter[platform]": "IOS",
                                                "filter[state]": "READY_FOR_REVIEW"})
    rs = subs[0] if subs else post("reviewSubmissions", {"platform": "IOS"}, {"app": ref("apps", aid)})
    try:
        post("reviewSubmissionItems", rels={"reviewSubmission": ref("reviewSubmissions", rs["id"]),
                                            "appStoreVersion": ref("appStoreVersions", v["id"])})
    except RuntimeError as e:
        if "already" not in str(e).lower():
            raise
    patch("reviewSubmissions", rs["id"], {"submitted": True})
    print(f"Submitted version {a.version} for App Review.")


def main():
    global DRY
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print writes instead of sending them")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("apps")
    p = sp.add_parser("status"); p.add_argument("app"); p.add_argument("--version")
    p = sp.add_parser("new-version"); p.add_argument("app"); p.add_argument("version")
    p.add_argument("--release", choices=["manual", "after-approval"], default="after-approval")
    p = sp.add_parser("meta-pull"); p.add_argument("app"); p.add_argument("--out", required=True); p.add_argument("--version")
    p = sp.add_parser("meta-push"); p.add_argument("app"); p.add_argument("--file", required=True); p.add_argument("--version")
    p = sp.add_parser("products"); p.add_argument("app"); p.add_argument("--file", required=True)
    p = sp.add_parser("project"); p.add_argument("app"); p.add_argument("--root", action="append")
    p = sp.add_parser("build"); p.add_argument("project"); p.add_argument("--profile", default="production")
    for name in ("build-wait", "attach-build"):
        p = sp.add_parser(name); p.add_argument("app"); p.add_argument("--version", required=True)
        p.add_argument("--build-number")
        if name == "build-wait":
            p.add_argument("--timeout", type=int, default=5400)
    p = sp.add_parser("check"); p.add_argument("app"); p.add_argument("--version", required=True)
    p = sp.add_parser("submit"); p.add_argument("app"); p.add_argument("--version", required=True)
    p.add_argument("--products", default="all", help="'all' (default), 'none', or comma-separated product IDs")
    a = ap.parse_args()
    DRY = a.dry_run
    if getattr(a, "products", None) == "none":
        a.products = ","
    fn = {"apps": cmd_apps, "status": cmd_status, "new-version": cmd_new_version, "meta-pull": cmd_meta_pull,
          "meta-push": cmd_meta_push, "products": cmd_products, "build": cmd_build, "project": cmd_project, "build-wait": cmd_build_wait,
          "attach-build": cmd_attach_build, "check": cmd_check, "submit": cmd_submit}[a.cmd]
    try:
        fn(a)
    except RuntimeError as e:
        sys.exit(str(e))
    if DRY:
        print("\nDry run: nothing was sent to App Store Connect.")


if __name__ == "__main__":
    main()
