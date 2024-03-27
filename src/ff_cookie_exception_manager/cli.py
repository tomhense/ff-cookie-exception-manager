#!env python3
import argparse
import json
import os.path
import sqlite3
import sys
from pathlib import Path

from ff_cookie_exception_manager import ff, logger


def createParser():
    parser = argparse.ArgumentParser(
        description="Tool to manage cookie exceptions of a firefox profile"
    )
    parser.add_argument(
        "--profile-name",
        "-P",
        metavar="profile",
        help="Start with <profile>",
    )
    parser.add_argument(
        "--profile-path",
        metavar="path",
        type=str,
        help="Start with profile at <path>",
    )
    parser.add_argument(
        "--import",
        "-i",
        dest="import_file",
        type=str,
        metavar="file",
        help="Import exceptions from file or stdin",
    )
    parser.add_argument(
        "--export",
        "-e",
        dest="export_file",
        type=str,
        metavar="file",
        help="Export exceptions to file or stdout",
    )
    parser.add_argument("--list", "-l", action="store_true", help="List exceptions")
    parser.add_argument(
        "--clear", action="store_true", help="Clear all cookie exceptions"
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update existing cookie exceptions instead of skipping them while importing",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logger level",
    )
    return parser


def confirm(msg):
    userInput = input(msg)
    return userInput.lower() == "y"


def readRulesFromFile(filePath):
    if filePath != "-" and not os.path.isfile(filePath):
        logger.error("Given import file does not exist")
        exit(1)

    if filePath == "-":  # Read from stdin
        return json.loads(sys.stdin.read(), cls=ff.CustomDecoder)
    else:
        with open(filePath, "r") as importFile:
            return json.load(importFile, cls=ff.CustomDecoder)


def exportRulesToFile(filePath: Path, rules: list[ff.CookieExceptionRule]):
    if filePath == "-":  # Write to stdout
        sys.stdout.write(json.dumps(rules, cls=ff.CustomEncoder, indent=4))
    else:
        with open(filePath, "w") as exportFile:
            json.dump(rules, exportFile, cls=ff.CustomEncoder, indent=4)


def listExceptions(exceptions: list[ff.CookieExceptionRule]):
    for exception in exceptions:
        print(f"{exception.origin} {exception.permission} {exception.modificationTime}")


def main() -> None:
    parser = createParser()
    args = parser.parse_args()

    # Set the logger level
    logger.setLevel(args.log_level)

    profile: ff.FFProfile | None = None

    # Extract the firefox profile path by parsing arguments
    if args.profile_name is None and args.profile_path is None:  # Use default profile
        profile = ff.getDefaultProfile()

    elif args.profile_name is not None:  # Get profile by given profile name:
        profile = next(
            (i for i in ff.getProfiles() if i.path == args.profile_name), None
        )
        if profile is None:
            logger.error("No profile with that given name was found")
            exit(1)

    elif args.profile_path is not None:  # Get profile by given profile path
        if not os.path.isdir(args.profile_path):
            logger.error("Given profile path is not a directory")
            exit(1)
        profile = next(
            (i for i in ff.getProfiles() if i.path == args.profile_path), None
        )
        if profile is None:
            logger.error("No profile with that given path was found")
            exit(1)

    else:  # Error case
        logger.error("Please choose a profile either by name or by path")
        exit(1)

    # Open the database
    conn = ff.openDatabase(profile)

    try:
        # Execution of task
        if args.clear:  # Clear all cookie exceptions from database
            if confirm(
                "Do you really want to clear all cookie exception from this profile? (y/n) "
            ):
                ff.deleteAllExceptions(conn)
            else:
                logger.error("Aborted")
                exit(0)

        if args.import_file is not None:
            rules = readRulesFromFile(args.import_file)
            ff.importRules(conn, rules, args.update_existing)

        if args.list:
            listExceptions(ff.getExceptions(conn))

        if args.export_file is not None:
            rules = ff.getExceptions(conn)
            exportRulesToFile(args.export_file, rules)
    except sqlite3.OperationalError as err:
        logger.error(f"Database error: {err}")
        exit(1)


if __name__ == "__main__":
    main()
    main()
