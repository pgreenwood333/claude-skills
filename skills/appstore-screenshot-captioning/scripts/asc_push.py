"""Push screenshots + localized metadata to App Store Connect.

Usage:
  PYTHONPATH=/Volumes/PGExtHD/pydeps python3 scripts/store-screenshots/asc_push.py status
  PYTHONPATH=/Volumes/PGExtHD/pydeps python3 scripts/store-screenshots/asc_push.py push [locale ...]

Reads metadata.json (per-locale text + which screenshots folder to use) and
screenshots/appstore/<folder>/0N.png. Targets the app's editable version
(PREPARE_FOR_SUBMISSION etc.). Replaces the 6.9" iPhone screenshot set.
"""
import hashlib, json, os, sys, time
import jwt, requests

ISSUER = "<YOUR_ASC_ISSUER_ID>"
KEY_ID = "<YOUR_ASC_KEY_ID>"
KEY_PATH = os.path.expanduser(f"~/.appstoreconnect/private_keys/AuthKey_{KEY_ID}.p8")
APP_ID = "6799964411"
API = "https://api.appstoreconnect.apple.com/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SHOT_TYPE = "APP_IPHONE_67"  # 6.9"/6.7" slot; accepts 1320x2868
EDITABLE = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED",
            "METADATA_REJECTED", "WAITING_FOR_REVIEW", "INVALID_BINARY"}

_tok = {"t": None, "exp": 0}


def token():
    if time.time() > _tok["exp"] - 60:
        exp = int(time.time()) + 1100
        _tok["t"] = jwt.encode({"iss": ISSUER, "exp": exp, "aud": "appstoreconnect-v1"},
                               open(KEY_PATH).read(), algorithm="ES256",
                               headers={"kid": KEY_ID, "typ": "JWT"})
        _tok["exp"] = exp
    return _tok["t"]


def call(method, path, **kw):
    url = path if path.startswith("http") else API + path
    for attempt in range(5):
        try:
            r = requests.request(method, url, headers={"Authorization": f"Bearer {token()}"},
                                 timeout=60, **kw)
        except requests.exceptions.RequestException:
            if attempt == 4: raise
            time.sleep(2 ** attempt); continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(int(r.headers.get("Retry-After", 2 ** attempt))); continue
        break
    if r.status_code >= 400:
        raise SystemExit(f"{method} {path} -> {r.status_code}\n{r.text[:1500]}")
    return r.json() if r.content else {}


def editable_version():
    vs = call("GET", f"/apps/{APP_ID}/appStoreVersions",
              params={"filter[platform]": "IOS", "limit": 10})["data"]
    for v in vs:
        if v["attributes"]["appStoreState"] in EDITABLE:
            return v
    raise SystemExit("No editable iOS version: " +
                     ", ".join(f'{v["attributes"]["versionString"]}={v["attributes"]["appStoreState"]}' for v in vs))


def editable_appinfo():
    infos = call("GET", f"/apps/{APP_ID}/appInfos")["data"]
    for i in infos:
        if i["attributes"].get("appStoreState") in EDITABLE or i["attributes"].get("state") in (
                "PREPARE_FOR_SUBMISSION", "WAITING_FOR_REVIEW", "REJECTED", "DEVELOPER_REJECTED"):
            return i
    return infos[0]


def status():
    v = editable_version()
    print("version", v["attributes"]["versionString"], v["attributes"]["appStoreState"], v["id"])
    for l in call("GET", f'/appStoreVersions/{v["id"]}/appStoreVersionLocalizations')["data"]:
        a = l["attributes"]
        sets = call("GET", f'/appStoreVersionLocalizations/{l["id"]}/appScreenshotSets')["data"]
        shots = {s["attributes"]["screenshotDisplayType"]:
                 len(call("GET", f'/appScreenshotSets/{s["id"]}/appScreenshots')["data"]) for s in sets}
        print(f'  {a["locale"]}: kw={a.get("keywords")!r} whatsNew={bool(a.get("whatsNew"))} '
              f'support={a.get("supportUrl")} shots={shots}')
    info = editable_appinfo()
    print("appInfo", info["id"], info["attributes"])
    for l in call("GET", f'/appInfos/{info["id"]}/appInfoLocalizations')["data"]:
        a = l["attributes"]
        print(f'  {a["locale"]}: name={a["name"]!r} subtitle={a.get("subtitle")!r} privacy={a.get("privacyPolicyUrl")}')


def upload_shots(loc_id, folder):
    files = sorted(f for f in os.listdir(os.path.join(ROOT, "screenshots/appstore", folder))
                   if f.endswith(".png") and f[:2].isdigit())
    sets = call("GET", f"/appStoreVersionLocalizations/{loc_id}/appScreenshotSets")["data"]
    s = next((x for x in sets if x["attributes"]["screenshotDisplayType"] == SHOT_TYPE), None)
    if s:
        for old in call("GET", f'/appScreenshotSets/{s["id"]}/appScreenshots')["data"]:
            call("DELETE", f'/appScreenshots/{old["id"]}')
    else:
        s = call("POST", "/appScreenshotSets", json={"data": {
            "type": "appScreenshotSets", "attributes": {"screenshotDisplayType": SHOT_TYPE},
            "relationships": {"appStoreVersionLocalization": {
                "data": {"type": "appStoreVersionLocalizations", "id": loc_id}}}}})["data"]
    ids = []
    for f in files:
        path = os.path.join(ROOT, "screenshots/appstore", folder, f)
        data = open(path, "rb").read()
        shot = call("POST", "/appScreenshots", json={"data": {
            "type": "appScreenshots", "attributes": {"fileName": f"{folder}-{f}", "fileSize": len(data)},
            "relationships": {"appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": s["id"]}}}}})["data"]
        for op in shot["attributes"]["uploadOperations"]:
            part = data[op["offset"]:op["offset"] + op["length"]]
            h = {x["name"]: x["value"] for x in op.get("requestHeaders", [])}
            r = requests.request(op["method"], op["url"], headers=h, data=part)
            if r.status_code >= 400:
                raise SystemExit(f"upload part failed {r.status_code} {r.text[:300]}")
        call("PATCH", f'/appScreenshots/{shot["id"]}', json={"data": {
            "type": "appScreenshots", "id": shot["id"],
            "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}}})
        ids.append(shot["id"])
        print(f"    uploaded {f}")
    call("PATCH", f'/appScreenshotSets/{s["id"]}/relationships/appScreenshots',
         json={"data": [{"type": "appScreenshots", "id": i} for i in ids]})
    return ids


def push(locales):
    meta = json.load(open(os.path.join(HERE, "metadata.json")))
    v = editable_version()
    vlocs = {l["attributes"]["locale"]: l for l in
             call("GET", f'/appStoreVersions/{v["id"]}/appStoreVersionLocalizations')["data"]}
    base = vlocs["en-US"]["attributes"]
    info = editable_appinfo()
    ilocs = {l["attributes"]["locale"]: l for l in
             call("GET", f'/appInfos/{info["id"]}/appInfoLocalizations')["data"]}
    privacy = ilocs["en-US"]["attributes"].get("privacyPolicyUrl")
    for loc in locales:
        m = meta[loc]
        print(loc)
        if "name" in m:
            iattrs = {"name": m["name"], "subtitle": m["subtitle"], "privacyPolicyUrl": privacy}
            if loc in ilocs:
                call("PATCH", f'/appInfoLocalizations/{ilocs[loc]["id"]}', json={"data": {
                    "type": "appInfoLocalizations", "id": ilocs[loc]["id"], "attributes": iattrs}})
            else:
                call("POST", "/appInfoLocalizations", json={"data": {
                    "type": "appInfoLocalizations", "attributes": {"locale": loc, **iattrs},
                    "relationships": {"appInfo": {"data": {"type": "appInfos", "id": info["id"]}}}}})
            print("  name/subtitle set")
            # creating an appInfoLocalization auto-creates the version localization
            vlocs = {l["attributes"]["locale"]: l for l in
                     call("GET", f'/appStoreVersions/{v["id"]}/appStoreVersionLocalizations')["data"]}
            vattrs = {k: m[k] for k in ("description", "keywords", "promotionalText", "whatsNew")}
            vattrs["supportUrl"] = base.get("supportUrl")
            if base.get("marketingUrl"):
                vattrs["marketingUrl"] = base["marketingUrl"]
            if loc in vlocs:
                call("PATCH", f'/appStoreVersionLocalizations/{vlocs[loc]["id"]}', json={"data": {
                    "type": "appStoreVersionLocalizations", "id": vlocs[loc]["id"], "attributes": vattrs}})
            else:
                vlocs[loc] = call("POST", "/appStoreVersionLocalizations", json={"data": {
                    "type": "appStoreVersionLocalizations", "attributes": {"locale": loc, **vattrs},
                    "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": v["id"]}}}}})["data"]
            print("  description/keywords/whatsNew set")
        upload_shots(vlocs[loc]["id"], m["screenshots"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        status()
    elif cmd == "push":
        meta = json.load(open(os.path.join(HERE, "metadata.json")))
        push(sys.argv[2:] or [k for k in meta if not k.startswith("_")])
