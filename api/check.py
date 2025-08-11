import json
from urllib.parse import parse_qs

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


def handler(request, response):
    """Vercel serverless function handler"""
    try:
        # Set CORS headers
        response.setHeader('Access-Control-Allow-Origin', '*')
        response.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        response.setHeader('Access-Control-Allow-Headers', 'Content-Type')
        response.setHeader('Content-Type', 'application/json')

        # Handle CORS preflight
        if request.method == 'OPTIONS':
            response.status(200).end()
            return

        # Parse parameters based on method
        if request.method == 'POST':
            try:
                body = json.loads(request.body or '{}')
            except:
                body = {}
            username = body.get('username')
            sites = body.get('sites')
            include_nsfw = bool(body.get('nsfw', False))
            timeout = int(body.get('timeout', 30))
            proxy = body.get('proxy')
            json_file = body.get('json')
            max_sites = int(body.get('max_sites', 30))
            only_found = bool(body.get('only_found', True))
        else:  # GET
            query = request.query
            username = query.get('username')
            sites_raw = query.get('sites')
            sites = [s.strip() for s in sites_raw.split(",")] if sites_raw else None
            include_nsfw = query.get('nsfw', 'false').lower() == 'true'
            timeout = int(query.get('timeout', 30))
            proxy = query.get('proxy')
            json_file = query.get('json')
            max_sites = int(query.get('max_sites', 30))
            only_found = query.get('only_found', 'true').lower() == 'true'

        if not username:
            response.status(400).json({"error": "username is required"})
            return

        site_data = build_site_data(sites, include_nsfw, json_file)
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

        response.status(200).json(payload)

    except Exception as e:
        response.status(500).json({"error": str(e)})