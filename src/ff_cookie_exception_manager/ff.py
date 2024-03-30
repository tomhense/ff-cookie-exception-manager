import configparser
import json
import os.path
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path

from ff_cookie_exception_manager import logger

"""
What to insert in table moz_perms:

id: automanaged by database
origin: host (e.g. https://duckduckgo.com)
type: cookie
permission: 8 (for session) or 1 (for indefinite)
expireType: 0
expireTime: 0
modificationTime: unix epoch in ms
"""


class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, CookieExceptionRule):
            return o.to_dict()
        elif isinstance(o, FFProfile):
            return o.to_dict()
        return super().default(o)


class CustomDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        super().__init__(object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, d):
        if "origin" in d:
            return CookieExceptionRule.from_dict(d)
        elif "name" in d:
            return FFProfile.from_dict(d)
        return d


class FFProfile:
    def __init__(
        self, name: str, path: Path, isDefault: bool, isRelative: bool
    ) -> None:
        self.name = name
        self.path = path
        self.isDefault = isDefault
        self.isRelative = isRelative

    def getPermissionDatabasePath(self) -> Path:
        dbPath = self.path / "permissions.sqlite"
        if not dbPath.is_file():
            logger.error(f"Database file {dbPath} does not exist")
            exit(1)
        return dbPath

    def to_dict(self):
        return {
            "name": self.name,
            "path": str(self.path),
            "isDefault": self.isDefault,
            "isRelative": self.isRelative,
        }

    def __str__(self) -> str:
        return (
            f"FFProfile({self.name}, {self.path}, {self.isDefault}, {self.isRelative})"
        )

    @classmethod
    def from_dict(cls, d):
        return cls(d["name"], Path(d["path"]), d["isDefault"], d["isRelative"])


class CookieExceptionRule:
    class Permission(Enum):
        ALWAYS = 1
        SESSION = 8

    def __init__(
        self,
        origin: str,
        permission: Permission,
        modificationTime: datetime,
    ) -> None:
        self.origin = origin
        self.permission = permission
        self.modificationTime = modificationTime
        self.modificationTimestamp = int(modificationTime.timestamp() * 1000)

    def verify(self):
        # Check if permission has a valid value
        if self.permission not in ("always", "session"):
            return False

        # Check if origin is a valid URL (not perfect, but good enough for now)
        if "://" not in self.origin:
            return False

        # Check if the modificationTime lies lies within a reasonable range
        if self.modificationTime.year < 2000 or self.modificationTime.year > 2050:
            return False

        return True

    def __str__(self) -> str:
        return f"CookieExceptionRule({self.origin}, {self.permission}, {self.modificationTime})"

    def to_dict(self):
        return {
            "origin": self.origin,
            "permission": self.permission.name,
            "modificationTime": self.modificationTime.isoformat(),
        }

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __hash__(self):
        return hash((self.origin, self.permission, self.modificationTime))

    @classmethod
    def from_dict(cls, d):
        return cls(
            d["origin"],
            cls.Permission(d["permission"]),
            datetime.fromisoformat(d["modificationTime"]),
        )


def openDatabase(profile: FFProfile) -> sqlite3.Connection:
    conn = sqlite3.connect(profile.getPermissionDatabasePath())
    conn.row_factory = sqlite3.Row  # Enable dict based indexing
    return conn


def getProfiles() -> list[FFProfile]:
    firefoxDirectory = os.path.expanduser("~/.mozilla/firefox")
    config = configparser.ConfigParser()
    config.read(os.path.join(firefoxDirectory, "profiles.ini"))

    profiles = []
    for section in config.sections():
        if section.startswith("Profile") and config[section].get("Name") is not None:
            profilePath = Path(config[section]["Path"])
            profileIsRelative = (
                config[section]["IsRelative"] == "1"
            )  # 1=relative,0=absoute
            if profileIsRelative:
                profilePath = firefoxDirectory / profilePath

            profiles.append(
                FFProfile(
                    config[section]["Name"],
                    profilePath,
                    config[section].get("Default") == "1",
                    profileIsRelative,
                )
            )
    return profiles


def getDefaultProfile() -> FFProfile:
    profiles = getProfiles()
    defaultProfiles = list(filter(lambda x: x.isDefault, profiles))

    if len(defaultProfiles) == 0:
        logger.error("No default profile found")
        exit(1)
    elif len(defaultProfiles) > 1:
        logger.error("Ambigious default profile")
        exit(1)

    return defaultProfiles[0]


def importRules(
    conn: sqlite3.Connection,
    rules: list[CookieExceptionRule],
    updateExisting: bool = False,
) -> None:
    cursor = conn.cursor()

    # Verify the rules
    for rule in rules:
        if not rule.verify():
            logger.error(f"Invalid rule {rule}")
            exit(1)

    # Insert or update the rules
    for rule in rules:
        cursor.execute(
            "SELECT origin FROM moz_perms WHERE type = 'cookie' AND origin = ?",
            [rule.origin],
        )
        if cursor.fetchone() is None:  # No cookie exception exists for this host
            logger.info(f"Imporing rule {rule}")
            cursor.execute(
                "INSERT INTO moz_perms(origin,type,permission,expireType,expireTime,modificationTime) VALUES(?,'cookie',?,0,0,?)",
                [rule.origin, rule.permission.value, rule.modificationTimestamp],
            )
        elif updateExisting:  # Update existing cookie exception
            logger.info(f"Updating rule {rule}")
            cursor.execute(
                "UPDATE moz_perms set permission = ?, modificationTime = ? WHERE type = 'cookie' AND origin=?",
                [rule.permission.value, rule.modificationTimestamp, rule.origin],
            )
        else:  # Skip
            logger.info(f"Skipping rule {rule}")


def getExceptions(conn: sqlite3.Connection) -> list[CookieExceptionRule]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT origin,permission,modificationTime FROM moz_perms WHERE type = 'cookie'"
    )

    exceptions = []
    for entry in cursor.fetchall():
        if entry["permission"] not in (1, 8):
            logger.error(
                "Unknown value in permission attribute, please contact the developer"
            )
        exceptions.append(
            CookieExceptionRule(
                entry["origin"],
                CookieExceptionRule.Permission(entry["permission"]),
                datetime.fromtimestamp(entry["modificationTime"] / 1000),
            )
        )
    return exceptions


def deleteAllExceptions(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    deletedCount = cursor.execute(
        "DELETE FROM moz_perms WHERE type = 'cookie'"
    ).rowcount
    conn.commit()  # Save changes
    logger.info(f"Successfully deleted {deletedCount} cookie exceptions")


def replaceRules(conn: sqlite3.Connection, rules: list[CookieExceptionRule]) -> None:
    assert len(rules) > 0, "No rules provided"  # Sanity check

    cursor = conn.cursor()
    cursor.execute("DELETE FROM moz_perms WHERE type = 'cookie'")
    cursor.executemany(
        "INSERT INTO moz_perms(origin,type,permission,expireType,expireTime,modificationTime) VALUES(?, 'cookie', ?, 0, 0, ?)",
        [
            (rule.origin, rule.permission.value, rule.modificationTimestamp)
            for rule in rules
        ],
    )
    conn.commit()  # Save changes
    logger.info("Successfully replaced all cookie exceptions")
