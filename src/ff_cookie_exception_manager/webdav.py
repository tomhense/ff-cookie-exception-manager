import os.path

import requests


class Error(Exception):
    def __init__(self, response: requests.Response):
        self.response = response
        self.status_code = response.status_code
        self.reason = response.reason
        self.text = response.text


class WebDAVClient:
    session = requests.Session()

    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password
        self.session.auth = (self.username, self.password)

    def selfcheck(self) -> bool:
        response = self.session.request("PROPFIND", self.url)

        # 207 Multi-Status is the expected response
        return response.status_code == 207

    def list(self, path) -> str:
        response = self.session.request("PROPFIND", self.url + path)
        return response.text

    def upload(self, path, text) -> None:
        # Chunked upload is not supported
        response = self.session.request(
            "PUT",
            self.url + path,
            data=text,
            headers={"Content-Type": "text/plain"},
        )
        if response.status_code != 201:
            raise Error(response)

    def download(self, path) -> str:
        response = self.session.request("GET", self.url + path)
        if response.status_code == 200:
            return response.text
        else:
            raise Error(response)

    def delete(self, path) -> int:
        response = self.session.request("DELETE", self.url + path)
        return response.status_code

    def mkdir(self, path) -> int:
        response = self.session.request("MKCOL", self.url + path)
        return response.status_code

    def rmdir(self, path) -> int:
        if not os.path.isdir(path):
            raise FileNotFoundError(f"Directory {path} does not exist")
        response = self.session.request("DELETE", self.url + path)
        return response.status_code
