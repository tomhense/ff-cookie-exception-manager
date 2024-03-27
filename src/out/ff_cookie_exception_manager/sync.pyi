from _typeshed import Incomplete
from ff_cookie_exception_manager import ff as ff, logger as logger
from pathlib import Path

class Config:
    config_path: Incomplete
    config: Incomplete
    def __init__(self) -> None: ...
    def getXDGConfigHome(self) -> Path: ...

def main() -> None: ...
