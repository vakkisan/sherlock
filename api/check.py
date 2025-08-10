from flask import Flask, request, jsonify

from sherlock_project.sites import SitesInformation
from sherlock_project.sherlock import sherlock as run_sherlock
from sherlock_project.notify import QueryNotify


class QuietNotify(QueryNotify):
    def start(self, message=None):
        pass

    def update(self, result):
        self.result = result

    def finish(self, message=None):
        return 0


app = Flask(__name__)


def build_site_data(requested_sites, include_nsfw, json_url=None):
    sites = SitesInformation(json_url)
    if not include_nsfw:
        sites.remove_nsfw_sites(do_not_remove=(requested_sites or []))

    all_sites = {site.name: site.information for site in sites}
    if not requested_sites:
        return all_sites

    pruned, missing = {}, []
    for req in requested_sites:
        matched = next((name for name in all_sites if name.lower() == req.lower()), None)
        if matched:
            pruned[matched] = all_sites[matched]
        else:
            missing.append(req)

    if not pruned:
        raise ValueError(f"No valid sites from: {missing}")

    return pruned


def serialize_results(username, site_data, results):
    return {
        "username": username,
        "total_sites": len(site_data),
        "results": [
            {
                "site": site_name,
                "url_main": site_result.get("url_main"),
                "url_user": site_result.get("url_user"),
                "status": str(site_result["status"].status),
                "http_status": site_result.get("http_status"),
                "response_time_s": site_result["status"].query_time,
            }
            for site_name, site_result in results.items()
        ],
    }


@app.post("/")
def check_post():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    if not username:
        return jsonify({"error": "username is required"}), 400

    sites = data.get("sites") or None  # list[str], optional
    include_nsfw = bool(data.get("nsfw", False))
    timeout = int(data.get("timeout", 30))
    proxy = data.get("proxy")
    json_file = data.get("json")  # optional override for data.json (URL or local path)
    max_sites = int(data.get("max_sites", 30))
    only_found = bool(data.get("only_found", True))

    try:
        site_data = build_site_data(sites, include_nsfw, json_file)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if max_sites and len(site_data) > max_sites:
        site_data = dict(list(site_data.items())[:max_sites])

    results = run_sherlock(
        username=username,
        site_data=site_data,
        query_notify=QuietNotify(),
        proxy=proxy,
        timeout=timeout,
    )
    payload = serialize_results(username, site_data, results)
    if only_found:
        payload["results"] = [r for r in payload["results"] if r["status"] == "Claimed"]
    return jsonify(payload), 200


@app.get("/")
def check_get():
    username = request.args.get("username")
    if not username:
        return jsonify({"error": "username is required"}), 400

    sites_raw = request.args.get("sites")
    sites = [s.strip() for s in sites_raw.split(",")] if sites_raw else None
    include_nsfw = request.args.get("nsfw", "false").lower() == "true"
    timeout = int(request.args.get("timeout", 30))
    proxy = request.args.get("proxy")
    json_file = request.args.get("json")
    max_sites = int(request.args.get("max_sites", 30))
    only_found = request.args.get("only_found", "true").lower() == "true"

    try:
        site_data = build_site_data(sites, include_nsfw, json_file)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if max_sites and len(site_data) > max_sites:
        site_data = dict(list(site_data.items())[:max_sites])

    results = run_sherlock(
        username=username,
        site_data=site_data,
        query_notify=QuietNotify(),
        proxy=proxy,
        timeout=timeout,
    )
    payload = serialize_results(username, site_data, results)
    if only_found:
        payload["results"] = [r for r in payload["results"] if r["status"] == "Claimed"]
    return jsonify(payload), 200


# Exported `app` is discovered by Vercel's Python runtime


