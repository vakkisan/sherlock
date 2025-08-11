from http.server import BaseHTTPRequestHandler
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Parse query parameters
            if '?' in self.path:
                _, query_string = self.path.split('?', 1)
                query = parse_qs(query_string)
            else:
                query = {}

            username = query.get('username', [None])[0]
            if not username:
                self.send_error_response(400, {"error": "username is required"})
                return

            sites_raw = query.get('sites', [None])[0]
            sites = [s.strip() for s in sites_raw.split(",")] if sites_raw else None
            include_nsfw = query.get('nsfw', ['false'])[0].lower() == 'true'
            timeout = int(query.get('timeout', ['30'])[0])
            proxy = query.get('proxy', [None])[0]
            json_file = query.get('json', [None])[0]
            max_sites = int(query.get('max_sites', ['30'])[0])
            only_found = query.get('only_found', ['true'])[0].lower() == 'true'

            # Process request
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

            self.send_json_response(200, payload)

        except Exception as e:
            self.send_error_response(500, {"error": str(e)})

    def do_POST(self):
        try:
            # Read POST body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                data = json.loads(body) if body else {}
            except:
                data = {}

            username = data.get('username')
            if not username:
                self.send_error_response(400, {"error": "username is required"})
                return

            sites = data.get('sites')
            include_nsfw = bool(data.get('nsfw', False))
            timeout = int(data.get('timeout', 30))
            proxy = data.get('proxy')
            json_file = data.get('json')
            max_sites = int(data.get('max_sites', 30))
            only_found = bool(data.get('only_found', True))

            # Process request
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

            self.send_json_response(200, payload)

        except Exception as e:
            self.send_error_response(500, {"error": str(e)})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def send_error_response(self, status_code, error_data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(error_data).encode('utf-8'))