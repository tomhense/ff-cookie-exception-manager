import argparse
import configparser
import importlib.resources
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from ff_cookie_exception_manager import ff, logger, webdav


class Config:
    def __init__(self) -> None:
        self.config_dir = self.getXDGConfigHome() / "ff-cookie-exceptions-sync"
        self.config_path = self.config_dir / "config.ini"

        if not os.path.exists(self.config_dir):
            os.mkdir(self.config_dir)
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w") as file:
                file.write(
                    importlib.resources.read_text(
                        "ff_cookie_exception_manager", "config.ini"
                    )
                )

        self.config = configparser.ConfigParser()
        self.config.read(self.config_path)

    def getXDGConfigHome(self) -> Path:
        # Cross platform XDG compliant config location detection
        XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME")
        if XDG_CONFIG_HOME is None:
            XDG_CONFIG_HOME = "~/.config"
        return Path(os.path.expanduser(XDG_CONFIG_HOME))

    def get(self, section: str, option: str) -> str:
        return self.config.get(section, option)

    def set(self, section: str, option: str, value: str) -> None:
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, option, value)


def createParser():
    parser = argparse.ArgumentParser(description="Sync firefox cookie exceptions")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logger level",
    )
    parser.add_argument(
        "--simulate",
        "-n",
        action="store_true",
        help="Only simulate, do not change anything",
    )
    return parser


def getFFProfile(config: Config) -> ff.FFProfile:
    profileName = config.get("firefox", "profile_name")
    profilePath = config.get("firefox", "profile_path")

    # Extract the firefox profile path by parsing arguments
    if profileName is None and profilePath is None:  # Use default profile
        profile = ff.getDefaultProfile()

    elif profileName is not None:  # Get profile by given profile name:
        profile = next(
            (i for i in ff.getProfiles() if i.path == profileName),
            None,
        )
        if profile is None:
            logger.error("No profile with that given name was found")
            exit(1)

    elif profilePath is not None:  # Get profile by given profile path
        if not os.path.isdir(profilePath):
            logger.error("Given profile path is not a directory")
            exit(1)
        profile = next((i for i in ff.getProfiles() if i.path == profilePath), None)
        if profile is None:
            logger.error("No profile with that given path was found")
            exit(1)
    else:
        logger.error("Invalid profile configuration")
        exit(1)

    return profile


def createSyncDir(webdavClient: webdav.WebDAVClient) -> None:
    # Create the sync directory if it does not exist
    try:
        webdavClient.mkdir("/ff-cookie-exceptions")
    except webdav.Error as e:
        if e.status_code == 405:
            logger.error("WebDAV server does not support MKCOL")
            exit(1)
        elif e.status_code == 409:
            pass
        else:
            logger.error(f"Failed to create sync directory: {e.reason}")
            exit(1)


def downloadSyncState(webdavClient: webdav.WebDAVClient) -> dict:
    # Download the exceptions file
    try:
        resp_text = webdavClient.download("/ff-cookie-exceptions/sync.json")
    except webdav.Error as e:
        if e.status_code == 404:
            logger.error("No sync file found")
            exit(1)
        else:
            logger.error(f"Failed to download sync file: {e.reason}")
            exit(1)

    # Parse the exceptions file
    syncState = json.loads(resp_text, cls=ff.CustomDecoder)
    return syncState


def uploadSyncState(
    webdavClient: webdav.WebDAVClient,
    syncState: dict,
    path: str = "/ff-cookie-exceptions/sync.json",
) -> None:
    # Upload the exceptions
    try:
        webdavClient.upload(
            path,
            json.dumps(
                syncState,
                cls=ff.CustomEncoder,
                indent=4,
            ),
        )
    except webdav.Error as e:
        logger.error(f"Failed to upload sync file: {e.reason}")
        exit(1)


def backupSyncStateRemote(webdavClient: webdav.WebDAVClient) -> None:
    # Not used currently
    try:
        sync_state = downloadSyncState(webdavClient)
        iso_date = datetime.now().isoformat()[:19].replace(":", "-")
        uploadSyncState(
            webdavClient,
            sync_state,
            path=f"/ff-cookie-exceptions/backups/backup_{iso_date}.json",
        )

    except webdav.Error as e:
        logger.error(f"Failed to upload sync file: {e.reason}")
        exit(1)


def intervalToSeconds(interval: str) -> int:
    if interval[-1] == "s":
        return int(interval[:-1])
    elif interval[-1] == "m":
        return int(interval[:-1]) * 60
    elif interval[-1] == "h":
        return int(interval[:-1]) * 60 * 60
    elif interval[-1] == "d":
        return int(interval[:-1]) * 60 * 60 * 24
    else:
        logger.error("Invalid interval")
        exit(1)


def backupSyncState(config_dir: Path, sync_interval: str) -> None:
    if not os.path.exists(config_dir / "backups"):
        os.mkdir(config_dir / "backups")

    # Check if the mtime of the backup directory is older than the interval
    mtime = os.path.getmtime(config_dir / "backups")
    if datetime.now().timestamp() - mtime > intervalToSeconds(sync_interval):
        logger.info("Making backup")
        assert os.path.exists(
            config_dir / "last_sync_state.json"
        ), "No last sync state found"

        iso_date = datetime.now().isoformat()[:19].replace(":", "-")
        shutil.copyfile(
            config_dir / "last_sync_state.json",
            config_dir / "backups" / f"backup_{iso_date}.json",
        )
    else:
        logger.info("Backup interval not reached")


def mergeChanges(
    mergeStatergy: str, local_state: dict, remote_state: dict
) -> dict | None:
    if mergeStatergy == "use_newest":
        if local_state["syncDate"] > remote_state["syncDate"]:
            return local_state
        else:
            return remote_state
    elif mergeStatergy == "use_local":
        return local_state
    elif mergeStatergy == "use_remote":
        return remote_state
    elif mergeStatergy == "do_nothing":
        return None
    else:
        logger.error("Invalid merge statergy")
        exit(1)


def saveLastSyncState(config: Config, syncState: dict) -> None:
    with open(config.config_dir / "last_sync_state.json", "w") as file:
        json.dump(syncState, file, cls=ff.CustomEncoder, indent=4)


def main() -> None:
    parser = createParser()
    args = parser.parse_args()

    # Set the logger level
    logger.setLevel(args.log_level)

    config = Config()

    ffProfile = getFFProfile(config)
    ffConn = ff.openDatabase(ffProfile)

    webdavClient = webdav.WebDAVClient(
        config.get("webdav", "url"),
        config.get("webdav", "username"),
        config.get("webdav", "password"),
    )

    if not webdavClient.selfcheck():
        logger.error("WebDAV server selfcheck failed")
        exit(1)

    createSyncDir(webdavClient)

    # Fetch the last sync state from disk
    if os.path.exists(config.config_dir / "last_sync_state.json"):
        with open(config.config_dir / "last_sync_state.json", "r") as file:
            last_sync_state = json.load(file)
    else:
        logger.info(
            "No last sync state found, using empty state (that will be replaced by remote state)"
        )
        last_sync_state = {
            "syncDate": datetime(1970, 1, 1).isoformat(),
            "exceptionRules": ff.getExceptions(ffConn),
        }

    local_state = {
        "syncDate": datetime.now().isoformat(),
        "exceptionRules": ff.getExceptions(ffConn),
    }

    # Are there any new local changes?
    new_local_changes = set(last_sync_state["exceptionRules"]) != set(
        local_state["exceptionRules"]
    )

    # Fetch the remote sync state
    remote_state = downloadSyncState(webdavClient)

    # Handle possible panic states
    panic_detected = False
    if len(remote_state["exceptionRules"]) == 0:
        logger.error("Remote sync file is empty")
        panic_detected = True
    if len(local_state["exceptionRules"]) == 0:
        logger.error("Local sync file is empty")
        panic_detected = True
    if config.get("sync", "panic") and panic_detected:
        logger.error("Panic detected, exiting")
        exit(1)

    if last_sync_state["syncDate"] < remote_state["syncDate"] and not new_local_changes:
        # Replace local rules with remote rules
        logger.info("Remote changes")
        if not args.simulate:
            ff.replaceRules(ffConn, remote_state["exceptionRules"])
            saveLastSyncState(config, local_state)
    elif local_state["syncDate"] < remote_state["syncDate"] and new_local_changes:
        # Merge local changes with remote rules by using the specified merge strategy (e.g. use newest)
        logger.info("Remote changes and local changes, using specified merge strategy")
        merged_state = mergeChanges(
            config.get("sync", "merge_statergy"), local_state, remote_state
        )
        if merged_state is None:
            logger.info("Do nothing")
        elif not args.simulate:
            ff.replaceRules(ffConn, merged_state["exceptionRules"])
            uploadSyncState(webdavClient, merged_state)
            saveLastSyncState(config, local_state)
    elif local_state["syncDate"] == remote_state["syncDate"] and not new_local_changes:
        # Do nothing
        logger.info("No remote changes and no local changes")
        exit(0)
    elif local_state["syncDate"] == remote_state["syncDate"] and new_local_changes:
        # Upload local changes to remote
        logger.info("No remote changes but local changes")
        if not args.simulate:
            uploadSyncState(webdavClient, local_state)
            saveLastSyncState(config, local_state)
    else:
        logger.error("Impossible state reached")
        exit(1)

    # Make backups
    if config.get("backup", "enabled"):
        logger.info("Making backup")
        backupSyncState(config.config_dir, config.get("backup", "interval"))
