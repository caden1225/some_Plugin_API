"""
A web search server for ParlAI, including Blenderbot2.
See README.md
"""
import html
import http.server
import json
import re
from typing import *
import urllib.parse

import bs4
import chardet
import fire
import html2text
import parlai.agents.rag.retrieve_api
import rich
import rich.markup
import requests

print = rich.print

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 8080
_STYLE_GOOD = "[green]"
_STYLE_SKIP = ""
_CLOSE_STYLE_GOOD = "[/]" if _STYLE_GOOD else ""
_CLOSE_STYLE_SKIP = "[/]" if _STYLE_SKIP else ""
_requests_get_timeout = 5  # seconds
_strip_html_menus = False
_max_text_bytes = None

# To get a free Bing Subscription Key go here:
#    https://www.microsoft.com/en-us/bing/apis/bing-entity-search-api
_use_bing_description_only = False  # short but 10X faster


def _parse_host(host: str) -> Tuple[str, int]:
    """ Parse the host string. 
    Should be in the format HOSTNAME:PORT. 
    Example: 0.0.0.0:8080
    """
    splitted = host.split(":")
    hostname = splitted[0]
    port = splitted[1] if len(splitted) > 1 else _DEFAULT_PORT
    return hostname, int(port)


class SearchABC(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _strip_html_menus, _max_text_bytes, _use_bing_description_only

        """ Handle POST requests from the client. (All requests are POST) """

        #######################################################################
        # Prepare and Parse
        #######################################################################
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)

        # Figure out the encoding
        if "charset=" in self.headers["Content-Type"]:
            charset = re.match(r".*charset=([\w_\-]+)\b.*", self.headers["Content-Type"]).group(1)
        else:
            detector = chardet.UniversalDetector()
            detector.feed(post_data)
            detector.close()
            charset = detector.result["encoding"]

        post_data = post_data.decode(charset)
        parsed = urllib.parse.parse_qs(post_data)

        for v in parsed.values():
            assert len(v) == 1, len(v)
        parsed = {k: v[0] for k, v in parsed.items()}

        #######################################################################
        # Search, get the pages and parse the content of the pages
        #######################################################################

        print(
            f"\n[bold]Received query:[/] {parsed}, using bing search engine and using bing link descriptions only {_use_bing_description_only}")

        n = int(parsed["n"])
        q = parsed["q"]

        # Over query a little in case we find useless URLs
        result_list = []
        results = self.search_bing(q, n, _use_bing_description_only)

        if not results:
            logging.warning(
                f'Server search did not produce any results for "{q}" query.'
                ' returning an empty set of results for this query.'
            )
            return None

        for rd in results:
            url = rd.get('url', '')
            title = rd.get('name', '')
            sentences = [s.strip() for s in rd['snippet'].split('\n') if s and s.strip()]
            result_list.append(
                self.create_content_dict(url=url, title=title, content=sentences)
            )

        output = json.dumps(result_list).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", len(output))
        self.end_headers()
        self.wfile.write(output)

    @staticmethod
    def search_bing(
            query: str, n: int, _use_bing_description_only
    ):

        global _bing_subscription_key

        assert _bing_subscription_key

        search_url = "https://api.bing.microsoft.com/v7.0/search"
        print(f"n={n} responseFilter=webPages")

        headers = {"Ocp-Apim-Subscription-Key": _bing_subscription_key,
                   'Accept-Language': 'English'}
        params = {"q": query, 'count': n,
                  'cc': 'US', 'ensearch': '1',
                  "textDecorations": True, "textFormat": "HTML", "responseFilter": "webPages"}

        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status()
        search_results = response.json().get('webPages').get('value')

        return search_results

    def create_content_dict(self, content: list, **kwargs) -> Dict:
        resp_content = {'snippet': content}
        resp_content.update(**kwargs)
        return resp_content


class Application:
    def serve(
            self, host: str = _DEFAULT_HOST,
            requests_get_timeout=_requests_get_timeout,
            strip_html_menus=_strip_html_menus,
            max_text_bytes=_max_text_bytes,
            use_bing_description_only=_use_bing_description_only,
            bing_subscription_key=None) -> NoReturn:
        global _requests_get_timeout, _strip_html_menus, _max_text_bytes
        global _use_bing_description_only, _bing_subscription_key

        """ Main entry point: Start the server.
        Arguments:
            host (str):
            requests_get_timeout (int):
            strip_html_menus (bool):
            max_text_bytes (int):
            use_bing (bool):
            use_bing_description_only (bool):
               use_bing_description_only are short but 10X faster since no url gets
        bing_subscription_key required to use bing. Can get one at:
            https://www.microsoft.com/en-us/bing/apis/bing-entity-search-api
        """

        hostname, port = _parse_host(host)
        host = f"{hostname}:{port}"

        _requests_get_timeout = requests_get_timeout
        _strip_html_menus = strip_html_menus
        _max_text_bytes = max_text_bytes
        _use_bing_description_only = use_bing_description_only
        _bing_subscription_key = bing_subscription_key

        with http.server.ThreadingHTTPServer(
                (hostname, int(port)), SearchABC
        ) as server:
            print("Serving forever.")
            print(f"Host: {host}")
            server.serve_forever()

    @staticmethod
    def test_server(
            query: str, n: int, host: str = _DEFAULT_HOST,
            requests_get_timeout=_requests_get_timeout,
            strip_html_menus=_strip_html_menus,
            max_text_bytes=_max_text_bytes,
            use_bing_description_only=_use_bing_description_only,
            bing_subscription_key=None
    ) -> None:
        global _requests_get_timeout, _strip_html_menus, _max_text_bytes
        global _use_bing_description_only

        """ Creates a thin fake client to test a server that is already up.
        Expects a server to have already been started with `python search_server.py serve [options]`.
        Creates a retriever client the same way ParlAi client does it for its chat bot, then
        sends a query to the server.
        """
        host, port = _parse_host(host)

        _requests_get_timeout = requests_get_timeout
        _strip_html_menus = strip_html_menus
        _max_text_bytes = max_text_bytes
        _use_bing_description_only = use_bing_description_only

        print(f"Query: `{query}`")
        print(f"n: {n}")

        retriever = parlai.agents.rag.retrieve_api.SearchEngineRetriever(
            dict(
                search_server=f"{host}:{port}",
                skip_retrieval_token=False,
            )
        )
        print("Retrieving one.")
        print(retriever.retrieve([query], n))
        print("Done.")


if __name__ == "__main__":
    fire.Fire(Application)
