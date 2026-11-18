# -*- coding: utf-8 -*-
################################
# File Name   : collect_license_log.py
# Created On  : 2026-11-18
# Description : Collect LOG CURVE data (license.log OUT/IN events) into
#               <db_path>/license_log/<log file name>/ for the GUI LOG CURVE
#               tab.  Just run it directly, no environment or config is
#               required:
#
#                   python3 /path/to/licenseMonitor/tools/collect_license_log.py
#
#               Data is stored in the "license_log" directory at the same
#               level as the "license_server" directory (created
#               automatically).
################################
import os
import sys
import argparse

# This script lives in <install>/tools, so the install path is its parent
# directory.  No LICENSE_MONITOR_INSTALL_PATH environment setting is needed.
INSTALL_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(INSTALL_PATH)

from common import common
from common import common_license_log

os.environ.setdefault('PYTHONUNBUFFERED', '1')


def load_config(install_path):
    """
    Load config.py when it is available: ~/.licenseMonitor/config/config.py
    first, then <install_path>/config/config.py.  Return None when no config
    exists, then all settings fall back to automatic defaults.
    """
    home_dir = str(os.environ.get('HOME', ''))

    # HOME config is a plain module file.
    if home_dir and os.path.exists(home_dir + '/.licenseMonitor/config/config.py'):
        sys.path.insert(0, home_dir + '/.licenseMonitor/config')

        try:
            import config
            return config
        except Exception as error:
            common.bprint('Failed on loading "' + home_dir + '/.licenseMonitor/config/config.py".', level='Warning')
            common.bprint(error, color='yellow', display_method=1, indent=9)

    # Install config is a python package (config/__init__.py + config/config.py).
    if os.path.exists(str(install_path) + '/config/config.py'):
        sys.path.insert(0, str(install_path))

        try:
            from config import config
            return config
        except Exception as error:
            common.bprint('Failed on loading "' + str(install_path) + '/config/config.py".', level='Warning')
            common.bprint(error, color='yellow', display_method=1, indent=9)

    return None


def find_db_path(install_path):
    """
    Find the default db directory automatically: prefer the directory which
    already contains the "license_server" data directory (written by
    license_sample), fall back to <install_path>/db.  The "license_log"
    directory is created at the same level as "license_server" afterwards.
    """
    for candidate in [str(install_path) + '/db', str(install_path)]:
        if os.path.isdir(candidate + '/license_server'):
            return candidate

    return str(install_path) + '/db'


def read_args():
    """
    Read in arguments.  All arguments are optional, the script works with no
    arguments at all.
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--init_file',
                        default='',
                        help='Optional, license log server init file ("ServerName:/path/to/license.log" lines), default is "license_log_server_init_file" on config.py, or "config/others/license_log_server.init" under the install path.')
    parser.add_argument('-d', '--db_path',
                        default='',
                        help='Optional, specify the database directory, default is "db_path" on config.py, or the directory which contains the "license_server" directory, or "<install>/db". The license_log directory is created at the same level as license_server automatically.')
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        default=False,
                        help='Show detailed collecting progress.')

    args = parser.parse_args()

    return args.init_file, args.db_path, args.verbose


class CollectLicenseLog():
    """
    Read license.log of every server listed in license_log_server.init (one
    "ServerName:/path/to/license.log" line per server) and store OUT/IN events
    into <db_path>/license_log/<log file name>/events.csv (one directory per
    log file, plus a log_info.txt marker).  The directory structure is created
    automatically.

    The LOG CURVE tab of bin/license_monitor reads these csv files directly,
    so the GUI host does not need ssh access to the license servers.
    """
    def __init__(self, init_file='', db_path='', verbose=False):
        self.verbose = bool(verbose)
        self.config = load_config(INSTALL_PATH)
        self.init_file = str(init_file or '')
        self.db_path = str(db_path or '')
        self.log_parser = None
        self.init_log_parser()

    def vprint(self, message=''):
        """
        Print detailed progress only when --verbose is requested.
        """
        if self.verbose:
            print(message)

    def init_log_parser(self):
        """
        Initialize the license log parser with license_log_server.init, create
        the license_log directory structure automatically.
        """
        # db_path: argument -> config.py -> automatic detection.
        if not self.db_path:
            self.db_path = str(getattr(self.config, 'db_path', '') or '')

        if not self.db_path:
            self.db_path = find_db_path(INSTALL_PATH)

        # init file: argument -> config.py -> install path default.
        if not self.init_file:
            self.init_file = str(getattr(self.config, 'license_log_server_init_file', '') or '')

        if not self.init_file:
            self.init_file = str(INSTALL_PATH) + '/config/others/license_log_server.init'

        if not os.path.exists(self.init_file):
            common.bprint('License log server init file "' + self.init_file + '" does not exist, nothing to collect.', level='Error')
            sys.exit(1)

        # Create the license_log directory at the same level as license_server.
        curve_db_path = self.db_path + '/license_log'

        if not os.path.exists(curve_db_path):
            os.makedirs(curve_db_path, mode=0o755, exist_ok=True)
            self.vprint('    Create directory "' + curve_db_path + '".')

        self.curve_db_path = curve_db_path
        self.log_parser = common_license_log.LicenseLogParser(
            log_config_file=self.init_file,
            db_path=curve_db_path,
            ssh_user=str(getattr(self.config, 'license_log_ssh_user', '') or ''),
        )
        self.vprint('>>> Collecting license log data (init file: "' + self.init_file + '", db: "' + curve_db_path + '") ...')

    def collect(self):
        """
        Read each license log and store the parsed events as csv data.
        """
        if not self.log_parser:
            return

        store_failed = False

        for license_server in sorted(self.log_parser.log_dic.keys()):
            log_path = self.log_parser.log_dic[license_server]
            store_name = self.log_parser.get_log_store_dir_name(license_server, log_path)
            log_db_path = self.curve_db_path + '/' + str(store_name)
            events_csv_file = log_db_path + '/events.csv'
            log_info_file = log_db_path + '/log_info.txt'

            try:
                event_list = self.log_parser.get_log_events(license_server)
            except Exception as error:
                event_list = []
                print('LOG CURVE READ: NO server=' + str(license_server) + ' log=' + str(log_path) + ' reason=' + str(error).replace('\n', ' ')[:120])

            result = self.log_parser.read_result_dic.get(license_server, {})
            status = str(result.get('status', 'NOT_READ')).upper()

            if status != 'READ':
                continue

            try:
                stored_event_list = common_license_log.LicenseLogParser.load_events_csv(events_csv_file)
                merged_event_list = common_license_log.LicenseLogParser.merge_event_lists(stored_event_list, event_list)
                merged_event_list.sort(key=lambda event: event['timestamp_second'])

                for event in merged_event_list:
                    event['license_server'] = license_server
                    event['log_path'] = log_path

                common_license_log.LicenseLogParser.write_events_csv(events_csv_file, merged_event_list)

                with open(log_info_file, 'w', encoding='utf-8') as log_info:
                    log_info.write('license_server=' + str(license_server) + '\n')
                    log_info.write('log_path=' + str(log_path) + '\n')

                print('LOG CURVE READ: YES server=' + str(license_server) + ' log=' + str(log_path) + ' new_events=' + str(result.get('new_events', 0)) + ' total_events=' + str(len(merged_event_list)))
            except Exception as error:
                store_failed = True
                print('LOG CURVE READ: NO server=' + str(license_server) + ' log=' + str(log_path) + ' reason=store-failed: ' + str(error).replace('\n', ' ')[:120])
                common.bprint('Failed on storing LOG CURVE data into "' + str(events_csv_file) + '".', level='Warning')
                common.bprint(error, color='yellow', display_method=1, indent=9)

        if not store_failed:
            # Offsets are committed only after events are stored successfully,
            # otherwise the events will be read again next time.
            self.log_parser.commit_log_state()

        print('LOG CURVE DATA: ' + self.curve_db_path)


################
# Main Process #
################
def main():
    (init_file, db_path, verbose) = read_args()
    my_collector = CollectLicenseLog(init_file=init_file, db_path=db_path, verbose=verbose)
    my_collector.collect()


if __name__ == '__main__':
    main()
