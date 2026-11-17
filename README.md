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
  - The license log is read from the license server over SSH incrementally with
    common/common_license_log.py, only new lines are parsed each time.
  - The license usage data is saved as csv files together with the CURVE db data:

        db/license_log/<license_server>/events.csv      (all OUT/IN events)
        db/license_log/<license_server>/<feature>.csv   (per-feature usage curve,
                                                         columns: sample_second, sample_time, in_use)

  - Click "Check" on LOG CURVE tab to read the newest log, update the table
    and draw the usage curve of one feature (same usage as CURVE tab).


More details please see ["docs/licenseMonitor_user_manual.pdf"](./docs/licenseMonitor_user_manual.pdf)
