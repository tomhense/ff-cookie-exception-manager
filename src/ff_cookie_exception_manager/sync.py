import argparse
import configparser
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Self

from ff_cookie_exception_manager import ff, logger, webdav


class Config:
    def __init__(self) -> None:
        self.config_dir = self.getXDGConfigHome() / "ff-cookie-exceptions-sync"
        self.config_path = self.config_dir / "config.ini"
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


def uploadSyncState(webdavClient: webdav.WebDAVClient, syncState: dict) -> None:
    # Upload the exceptions
    try:
        webdavClient.upload(
            "/ff-cookie-exceptions/sync.json",
            json.dumps(
                {
                    "syncDate": syncState["syncDate"],
                    "exceptionRules": syncState["exceptionRules"],
                },
                cls=ff.CustomEncoder,
                indent=4,
            ),
        )
    except webdav.Error as e:
        logger.error(f"Failed to upload sync file: {e.reason}")
        exit(1)


class Changes:
    def __init__(
        self,
        added: set[ff.CookieExceptionRule],
        removed: set[ff.CookieExceptionRule],
        modified: set[ff.CookieExceptionRule],
    ) -> None:
        self.added = added
        self.removed = removed
        self.modified = modified

    def removeRule(self, rule: ff.CookieExceptionRule) -> None:
        if rule in self.added:
            self.added.remove(rule)
        elif rule in self.removed:
            self.removed.remove(rule)
        elif rule in self.modified:
            self.modified.remove(rule)

    @classmethod
    def mergeChanges(cls, localChanges: Self, remoteChanges: Self) -> Self:
        # Be careful this method may modify the input sets

        # If a rule is in both local and remote changes, we need to compare their modification times and keep the most recent one
        for i in localChanges.added | localChanges.removed | localChanges.modified:
            for j in (
                remoteChanges.added | remoteChanges.removed | remoteChanges.modified
            ):
                if i.origin == j.origin:
                    if i.modificationTime > j.modificationTime:
                        remoteChanges.removeRule(j)
                    else:
                        localChanges.removeRule(i)

        return cls(
            localChanges.added | remoteChanges.added,
            localChanges.removed | remoteChanges.removed,
            localChanges.modified | remoteChanges.modified,
        )

    @classmethod
    def computeDiff(
        cls,
        newState: set[ff.CookieExceptionRule],
        oldState: set[ff.CookieExceptionRule],
    ) -> Self:
        modified = set()
        for i in newState:
            for j in oldState:
                if i != j and i.origin == j.origin:
                    modified.add(i)
        return cls(
            set(newState) - set(oldState), set(oldState) - set(newState), modified
        )


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
    with open(config.config_dir / "last_sync_state.json", "r") as file:
        local_sync_state = json.load(file)

    # Fetch the remote sync state
    remoteSyncState = downloadSyncState(webdavClient)

    # Compare the remote sync state with the last (local) sync state
    if local_sync_state["syncDate"] < remoteSyncState["syncDate"]:
        remoteChanges = Changes.computeDiff(
            set(local_sync_state["exceptionRules"]),
            set(remoteSyncState["exceptionRules"]),
        )
    else:
        logger.info("No remote changes")

    # Compare out ff exceptions with the last (local) sync state
    # Because we can't easily get the date of the last modification of the ff exceptions (well for the modifications we can but now for the removals), so we just asssume that they were just now modified
    localFFExceptions = ff.getExceptions(ffConn)
    localChanges = Changes.computeDiff(
        set(local_sync_state["exceptionRules"]), set(localFFExceptions)
    )

    # Merge the two sets of changes
    mergedChanges = Changes.mergeChanges(localChanges, remoteChanges)

    if not args.simulate:
        # Apply the merged changes to our local ff exceptions
        applyChanges(ffConn, mergedChanges)

        # Save our now modified last sync state to disk
        with open(config.config_dir / "last_sync_state.json", "w") as file:
            json.dump(mergedChanges, file, cls=ff.CustomEncoder, indent=4)

        # Upload our now modified last sync state to the remote
        uploadSyncState(webdavClient, mergedChanges)
