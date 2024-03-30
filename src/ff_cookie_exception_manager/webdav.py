import os.path

import requests

from ff_cookie_exception_manager import logger


class Error(Exception):
    def __init__(self, response: requests.Response):
        self.response = response
        self.status_code = response.status_code
        self.reason = response.reason
        self.text = response.text


class WebDAVClient:
    session = requests.Session()

    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.session.auth = (self.username, password)
        logger.debug(f"WebDAV client initialized: {self.url}")

    def selfcheck(self) -> bool:
        response = self.session.request("PROPFIND", self.url, headers={"Depth": "0"})

        logger.debug(f"WebDAV selfcheck: {response.status_code} {response.reason}")

        # 207 Multi-Status is the expected response
        return response.status_code == 207

    def list(self, path: str) -> str:
        response = self.session.request("PROPFIND", self.url + path)
        return response.text

    def upload(self, path: str, data: str) -> None:
        # Chunked upload is not supported
        response = self.session.request(
            "PUT",
            self.url + path,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code not in [201, 204]:
            raise Error(response)

    def download(self, path: str) -> str:
        response = self.session.request("GET", self.url + path)
        if response.status_code == 200:
            return response.text
        else:
            raise Error(response)

    def delete(self, path: str) -> int:
        response = self.session.request("DELETE", self.url + path)
        return response.status_code

    def mkdir(self, path: str) -> int:
        response = self.session.request("MKCOL", self.url + path)
        return response.status_code

    def rmdir(self, path: str) -> int:
        if not os.path.isdir(path):
            raise FileNotFoundError(f"Directory {path} does not exist")
        response = self.session.request("DELETE", self.url + path)
        return response.status_code
