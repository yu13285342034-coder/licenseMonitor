# -*- coding: utf-8 -*-
################################
# File Name   : collect_license_log.py
# Created On  : 2026-11-18
# Description : Collect LOG CURVE data (license.log OUT/IN events) into
#               db_path/license_log/<log file name>/ for the GUI LOG CURVE
#               tab.  Designed to run on a collector host (for example via
#               cron) which has ssh access to the license servers.
################################
import os
import sys
import getpass
import argparse

sys.path.append(os.environ['LICENSE_MONITOR_INSTALL_PATH'])
from common import common
from common import common_license_log

# Import local config file if exists.
local_config_dir = str(os.environ['HOME']) + '/.licenseMonitor/config'
local_config = str(local_config_dir) + '/config.py'

if os.path.exists(local_config):
    sys.path.append(local_config_dir)
    import config
else:
    from config import config

os.environ['PYTHONUNBUFFERED'] = '1'


def read_args():
    """
    Read in arguments.
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--init_file',
                        default='',
                        help='Optional, license log server init file, default is "license_log_server_init_file" on config.py ("config/others/license_log_server.init").')
    parser.add_argument('-d', '--db_path',
                        default='',
                        help='Optional, specify the database directory, default is "db_path" on config.py. It must be visible to the GUI host (shared NFS or regular sync).')
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
    into db_path/license_log/<log file name>/events.csv (one directory per log
    file, plus a log_info.txt marker).

    The LOG CURVE tab of bin/license_monitor reads these csv files directly,
    so the GUI host does not need ssh access to the license servers.
    """
    def __init__(self, init_file='', db_path='', verbose=False):
        self.verbose = bool(verbose)
        self.log_parser = None
        self.init_log_parser(init_file=init_file, db_path=db_path)

    def vprint(self, message=''):
        """
        Print detailed progress only when --verbose is requested.
        """
        if self.verbose:
            print(message)

    def init_log_parser(self, init_file='', db_path=''):
        """
        Initialize the license log parser with license_log_server.init.
        """
        if not db_path:
            if (not hasattr(config, 'db_path')) or (not config.db_path):
                common.bprint('No "db_path" is specified on config/config.py or "-d/--db_path".', level='Error')
                sys.exit(1)

            db_path = str(config.db_path)

        if not init_file:
            install_path = str(os.environ.get('LICENSE_MONITOR_INSTALL_PATH', os.getcwd()))
            init_file = str(getattr(config, 'license_log_server_init_file', '') or (install_path + '/config/others/license_log_server.init'))

        if not os.path.exists(init_file):
            common.bprint('License log server init file "' + str(init_file) + '" does not exist, nothing to collect.', level='Error')
            sys.exit(1)

        curve_db_path = str(db_path) + '/license_log'

        if not os.path.exists(curve_db_path):
            os.makedirs(curve_db_path, mode=0o755, exist_ok=True)

        self.db_path = str(db_path)
        self.log_parser = common_license_log.LicenseLogParser(
            log_config_file=init_file,
            db_path=curve_db_path,
            ssh_user=getattr(config, 'license_log_ssh_user', ''),
        )
        self.vprint('>>> Collecting license log data (from "' + str(init_file) + '") ...')

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
            log_db_path = self.db_path + '/license_log/' + str(store_name)
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


################
# Main Process #
################
def main():
    (init_file, db_path, verbose) = read_args()
    my_collector = CollectLicenseLog(init_file=init_file, db_path=db_path, verbose=verbose)
    my_collector.collect()


if __name__ == '__main__':
    main()
