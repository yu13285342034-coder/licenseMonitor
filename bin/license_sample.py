# -*- coding: utf-8 -*-
################################
# File Name   : license_sample.py
# Author      : liyanqing.1987
# Created On  : 2023-04-23 17:30:35
# Description :
################################
import os
import re
import sys
import time
import shutil
import datetime
import argparse
import sqlite3
from multiprocessing import Process

sys.path.append(os.environ['LICENSE_MONITOR_INSTALL_PATH'])
from common import common
from common import common_license
from common import common_sqlite3
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
    Read arguments.
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('-u', '--usage',
                        action='store_true',
                        default=False,
                        help='Sample license feature usage info.')
    parser.add_argument('-U', '--utilization',
                        action='store_true',
                        default=False,
                        help='Sample license feature utilization info.')

    args = parser.parse_args()

    if (not args.usage) and (not args.utilization):
        common.bprint('At least one argument of "usage/utilization" must be selected.', level='Error')
        sys.exit(1)

    return args.usage, args.utilization


class Sampling:
    """
    Sample and save license feature information.
    """
    def __init__(self, usage_sampling, utilization_sampling):
        self.usage_sampling = usage_sampling
        self.utilization_sampling = utilization_sampling

        # Get sample time.
        self.sample_second = int(time.time())
        self.sample_date = datetime.datetime.today().strftime('%Y%m%d')
        self.sample_time = datetime.datetime.today().strftime('%Y%m%d_%H%M%S')

        # License manager LM_LICENSE_FILE setting.
        LM_LICENSE_FILE_file = str(os.environ['LICENSE_MONITOR_INSTALL_PATH']) + '/config/LM_LICENSE_FILE'

        if os.path.exists(LM_LICENSE_FILE_file):
            os.environ['LM_LICENSE_FILE'] = ''

            with open(LM_LICENSE_FILE_file, 'r') as LLF:
                for line in LLF.readlines():
                    line = line.strip()

                    if (not re.match(r'^\s*$', line)) and (not re.match(r'^\s*#.*$', line)):
                        if os.environ['LM_LICENSE_FILE']:
                            os.environ['LM_LICENSE_FILE'] = str(os.environ['LM_LICENSE_FILE']) + ':' + str(line)
                        else:
                            os.environ['LM_LICENSE_FILE'] = str(line)

        # license.log is the authoritative OUT/IN source.  Read it before lmstat
        # so a server can still be sampled when lmstat is unavailable.
        self.log_parser = None
        self.log_events_dic = {}
        self.license_dic = {}
        self.init_log_parser()

        # Get current feature/capacity metadata with lmstat.  It is no longer
        # used as the primary source for usage curves when license.log exists.
        if not hasattr(config, 'lmstat_path'):
            config.lmstat_path = []

        if isinstance(config.lmstat_path, str):
            config.lmstat_path = [config.lmstat_path]
        elif not isinstance(config.lmstat_path, list):
            config.lmstat_path = []

        if not hasattr(config, 'lmstat_bsub_command'):
            config.lmstat_bsub_command = ''

        print('>>> Sampling license usage information ...')

        if os.environ.get('LM_LICENSE_FILE', '').strip():
            my_get_license_info = common_license.GetLicenseInfo(lmstat_path=config.lmstat_path, bsub_command=config.lmstat_bsub_command)
            self.license_dic = my_get_license_info.get_license_info()
        else:
            self.license_dic = {}

        if self.log_parser:
            self.store_log_events()
            self.seed_license_dic_from_log_events()

    def init_log_parser(self):
        """
        Discover FlexNet license.log paths automatically and initialize parser.

        config/others/license_log.yaml is optional.  If present, it only
        overrides paths that SSH process discovery cannot find.
        """
        license_log_config_file = str(os.environ['LICENSE_MONITOR_INSTALL_PATH']) + '/config/others/license_log.yaml'

        if hasattr(config, 'license_log_config_file') and config.license_log_config_file:
            license_log_config_file = config.license_log_config_file

        if (not hasattr(config, 'db_path')) or (not config.db_path):
            return

        print('>>> Discovering license log paths ...')

        self.log_parser = common_license_log.LicenseLogParser(
            log_config_file=license_log_config_file,
            db_path=config.db_path,
            ssh_user=getattr(config, 'license_log_ssh_user', ''),
        )

        license_server_list = []
        lm_license_file_list = [entry for entry in os.environ.get('LM_LICENSE_FILE', '').split(':') if entry.strip()]

        for license_server in lm_license_file_list:
            if license_server not in license_server_list:
                license_server_list.append(license_server)

        discovered_log_dic = self.log_parser.discover_license_log_paths(
            license_server_list,
            ssh_user=getattr(config, 'license_log_ssh_user', ''),
        )
        self.log_parser.set_log_paths(discovered_log_dic, override=False)

        if self.log_parser.log_dic:
            for license_server, license_log in sorted(self.log_parser.log_dic.items()):
                print('    Using license.log "' + str(license_log) + '" for server "' + str(license_server) + '".')
        else:
            common.bprint('No license.log was discovered automatically. Log parsing will be skipped.', level='Info')
            self.log_parser = None
            return

        # Migrate readers from the old snapshot integration: without an event
        # database, read the complete retained log once.
        if (not os.path.exists(self.get_license_event_db_file())) and self.log_parser.state_dic:
            self.log_parser.state_dic = {}
            self.log_parser.save_state()

        for license_server in sorted(self.log_parser.log_dic.keys()):
            events = self.log_parser.get_log_events(license_server)

            if events:
                print('    Collected ' + str(len(events)) + ' new OUT/IN events for server "' + str(license_server) + '" from license.log.')
                self.log_events_dic.setdefault(license_server, []).extend(events)

    def create_db_path(self, db_path):
        """
        Create db_path if not exists.
        """
        if not os.path.exists(db_path):
            try:
                print('    Create directory "' + str(db_path) + '".')
                os.makedirs(db_path, mode=0o755)
            except Exception as error:
                common.bprint('Failed on creating database directory "' + str(db_path) + '".', level='Error')
                common.bprint(error, color='red', display_method=1, indent=9)

                if not re.search('File exists', str(error)):
                    sys.exit(1)

    def copy_file(self, source_file, target_dir):
        """
        Copy source_file into target_dir.
        """
        try:
            print('    Copy "' + str(source_file) + '" into directory "' + str(target_dir) + '".')
            shutil.copy(source_file, target_dir)
        except Exception as warning:
            common.bprint('Failed on copying "' + str(source_file) + '" into directory "' + str(target_dir) + '".', level='Warning')
            common.bprint(warning, color='yellow', display_method=1, indent=11)

    def detect_project_setting(self):
        """
        Detect config/project/* and save new update into config.db_path/project_setting.
        """
        print('>>> Detect project setting ...')

        project_list_file = os.path.realpath(str(os.environ['LICENSE_MONITOR_INSTALL_PATH']) + '/config/project/project_list')
        project_submit_host_file = os.path.realpath(str(os.environ['LICENSE_MONITOR_INSTALL_PATH']) + '/config/project/project_submit_host')
        project_execute_host_file = os.path.realpath(str(os.environ['LICENSE_MONITOR_INSTALL_PATH']) + '/config/project/project_execute_host')
        project_user_file = os.path.realpath(str(os.environ['LICENSE_MONITOR_INSTALL_PATH']) + '/config/project/project_user')

        # Get project_setting_dic.
        copy_mark = False
        project_setting_db_path = str(config.db_path) + '/project_setting'

        self.create_db_path(project_setting_db_path)

        project_setting_dic = common.parse_project_setting_db_path(project_setting_db_path)

        if not project_setting_dic:
            copy_mark = True
        else:
            create_time_list = list(os.listdir(project_setting_db_path))
            latest_create_time = create_time_list[-1]

            # Get project_list/project_submit_host/project_execute_host/project_user content on config directory.
            config_project_list = common.parse_project_list_file(project_list_file)
            config_project_submit_host_dic = common.parse_project_proportion_file(project_submit_host_file, config_project_list)
            config_project_execute_host_dic = common.parse_project_proportion_file(project_execute_host_file, config_project_list)
            config_project_user_dic = common.parse_project_proportion_file(project_user_file, config_project_list)

            # Compare latest db_path setting and current config setting.
            if (project_setting_dic[latest_create_time]['project_list'] != config_project_list) or (project_setting_dic[latest_create_time]['project_submit_host'] != config_project_submit_host_dic) or (project_setting_dic[latest_create_time]['project_execute_host'] != config_project_execute_host_dic) or (project_setting_dic[latest_create_time]['project_user'] != config_project_user_dic):
                copy_mark = True

        if copy_mark:
            current_time = datetime.datetime.today().strftime('%Y%m%d%H%M%S')
            current_project_setting_db_path = str(project_setting_db_path) + '/' + str(current_time)

            self.create_db_path(current_project_setting_db_path)
            self.copy_file(project_list_file, current_project_setting_db_path)
            self.copy_file(project_execute_host_file, current_project_setting_db_path)
            self.copy_file(project_submit_host_file, current_project_setting_db_path)
            self.copy_file(project_user_file, current_project_setting_db_path)

    def sample_usage_info(self):
        """
        Sample license feature usage info and save it into sqlite db.
        """
        print('>>> Sampling usage info ...')

        for license_server in self.license_dic.keys():
            for vendor_daemon in self.license_dic[license_server]['vendor_daemon'].keys():
                db_path = str(config.db_path) + '/license_server/' + str(license_server) + '/' + str(vendor_daemon)

                self.create_db_path(db_path)

                usage_db_file = str(db_path) + '/usage.db'
                (result, usage_db_conn) = common_sqlite3.connect_db_file(usage_db_file, mode='write')

                if result == 'passed':
                    usage_table_list = common_sqlite3.get_sql_table_list(usage_db_file, usage_db_conn)

                    key_list = ['id', 'sample_second', 'sample_time', 'server', 'vendor', 'feature', 'user', 'submit_host', 'execute_host', 'num', 'version', 'start_second', 'start_time']
                    key_type_list = ['INTEGER PRIMARY KEY AUTOINCREMENT', 'INTEGER', 'TEXT', 'TEXT', 'TEXT', 'TEXT', 'TEXT', 'TEXT', 'TEXT', 'TEXT', 'TEXT', 'INTEGER', 'TEXT']

                    for feature in self.license_dic[license_server]['vendor_daemon'][vendor_daemon]['feature'].keys():
                        usage_table_name = feature

                        print('    Sampling usage info for "' + str(license_server) + '/' + str(vendor_daemon) + '/' + str(feature) + '" ...')

                        if usage_table_name not in usage_table_list:
                            # Generate database table title.
                            key_string = common_sqlite3.gen_sql_table_key_string(key_list, key_type_list)
                            common_sqlite3.create_sql_table(usage_db_file, usage_db_conn, usage_table_name, key_string, commit=False)

                            # Insert sql table value.
                            for usage_dic in self.license_dic[license_server]['vendor_daemon'][vendor_daemon]['feature'][feature]['in_use_info']:
                                start_second = common_license.switch_start_time(usage_dic['start_time'], compare_second=self.sample_second)
                                value_list = ['NULL', self.sample_second, self.sample_time, license_server, vendor_daemon, feature, usage_dic['user'], usage_dic['submit_host'], usage_dic['execute_host'], usage_dic['license_num'], usage_dic['version'], start_second, usage_dic['start_time']]
                                value_string = common_sqlite3.gen_sql_table_value_string(value_list, autoincrement=True)
                                common_sqlite3.insert_into_sql_table(usage_db_file, usage_db_conn, usage_table_name, value_string, commit=False)
                        else:
                            # Clean up usage database, only keep 100000 items.
                            usage_table_count = common_sqlite3.get_sql_table_count(usage_db_file, usage_db_conn, usage_table_name)

                            if usage_table_count != 'N/A':
                                if int(usage_table_count) > 100000:
                                    row_id = 'sample_time'
                                    begin_line = 0
                                    end_line = int(usage_table_count) - 100000

                                    print('    Deleting database "' + str(usage_db_file) + '" table "' + str(usage_table_name) + '" ' + str(begin_line) + '-' + str(end_line) + ' lines to only keep 100000 items.')

                                    common_sqlite3.delete_sql_table_rows(usage_db_file, usage_db_conn, usage_table_name, row_id, begin_line, end_line)

                            for usage_dic in self.license_dic[license_server]['vendor_daemon'][vendor_daemon]['feature'][feature]['in_use_info']:
                                select_condition = "WHERE server='" + str(license_server) + "' AND vendor='" + str(vendor_daemon) + "' AND feature='" + str(feature) + "' AND user='" + str(usage_dic['user']) + "' AND submit_host='" + str(usage_dic['submit_host']) + "' AND execute_host='" + str(usage_dic['execute_host']) + "' AND num='" + str(usage_dic['license_num']) + "' AND version='" + str(usage_dic['version']) + "' AND start_time='" + str(usage_dic['start_time']) + "'"
                                usage_db_data_dic = common_sqlite3.get_sql_table_data(usage_db_file, usage_db_conn, usage_table_name, ['server', 'vendor', 'feature'], select_condition)

                                if usage_db_data_dic:
                                    # Replace sql table value.
                                    set_condition = "SET sample_second='" + str(self.sample_second) + "', sample_time='" + str(self.sample_time) + "'"
                                    where_condition = "WHERE server='" + str(license_server) + "' AND vendor='" + str(vendor_daemon) + "' AND feature='" + str(feature) + "' AND user='" + str(usage_dic['user']) + "' AND submit_host='" + str(usage_dic['submit_host']) + "' AND execute_host='" + str(usage_dic['execute_host']) + "' AND num='" + str(usage_dic['license_num']) + "' AND version='" + str(usage_dic['version']) + "' AND start_time='" + str(usage_dic['start_time']) + "'"
                                    common_sqlite3.update_sql_table_data(usage_db_file, usage_db_conn, usage_table_name, set_condition, where_condition, commit=False)
                                else:
                                    # Insert sql table value.
                                    start_second = common_license.switch_start_time(usage_dic['start_time'], compare_second=self.sample_second)
                                    value_list = ['NULL', self.sample_second, self.sample_time, license_server, vendor_daemon, feature, usage_dic['user'], usage_dic['submit_host'], usage_dic['execute_host'], usage_dic['license_num'], usage_dic['version'], start_second, usage_dic['start_time']]
                                    value_string = common_sqlite3.gen_sql_table_value_string(value_list, autoincrement=True)
                                    common_sqlite3.insert_into_sql_table(usage_db_file, usage_db_conn, usage_table_name, value_string, commit=False)

                    usage_db_conn.commit()
                    usage_db_conn.close()

    def sample_utilization_info(self):
        """
        Sample license feature utilization info and save it into sqlite db.
        """
        print('>>> Sampling utilization info ...')

        for license_server in self.license_dic.keys():
            for vendor_daemon in self.license_dic[license_server]['vendor_daemon'].keys():
                db_path = str(config.db_path) + '/license_server/' + str(license_server) + '/' + str(vendor_daemon)

                self.create_db_path(db_path)

                utilization_db_file = str(db_path) + '/utilization.db'
                (result, utilization_db_conn) = common_sqlite3.connect_db_file(utilization_db_file, mode='write')

                if result == 'passed':
                    utilization_table_list = common_sqlite3.get_sql_table_list(utilization_db_file, utilization_db_conn)
                    feature_utilization_dic = self.get_feature_utilization_info(specified_license_server=license_server, specified_vendor_daemon=vendor_daemon)

                    key_list = ['sample_second', 'sample_time', 'issued', 'in_use', 'utilization']
                    key_type_list = ['INTEGER PRIMARY KEY', 'TEXT', 'TEXT', 'INTEGER', 'TEXT']

                    for (feature, feature_dic) in feature_utilization_dic.items():
                        utilization_table_name = feature

                        print('    Sampling utilization info for "' + str(license_server) + '/' + str(vendor_daemon) + '/' + str(feature) + '" ...')

                        # Clean up utilization database, only keep 100000 items.
                        if utilization_table_name in utilization_table_list:
                            utilization_table_count = common_sqlite3.get_sql_table_count(utilization_db_file, utilization_db_conn, utilization_table_name)

                            if utilization_table_count != 'N/A':
                                if int(utilization_table_count) > 100000:
                                    row_id = 'sample_time'
                                    begin_line = 0
                                    end_line = int(utilization_table_count) - 100000

                                    print('    Deleting database "' + str(utilization_db_file) + '" table "' + str(utilization_table_name) + '" ' + str(begin_line) + '-' + str(end_line) + ' lines to only keep 100000 items.')

                                    common_sqlite3.delete_sql_table_rows(utilization_db_file, utilization_db_conn, utilization_table_name, row_id, begin_line, end_line)

                        # Generate sql table.
                        if utilization_table_name not in utilization_table_list:
                            key_string = common_sqlite3.gen_sql_table_key_string(key_list, key_type_list)
                            common_sqlite3.create_sql_table(utilization_db_file, utilization_db_conn, utilization_table_name, key_string, commit=False)

                        # Insert sql table value.
                        value_list = [self.sample_second, self.sample_time, feature_dic['issued'], feature_dic['in_use'], feature_dic['utilization']]
                        value_string = common_sqlite3.gen_sql_table_value_string(value_list)
                        common_sqlite3.insert_into_sql_table(utilization_db_file, utilization_db_conn, utilization_table_name, value_string, commit=False)

                    utilization_db_conn.commit()
                    utilization_db_conn.close()

        self.count_utilization_day_info()

    def get_feature_utilization_info(self, specified_license_server, specified_vendor_daemon):
        """
        Get issued/in_use info from self.license_dic.
        Reture issued/in_use/utilization info with feature_utilization_dic.
        """
        # Get feature issed/in_use information.
        feature_utilization_dic = {}

        for license_server in self.license_dic.keys():
            if license_server == specified_license_server:
                for vendor_daemon in self.license_dic[license_server]['vendor_daemon'].keys():
                    if vendor_daemon == specified_vendor_daemon:
                        for (feature, feature_dic) in self.license_dic[license_server]['vendor_daemon'][vendor_daemon]['feature'].items():
                            feature_utilization_dic.setdefault(feature, [])
                            feature_utilization_dic[feature].append({'issued': feature_dic['issued'], 'in_use': feature_dic['in_use']})

        # Get feature utilization information.
        for (feature, feature_dic_list) in feature_utilization_dic.items():
            feature_utilization_dic[feature] = {}
            issued_sum = 0
            in_use_sum = 0

            for feature_dic in feature_dic_list:
                issued_num = feature_dic['issued']
                in_use_num = int(feature_dic['in_use'])
                in_use_sum += in_use_num

                if issued_num == 'Uncounted':
                    issued_sum = 'Uncounted'

                    if in_use_num == 0:
                        issued_num = 1
                    else:
                        issued_num = in_use_num
                else:
                    if issued_sum != 'Uncounted':
                        issued_num = int(issued_num)
                        issued_sum += issued_num

            if issued_sum == 'Uncounted':
                if in_use_sum == 0:
                    utilization = 0
                else:
                    utilization = 100
            else:
                utilization = round(100*in_use_sum/issued_sum, 1)

            feature_utilization_dic[feature] = {'issued': issued_sum, 'in_use': in_use_sum, 'utilization': utilization}

        return feature_utilization_dic

    def count_utilization_day_info(self):
        """
        Count license feature utilization day info and save it into sqlite db.
        """
        print('')
        print('>>> Counting utilization (day average) info ...')

        for license_server in self.license_dic.keys():
            for vendor_daemon in self.license_dic[license_server]['vendor_daemon'].keys():
                utilization_day_db_file = str(config.db_path) + '/license_server/' + str(license_server) + '/' + str(vendor_daemon) + '/utilization_day.db'
                (result, utilization_day_db_conn) = common_sqlite3.connect_db_file(utilization_day_db_file, mode='write')

                if result == 'passed':
                    utilization_day_table_list = common_sqlite3.get_sql_table_list(utilization_day_db_file, utilization_day_db_conn)
                    utilization_day_dic = self.get_utilization_day_info(specified_license_server=license_server, specified_vendor_daemon=vendor_daemon)

                    key_list = ['sample_date', 'issued', 'in_use', 'utilization']
                    key_type_list = ['TEXT PRIMARY KEY', 'TEXT', 'INTEGER', 'TEXT']

                    for (utilization_day_table_name, utilization_day_table_dic) in utilization_day_dic.items():
                        print('    Counting utilization (day average) info for "' + str(license_server) + '/' + str(vendor_daemon) + '/' + str(utilization_day_table_name) + '" ...')

                        # Generate sql table.
                        if utilization_day_table_name not in utilization_day_table_list:
                            key_string = common_sqlite3.gen_sql_table_key_string(key_list, key_type_list)
                            common_sqlite3.create_sql_table(utilization_day_db_file, utilization_day_db_conn, utilization_day_table_name, key_string, commit=False)

                            # Insert sql table value.
                            value_list = [self.sample_date, utilization_day_table_dic['issued'], utilization_day_table_dic['in_use'], utilization_day_table_dic['utilization']]
                            value_string = common_sqlite3.gen_sql_table_value_string(value_list)
                            common_sqlite3.insert_into_sql_table(utilization_day_db_file, utilization_day_db_conn, utilization_day_table_name, value_string, commit=False)
                        else:
                            # Clean up utilization database, only keep 3650 items.
                            utilization_day_table_count = common_sqlite3.get_sql_table_count(utilization_day_db_file, utilization_day_db_conn, utilization_day_table_name)

                            if utilization_day_table_count != 'N/A':
                                if int(utilization_day_table_count) > 3650:
                                    row_id = 'sample_time'
                                    begin_line = 0
                                    end_line = int(utilization_day_table_count) - 3650

                                    print('    Deleting database "' + str(utilization_day_db_file) + '" table "' + str(utilization_day_table_name) + '" ' + str(begin_line) + '-' + str(end_line) + ' lines to only keep 100000 items.')

                                    common_sqlite3.delete_sql_table_rows(utilization_day_db_file, utilization_day_db_conn, utilization_day_table_name, row_id, begin_line, end_line)

                            select_condition = "WHERE sample_date='" + str(self.sample_date) + "'"
                            utilization_day_db_data_dic = common_sqlite3.get_sql_table_data(utilization_day_db_file, utilization_day_db_conn, utilization_day_table_name, ['issued', 'in_use', 'utilization'], select_condition)

                            if utilization_day_db_data_dic:
                                # Replace sql table value.
                                set_condition = "SET issued='" + str(utilization_day_table_dic['issued']) + "', in_use='" + str(utilization_day_table_dic['in_use']) + "', utilization='" + str(utilization_day_table_dic['utilization']) + "'"
                                where_condition = "WHERE sample_date='" + str(self.sample_date) + "'"
                                common_sqlite3.update_sql_table_data(utilization_day_db_file, utilization_day_db_conn, utilization_day_table_name, set_condition, where_condition, commit=False)
                            else:
                                # Insert sql table value.
                                value_list = [self.sample_date, utilization_day_table_dic['issued'], utilization_day_table_dic['in_use'], utilization_day_table_dic['utilization']]
                                value_string = common_sqlite3.gen_sql_table_value_string(value_list)
                                common_sqlite3.insert_into_sql_table(utilization_day_db_file, utilization_day_db_conn, utilization_day_table_name, value_string, commit=False)

                    utilization_day_db_conn.commit()
                    utilization_day_db_conn.close()

    def get_utilization_day_info(self, specified_license_server, specified_vendor_daemon):
        """
        Get current day issued/in_use/utilization info from sqlite3 database.
        Reture issued_avg/in_use_avg/utilization_avg info with utilization_day_dic.
        """
        utilization_day_dic = {}
        begin_time = str(self.sample_date) + ' 00:00:00'
        begin_second = time.mktime(time.strptime(begin_time, '%Y%m%d %H:%M:%S'))
        end_time = str(self.sample_date) + ' 23:59:59'
        end_second = time.mktime(time.strptime(end_time, '%Y%m%d %H:%M:%S'))
        select_condition = "WHERE sample_second BETWEEN '" + str(begin_second) + "' AND '" + str(end_second) + "'"

        for license_server in self.license_dic.keys():
            if license_server == specified_license_server:
                for vendor_daemon in self.license_dic[license_server]['vendor_daemon'].keys():
                    if vendor_daemon == specified_vendor_daemon:
                        utilization_db_file = str(config.db_path) + '/license_server/' + str(license_server) + '/' + str(vendor_daemon) + '/utilization.db'

                        if os.path.exists(utilization_db_file):
                            (result, utilization_db_conn) = common_sqlite3.connect_db_file(utilization_db_file, mode='read')

                            if result == 'passed':
                                utilization_table_list = common_sqlite3.get_sql_table_list(utilization_db_file, utilization_db_conn)

                                for utilization_table_name in utilization_table_list:
                                    # Get current day issued/in_use/utilization from sqlite3 database.
                                    utilization_db_data_dic = common_sqlite3.get_sql_table_data(utilization_db_file, utilization_db_conn, utilization_table_name, ['issued', 'in_use', 'utilization'], select_condition)

                                    if utilization_db_data_dic:
                                        # Get issued_sum/in_use_sum/utilization_sum info.
                                        issued_sum = 0
                                        in_use_sum = 0
                                        utilization_sum = 0

                                        for (i, issued) in enumerate(utilization_db_data_dic['issued']):
                                            if (issued == 'Uncounted') or (issued_sum == 'Uncounted'):
                                                issued_sum = 'Uncounted'
                                            else:
                                                issued_sum += int(issued)

                                            in_use_sum += int(utilization_db_data_dic['in_use'][i])
                                            utilization_sum += float(utilization_db_data_dic['utilization'][i])

                                        # Get issued_avg/in_use_avg/utilization_avg info.
                                        if issued_sum == 'Uncounted':
                                            issued_avg = 'Uncounted'
                                        else:
                                            issued_avg = round(issued_sum/len(utilization_db_data_dic['issued']), 1)

                                        in_use_avg = round(in_use_sum/len(utilization_db_data_dic['issued']), 1)
                                        utilization_avg = round(utilization_sum/len(utilization_db_data_dic['issued']), 1)

                                        utilization_day_dic[utilization_table_name] = {'issued': issued_avg, 'in_use': in_use_avg, 'utilization': utilization_avg}

        return utilization_day_dic

    @staticmethod
    def quote_sqlite_name(name):
        """
        Quote an SQLite table/column name safely.
        """
        return '"' + str(name).replace('"', '""') + '"'

    @staticmethod
    def format_log_time(timestamp_second):
        """
        Format a license.log timestamp in licenseMonitor database format.
        """
        return datetime.datetime.fromtimestamp(int(timestamp_second)).strftime('%Y%m%d_%H%M%S')

    @staticmethod
    def get_license_event_db_file():
        """
        Get the persistent event database used to avoid re-reading old logs.
        """
        return str(config.db_path) + '/license_log_events.db'

    def connect_license_event_db(self):
        """
        Create/connect the persistent license.log event database.
        """
        event_db_file = self.get_license_event_db_file()

        if not os.path.exists(config.db_path):
            self.create_db_path(str(config.db_path))

        event_conn = sqlite3.connect(event_db_file, timeout=30)
        event_conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server TEXT NOT NULL,
                timestamp_second INTEGER NOT NULL,
                timestamp_str TEXT,
                event_type TEXT NOT NULL,
                vendor TEXT NOT NULL,
                feature TEXT NOT NULL,
                user TEXT NOT NULL,
                host TEXT NOT NULL,
                lic_num INTEGER NOT NULL DEFAULT 1,
                raw_line TEXT
            )
        """)
        event_conn.execute('CREATE INDEX IF NOT EXISTS events_feature_idx ON events(server, vendor, feature, timestamp_second, id)')
        event_conn.execute("""CREATE TABLE IF NOT EXISTS meta (
            name TEXT PRIMARY KEY,
            value TEXT
        )""")
        event_conn.commit()

        return event_conn

    def get_event_meta(self, event_conn, name):
        """
        Read integer event-db metadata such as an integration watermark.
        """
        row = event_conn.execute('SELECT value FROM meta WHERE name = ?', (name,)).fetchone()

        if row and re.match(r'^\d+$', str(row[0])):
            return int(row[0])

        return 0

    def set_event_meta(self, event_conn, name, value, commit=True):
        """
        Save integration watermark after a successful rebuild.
        """
        event_conn.execute(
            'INSERT INTO meta(name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',
            (name, str(int(value)))
        )

        if commit:
            event_conn.commit()

    def store_log_events(self):
        """
        Persist newly-read license.log events before rebuilding display tables.
        """
        if (not self.log_parser) or (not self.log_events_dic):
            return

        event_db_file = self.get_license_event_db_file()
        print('>>> Saving license.log OUT/IN events into "' + str(event_db_file) + '" ...')

        try:
            event_conn = self.connect_license_event_db()

            for license_server, events in self.log_events_dic.items():
                rows = []

                for event in events:
                    rows.append((
                        license_server,
                        int(event['timestamp_second']),
                        str(event.get('timestamp_str', '')),
                        str(event['event_type']),
                        str(event.get('vendor', 'UNKNOWN')),
                        str(event['feature']),
                        str(event['user']),
                        str(event['host']),
                        max(1, int(event.get('lic_num', 1))),
                        str(event.get('raw_line', '')),
                    ))

                event_conn.executemany("""
                    INSERT INTO events(
                        server, timestamp_second, timestamp_str, event_type, vendor,
                        feature, user, host, lic_num, raw_line
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)

            event_conn.commit()
            event_conn.close()

            # Offsets are committed only after events are durable in SQLite.
            self.log_parser.commit_log_state()
        except Exception as error:
            try:
                event_conn.rollback()
                event_conn.close()
            except Exception:
                pass

            common.bprint('Failed on saving license.log events into "' + str(event_db_file) + '".', level='Error')
            common.bprint(error, color='red', display_method=1, indent=9)

    def get_max_log_event_id(self):
        """
        Get current event-db watermark.
        """
        try:
            event_conn = self.connect_license_event_db()
            row = event_conn.execute('SELECT COALESCE(MAX(id), 0) FROM events').fetchone()
            event_conn.close()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def log_integration_pending(self, integration_name):
        """
        Check whether a display database has events not yet integrated.
        """
        try:
            event_conn = self.connect_license_event_db()
            max_event_id = int(event_conn.execute('SELECT COALESCE(MAX(id), 0) FROM events').fetchone()[0])
            integrated_id = self.get_event_meta(event_conn, integration_name)
            event_conn.close()

            return max_event_id > integrated_id
        except Exception:
            return False

    def get_log_event_groups(self, event_conn, after_event_id=0, before_event_id=0):
        """
        Get server/vendor/feature groups containing new events.
        """
        condition = ''

        if after_event_id > 0:
            condition = ' WHERE id > ' + str(int(after_event_id))

        if before_event_id > 0:
            condition = ' WHERE id <= ' + str(int(before_event_id)) if not condition else condition + ' AND id <= ' + str(int(before_event_id))

        rows = event_conn.execute("""
            SELECT DISTINCT server, vendor, feature
            FROM events""" + condition + """
            ORDER BY server, vendor, feature
        """).fetchall()

        return [(row[0], row[1], row[2]) for row in rows]

    def get_log_events_for_group(self, event_conn, license_server, vendor_daemon, feature):
        """
        Read all persisted events for one server/vendor/feature group.
        """
        return event_conn.execute("""
            SELECT timestamp_second, event_type, user, host, lic_num
            FROM events
            WHERE server = ? AND vendor = ? AND feature = ?
            ORDER BY timestamp_second, id
        """, (license_server, vendor_daemon, feature)).fetchall()

    def seed_license_dic_from_log_events(self):
        """
        Seed feature/vendor metadata from license.log when lmstat is unavailable.
        """
        try:
            event_conn = self.connect_license_event_db()
            groups = self.get_log_event_groups(event_conn)
            event_conn.close()
        except Exception:
            return

        for (license_server, vendor_daemon, feature) in groups:
            self.license_dic.setdefault(license_server, {
                'license_files': '',
                'license_server_status': 'LOG',
                'license_server_version': '',
                'vendor_daemon': {},
            })

            self.license_dic[license_server].setdefault('vendor_daemon', {}).setdefault(vendor_daemon, {
                'vendor_daemon_status': 'LOG',
                'vendor_daemon_version': '',
                'feature': {},
            })

            features = self.license_dic[license_server]['vendor_daemon'][vendor_daemon].setdefault('feature', {})

            if feature not in features:
                features[feature] = {
                    'issued': 'Uncounted',
                    'in_use': '0',
                    'in_use_info_string': [],
                    'in_use_info': [],
                }

    def ensure_usage_table(self, usage_conn, feature):
        """
        Ensure one usage table has the original licenseMonitor schema.
        """
        usage_conn.execute("""
            CREATE TABLE IF NOT EXISTS """ + self.quote_sqlite_name(feature) + """ (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_second INTEGER,
                sample_time TEXT,
                server TEXT,
                vendor TEXT,
                feature TEXT,
                user TEXT,
                submit_host TEXT,
                execute_host TEXT,
                num TEXT,
                version TEXT,
                start_second INTEGER,
                start_time TEXT
            )
        """)

    def integrate_log_events_into_usage_db(self):
        """
        Rebuild usage tables from authoritative license.log OUT/IN events.

        A row represents one checkout session, not one lmstat observation.  Its
        sample_second/start_time are set to IN time after checkout completion;
        still-active sessions use the current sampling time.
        """
        event_db_file = self.get_license_event_db_file()
        event_conn = self.connect_license_event_db()
        max_event_id = int(event_conn.execute('SELECT COALESCE(MAX(id), 0) FROM events').fetchone()[0])
        integrated_id = self.get_event_meta(event_conn, 'usage_event_id')
        groups = self.get_log_event_groups(event_conn, after_event_id=integrated_id, before_event_id=max_event_id)
        print('>>> Rebuilding usage database from license.log events ...')

        for (license_server, vendor_daemon, feature) in groups:
            db_path = str(config.db_path) + '/license_server/' + str(license_server) + '/' + str(vendor_daemon)
            self.create_db_path(db_path)

            usage_db_file = str(db_path) + '/usage.db'
            usage_conn = sqlite3.connect(usage_db_file, timeout=30)
            self.ensure_usage_table(usage_conn, feature)

            rows = self.get_log_events_for_group(event_conn, license_server, vendor_daemon, feature)
            active_sessions = {}
            session_rows = []

            for (timestamp_second, event_type, user, host, lic_num) in rows:
                session_key = (str(user), str(host))

                if str(event_type).upper() == 'OUT':
                    session = {
                        'start_second': int(timestamp_second),
                        'end_second': None,
                        'user': str(user),
                        'host': str(host),
                        'lic_num': max(1, int(lic_num)),
                    }
                    active_sessions.setdefault(session_key, []).append(session)
                else:
                    candidates = active_sessions.get(session_key, [])

                    if candidates:
                        session = candidates.pop(0)
                        session['end_second'] = int(timestamp_second)
                        session_rows.append(session)

            for candidates in active_sessions.values():
                session_rows.extend(candidates)

            session_rows.sort(key=lambda session: session['start_second'])
            session_rows = session_rows[-100000:]

            table_name = self.quote_sqlite_name(feature)
            usage_conn.execute('DELETE FROM ' + table_name)

            usage_rows = []

            for session in session_rows:
                end_second = session['end_second'] if session['end_second'] is not None else self.sample_second
                end_second = max(end_second, session['start_second'])
                usage_rows.append((
                    end_second,
                    self.format_log_time(end_second),
                    license_server,
                    vendor_daemon,
                    feature,
                    session['user'],
                    'N/A',
                    session['host'],
                    str(session['lic_num']),
                    'N/A',
                    session['start_second'],
                    self.format_log_time(session['start_second']),
                ))

            usage_conn.executemany("""
                INSERT INTO """ + table_name + """
                    (sample_second, sample_time, server, vendor, feature, user,
                     submit_host, execute_host, num, version, start_second, start_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, usage_rows)
            usage_conn.commit()
            usage_conn.close()

            print('    Rebuilt ' + str(len(usage_rows)) + ' usage sessions for ' + str(license_server) + '/' + str(vendor_daemon) + '/' + str(feature))

        self.set_event_meta(event_conn, 'usage_event_id', max_event_id)
        event_conn.close()

    def get_current_issued_for_feature(self, license_server, feature):
        """
        Get latest lmstat capacity for a feature; logs themselves have no total.
        """
        if license_server in self.license_dic:
            for vendor_features in self.license_dic[license_server].get('vendor_daemon', {}).values():
                if feature in vendor_features.get('feature', {}):
                    return vendor_features['feature'][feature].get('issued', 'Uncounted')

        return ''

    def integrate_log_events_into_utilization_db(self):
        """
        Rebuild utilization curves from log event deltas.

        All OUT/IN events for a feature are replayed in timestamp order.  If an
        lmstat snapshot exists, only the first snapshot is used as a baseline for
        sessions opened before the retained log began; subsequent values are not
        replaced by incomplete snapshots.
        """
        event_conn = self.connect_license_event_db()
        max_event_id = int(event_conn.execute('SELECT COALESCE(MAX(id), 0) FROM events').fetchone()[0])
        integrated_id = self.get_event_meta(event_conn, 'utilization_event_id')
        groups = self.get_log_event_groups(event_conn, after_event_id=integrated_id, before_event_id=max_event_id)
        print('>>> Rebuilding utilization curve from license.log events ...')

        for (license_server, vendor_daemon, feature) in groups:
            db_path = str(config.db_path) + '/license_server/' + str(license_server) + '/' + str(vendor_daemon)
            self.create_db_path(db_path)

            utilization_db_file = str(db_path) + '/utilization.db'
            utilization_conn = sqlite3.connect(utilization_db_file, timeout=30)
            table_name = self.quote_sqlite_name(feature)
            utilization_conn.execute("""
                CREATE TABLE IF NOT EXISTS """ + table_name + """ (
                    sample_second INTEGER PRIMARY KEY,
                    sample_time TEXT,
                    issued TEXT,
                    in_use INTEGER,
                    utilization TEXT
                )
            """)

            rows = self.get_log_events_for_group(event_conn, license_server, vendor_daemon, feature)
            events_by_second = {}

            for row in rows:
                events_by_second.setdefault(int(row[0]), []).append((str(row[1]).upper(), max(1, int(row[4]))))

            snapshots = {}

            try:
                snapshot_rows = utilization_conn.execute(
                    'SELECT sample_second, issued, in_use FROM ' + table_name + ' ORDER BY sample_second'
                ).fetchall()

                for snapshot_row in snapshot_rows:
                    try:
                        snapshots[int(snapshot_row[0])] = (snapshot_row[1], int(snapshot_row[2]))
                    except Exception:
                        continue
            except Exception:
                snapshots = {}

            all_seconds = sorted(set(list(events_by_second.keys()) + list(snapshots.keys()) + [self.sample_second]))
            first_snapshot = snapshots.get(min(snapshots), None) if snapshots else None
            current_issued = self.get_current_issued_for_feature(license_server, feature)
            first_known_issued = first_snapshot[0] if first_snapshot else current_issued
            raw_in_use = 0
            baseline_correction = first_snapshot[1] if first_snapshot else 0
            output_rows = []
            last_output_in_use = 0

            for timestamp_second in all_seconds:
                snapshot = snapshots.get(timestamp_second)

                if (snapshot is not None) and (not output_rows):
                    # First lmstat point supplies sessions whose OUT lines are
                    # older than the retained license.log, not an override for
                    # already replayed log events.
                    raw_before = raw_in_use
                    baseline_correction = snapshot[1] - raw_before
                    first_known_issued = snapshot[0]

                for (event_type, lic_num) in events_by_second.get(timestamp_second, []):
                    if event_type == 'OUT':
                        raw_in_use += lic_num
                    else:
                        raw_in_use -= lic_num

                in_use = max(0, raw_in_use + baseline_correction)

                if snapshot is not None:
                    issued = snapshot[0]
                    first_known_issued = issued
                else:
                    issued = first_known_issued

                output_rows.append((timestamp_second, self.format_log_time(timestamp_second), issued, in_use))
                last_output_in_use = in_use

            if not first_known_issued or (str(first_known_issued).lower() == 'uncounted'):
                inferred_issued = str(max(1, max([row[3] for row in output_rows], default=1)))

                for index in range(len(output_rows)):
                    output_rows[index] = (
                        output_rows[index][0],
                        output_rows[index][1],
                        inferred_issued if not output_rows[index][2] else output_rows[index][2],
                        output_rows[index][3],
                    )

            final_rows = []

            for (timestamp_second, sample_time, issued, in_use) in output_rows[-100000:]:
                if (str(issued).lower() == 'uncounted') or (not re.match(r'^\d+$', str(issued))):
                    utilization = 100 if int(in_use) > 0 else 0
                else:
                    issued_num = int(issued)
                    utilization = round(100 * int(in_use) / issued_num, 1) if issued_num > 0 else 0

                final_rows.append((timestamp_second, sample_time, issued, int(in_use), utilization))

            utilization_conn.execute('DELETE FROM ' + table_name)
            utilization_conn.executemany("""
                INSERT INTO """ + table_name + """
                    (sample_second, sample_time, issued, in_use, utilization)
                VALUES (?, ?, ?, ?, ?)
            """, final_rows)
            utilization_conn.commit()
            utilization_conn.close()

            print('    Rebuilt ' + str(len(final_rows)) + ' curve points for ' + str(license_server) + '/' + str(vendor_daemon) + '/' + str(feature))

        self.set_event_meta(event_conn, 'utilization_event_id', max_event_id)
        event_conn.close()

    def find_vendor_for_feature(self, license_server, feature):
        """
        Find which vendor_daemon serves the given feature.
        """
        if license_server not in self.license_dic:
            return None

        for vendor_daemon in self.license_dic[license_server].get('vendor_daemon', {}).keys():
            if feature in self.license_dic[license_server]['vendor_daemon'][vendor_daemon].get('feature', {}):
                return vendor_daemon

        return None

    def sampling(self):
        if not ((hasattr(config, 'db_path')) and config.db_path):
            common.bprint('No "db_path" is specified on config/config.py.', level='Error')
            sys.exit(1)

        processes = []

        # lmstat snapshots remain useful for feature capacity and as an initial
        # baseline, but usage tables are rebuilt directly from license.log.
        if self.usage_sampling and (not self.log_integration_pending('usage_event_id')):
            process = Process(target=self.sample_usage_info)
            process.start()
            processes.append(process)

        if self.utilization_sampling:
            process = Process(target=self.sample_utilization_info)
            process.start()
            processes.append(process)

        for process in processes:
            process.join()

        direct_log_integrated = False

        if self.usage_sampling and self.log_integration_pending('usage_event_id'):
            self.integrate_log_events_into_usage_db()

        if self.utilization_sampling and self.log_integration_pending('utilization_event_id'):
            self.integrate_log_events_into_utilization_db()
            direct_log_integrated = True

        if direct_log_integrated:
            self.count_utilization_day_info()


################
# Main Process #
################
def main():
    (usage, utilization) = read_args()
    my_sampling = Sampling(usage, utilization)
    my_sampling.detect_project_setting()
    my_sampling.sampling()


if __name__ == '__main__':
    main()
