# licenseMonitor V1.3.2

## Update history
***
| Version | Date      | Update content                                                   |
|:--------|:----------|:-----------------------------------------------------------------|
| V1.0    | (2023.01) | Release original version.                                        |
| V1.1    | (2023.07) | Add tool bin/license_sample.                                     |
|         |           | Add UTILIZATION/COST tab.                                        |
| V1.2    | (2023.11) | Add log search function on FEATURE/USAGE tabs.                   |
|         |           | Add feature/product filter function on UTILIZATION/COST tabs.    |
|         |           | Add tool tools/gen_LM_LICENSE_FILE.py.                           |
| V1.3    | (2023.12) | Add CURVE tab.                                                   |
|         |           | Add logo and menu icons.                                         |
|         |           | Add tools tools/update_*.py.                                     |
| V1.3.1  | (2024.03) | Add license file search function on EXPIRES tab.                 |
|         |           | Add license log search function on UTILIZATION/COST tabs.        |
|         |           | Add product fast fuzzy search function on UTILIZATION/COST tabs. |
|         |           | Add tools tools/*.                                               |
| V1.3.2  | (2024.06) | Replace export file from excel to csv file.                      |


## Introduction
***

### 0. What is licenseMonitor?
licenseMonitor is an open source software for EDA license information data-collection,
data-analysis and data-display.

### 1. Python dependency
Need python3.8.8, Anaconda3-2021.05-Linux-x86_64.sh is better.
Install python library dependency with command

    pip install -r requirements.txt

### 2. Install
Copy install package into install directory.
Execute below command under install directory.

    python3 install.py

### 3. Config
  - $MONITOR_VIEWER_INSTALL_PATH/config/config.py : top configuration file for licenseMonitor.
  - $MONITOR_VIEWER_INSTALL_PATH/config/LM_LICENSE_FILE : LM_LICENSE_FILE list.
  - $MONITOR_VIEWER_INSTALL_PATH/config/cost : cost related settings.
  - $MONITOR_VIEWER_INSTALL_PATH/config/others : license log and product_feature related settings.
  - $MONITOR_VIEWER_INSTALL_PATH/config/project : project related settigns.
  - $MONITOR_VIEWER_INSTALL_PATH/config/utilization : utilization related settings.

### 4. Sample
  - Sample EDA license information with tool bin/license_sample.

### 5. LOG CURVE tab
  - Show license usage curve parsed from license manager debug log (license.log).
  - License servers and license log paths are specified manually in an init file,
    one server per line with format:

        MasterServer:/apps/eda/license.log

  - The init file path is set by "license_log_server_init_file" in config/config.py,
    default is config/others/license_log_server.init
    (see config/others/license_log_server.init.example).

#### 5.1 Split collector/GUI deployment (GUI host without SSH access)

The GUI host may have no SSH access to license servers (for example when the GUI
runs on server A and only server B can reach the license servers).  LOG CURVE
supports a split deployment:

  - Collector host (server B, has SSH access to license servers): run
    bin/license_sample with cron.  It reads every log listed in
    license_log_server.init over SSH and stores OUT/IN events as csv data,
    one directory per log file:

        db/license_log/<log file name>/events.csv     (all OUT/IN events)
        db/license_log/<log file name>/log_info.txt   (license_server/log_path marker)

    When several entries use logs with the same file name, the server name is
    appended to the directory name (for example license.log__MasterServer2).
    Example cron entry on the collector host:

        */10 * * * * /path/to/licenseMonitor/bin/license_sample -u -U

  - GUI host (server A): LOG CURVE tab reads the stored csv data directly and
    never connects to license servers over SSH.  The tab lists both the license
    servers and the license logs (multi-select "Server" and "Log" filters), and
    the result table shows a "Log" column for each feature/server row.

  - db_path must be visible to both hosts (shared NFS mount, or the collector
    copies db/license_log to the GUI host regularly).

#### 5.2 Same-host deployment

When the GUI host itself has SSH access to license servers, the collector and
the GUI may run on the same host and everything above works without any change.

  - Click "Check" on LOG CURVE tab to load the stored license log data, update
    the table and draw the usage curve of one feature (same usage as CURVE tab).


More details please see ["docs/licenseMonitor_user_manual.pdf"](./docs/licenseMonitor_user_manual.pdf)
