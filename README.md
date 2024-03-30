# FF-Cookie-Exception-Manager

Because firefox does not sync cookie exceptions (see these [1](https://bugzilla.mozilla.org/show_bug.cgi?id=978010) [2](https://bugzilla.mozilla.org/show_bug.cgi?id=1662804) years old bug reports on this) I created a small python cli tool to manage and synchronize these exception rules to webdav.

## Disclainer

I am not responsible for data loss (your cookie exceptions rules) that may occur when using this tool. Please make backups of your profile folder and/or use the the backup functionality of the manage tool. While I tested this software myself I can not completly rule any major bugs. Syncing data is always dangerous so make backups and be aware what you are doing.

## Installation

#### Installation using .whl file

1. Download the `.whl` file from the releases
2. Use `pipx install` or `pip install` to install the wheel file

#### Installation from source

1. Clone the code using `git clone`
2. Chdir into the directory and execute `python -m build`
   - You will need the `build` and `requests` library, either install these directly or install them in a venv
3. The wheel file will be created in the `dist` directory, use `pipx install` or `pip install` to install it

## Manage tool

- Can import & export exceptions (use - to output to stdout)
- Can clear all the exceptoins (Be cautious when using this!)
- For normal setups it should directly detect the correct profile if not you may have to use the profile name or profile path arguments
  - Profile info can be found in `~/.mozilla/firefox/profiles.ini`

```plaintext
usage: ff-cookie-exception-manager [-h] [--profile-name profile]
                                   [--profile-path path] [--import file]
                                   [--export file] [--clear]
                                   [--update-existing]
                                   [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]

Tool to manage cookie exceptions of a firefox profile

options:
  -h, --help            show this help message and exit
  --profile-name profile, -P profile
                        Start with <profile>
  --profile-path path   Start with profile at <path>
  --import file, -i file
                        Import exceptions from file or stdin
  --export file, -e file
                        Export exceptions to file or stdout
  --clear               Clear all cookie exceptions
  --update-existing     Update existing cookie exceptions instead of skipping
                        them while importing
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Set the logger level
```

## Sync tool

- **Be aware when adding a new device to a existing sync setup, if the new device already has existing rules the (specified) merge stratergy will be used. This may delete this devices / the remotes cookie exception rules**
  - Either manually solve this merge issue (complicated!) or simply clear the devices exceptions rules using the manage tool and then run the sync tool
- It is very advisable to test this tool using the `--simulate` and `--log-level DEBUG` flags first before syncing actual data
- The sync tool will periodically make backups (if enabled) after a specified period of time after the last backup has elapsed (it should also create a first backup when creating the backup folder)
  - The backup folder is located in the same directory as the config file is

```plaintext
usage: ff-cookie-exception-manager-sync [-h]
                                        [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                                        [--simulate]

Sync firefox cookie exceptions

options:
  -h, --help            show this help message and exit
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Set the logger level
  --simulate, -n        Only simulate, do not change anything
```

## Config file

- Currently only used be the sync tool
- This template whill automatically be installed on the first sync run
- Some of the firefox options are commented out so that the automatic detection is used instead
- The sync tool will create a new directory on the webdav server where it will store its files
- The config file is located at `~/.config/ff-cookie-exceptions-sync/config.ini`
  - XDG convections are respected
  - On windows this path will be `C:\Users\SOMEUSER\.config\ff-cookie-exceptions-sync\config.ini`

```conf
# Firefox profile configuration
[firefox]
#profile_name = default
#profile_path = /home/user/.mozilla/firefox/xxxxx.default

# Webdav server configuration
[webdav]
url = https://webdav.com
username = user
password = password

# Sync configuration
[sync]
panic = yes # Enter a panic state if encountering empty rules or missing files (disabling this is dangerous)
merge_strategy = use_newest # use_local, use_newest, use_remote, do_nothing

# Make periodic local backups of the sync state
[backup]
enabled = yes
interval = 1d # d, m, h, s supported
```
