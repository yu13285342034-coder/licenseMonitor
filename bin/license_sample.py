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

        # Get self.license_dic.
        print('>>> Sampling license usage information ...')

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

        if not hasattr(config, 'lmstat_path'):
            config.lmstat_path = []

        if isinstance(config.lmstat_path, str):
            config.lmstat_path = [config.lmstat_path]
        elif not isinstance(config.lmstat_path, list):
            config.lmstat_path = []

        if not hasattr(config, 'lmstat_bsub_command'):
            config.lmstat_bsub_command = ''

        my_get_license_info = common_license.GetLicenseInfo(lmstat_path=config.lmstat_path, bsub_command=config.lmstat_bsub_command)
        self.license_dic = my_get_license_info.get_license_info()

        self.log_parser = None
        self.log_events_dic = {}
        self.init_log_parser()

    def init_log_parser(self):
        """
        Initialize license log parser if config is available, and pre-collect log events.
        """
        license_log_config_file = str(os.environ['LICENSE_MONITOR_INSTALL_PATH']) + '/config/others/license_log.yaml'

        if hasattr(config, 'license_log_config_file') and config.license_log_config_file:
            license_log_config_file = config.license_log_config_file

        if (not os.path.exists(license_log_config_file)) or (not hasattr(config, 'db_path')) or (not config.db_path):
            return

        print('>>> Initializing license log parser ...')

        self.log_parser = common_license_log.LicenseLogParser(
            log_config_file=license_log_config_file,
            db_path=config.db_path,
        )

        if not self.log_parser.log_dic:
            common.bprint('No license log entries found in "' + str(license_log_config_file) + '". Log parsing will be skipped.', level='Info')
            self.log_parser = None
            return

        for license_server in self.license_dic.keys():
            events = self.log_parser.get_log_events(license_server)

            if events:
                print('    Collected ' + str(len(events)) + ' new log events for server "' + str(license_server) + '".')
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

    def integrate_log_events_into_usage_db(self):
        """
        Merge license log events into usage.db after snapshot sampling.
          - OUT events not already in usage.db → INSERT (sessions missed by all snapshots).
          - IN events                           → UPDATE sample_second/sample_time to actual end time
                                                  (fixes runtime underestimation when session ends between snapshots).
        """
        if not self.log_events_dic:
            return

        print('>>> Integrating license log events into usage db ...')

        for license_server in self.license_dic.keys():
            if license_server not in self.log_events_dic:
                continue

            events = self.log_events_dic[license_server]

            if not events:
                continue

            events_by_vendor_feature = {}
            for event in events:
                vendor_daemon = self.find_vendor_for_feature(license_server, event['feature'])

                if vendor_daemon:
                    events_by_vendor_feature.setdefault(vendor_daemon, []).append(event)

            for vendor_daemon in events_by_vendor_feature.keys():
                db_path = str(config.db_path) + '/license_server/' + str(license_server) + '/' + str(vendor_daemon)
                usage_db_file = str(db_path) + '/usage.db'

                if not os.path.exists(usage_db_file):
                    continue

                (result, usage_db_conn) = common_sqlite3.connect_db_file(usage_db_file, mode='write')

                if result != 'passed':
                    continue

                usage_table_list = common_sqlite3.get_sql_table_list(usage_db_file, usage_db_conn)

                out_events = [e for e in events_by_vendor_feature[vendor_daemon] if e['event_type'] == 'OUT']
                in_events = [e for e in events_by_vendor_feature[vendor_daemon] if e['event_type'] == 'IN']

                for out_event in out_events:
                    feature = out_event['feature']

                    if feature not in usage_table_list:
                        continue

                    start_second = out_event['timestamp_second']
                    start_time = out_event['timestamp_str']
                    sample_second = start_second
                    sample_time = datetime.datetime.fromtimestamp(start_second).strftime('%Y%m%d_%H%M%S')
                    lic_num = out_event['lic_num']

                    select_condition = (
                        "WHERE server='" + str(license_server) + "'"
                        " AND feature='" + str(feature) + "'"
                        " AND user='" + str(out_event['user']) + "'"
                        " AND execute_host='" + str(out_event['host']) + "'"
                        " AND num='" + str(lic_num) + "'"
                        " AND start_second='" + str(start_second) + "'"
                    )
                    existing = common_sqlite3.get_sql_table_data(usage_db_file, usage_db_conn, feature, ['id'], select_condition)

                    if existing:
                        continue

                    lmstat_match_condition = (
                        "WHERE server='" + str(license_server) + "'"
                        " AND feature='" + str(feature) + "'"
                        " AND user='" + str(out_event['user']) + "'"
                        " AND execute_host='" + str(out_event['host']) + "'"
                    )
                    lmstat_rows = common_sqlite3.get_sql_table_data(usage_db_file, usage_db_conn, feature, ['id', 'start_second'], lmstat_match_condition)

                    if lmstat_rows and lmstat_rows['id']:
                        for (i, row_start_second) in enumerate(lmstat_rows['start_second']):
                            try:
                                row_start = int(row_start_second)
                            except Exception:
                                row_start = 0

                            if abs(row_start - start_second) < 3600:
                                break
                        else:
                            value_list = ['NULL', sample_second, sample_time, license_server, vendor_daemon, feature,
                                          out_event['user'], 'N/A', out_event['host'], lic_num, 'N/A',
                                          start_second, start_time]
                            value_string = common_sqlite3.gen_sql_table_value_string(value_list, autoincrement=True)
                            common_sqlite3.insert_into_sql_table(usage_db_file, usage_db_conn, feature, value_string, commit=False)
                    else:
                        value_list = ['NULL', sample_second, sample_time, license_server, vendor_daemon, feature,
                                      out_event['user'], 'N/A', out_event['host'], lic_num, 'N/A',
                                      start_second, start_time]
                        value_string = common_sqlite3.gen_sql_table_value_string(value_list, autoincrement=True)
                        common_sqlite3.insert_into_sql_table(usage_db_file, usage_db_conn, feature, value_string, commit=False)

                for in_event in in_events:
                    feature = in_event['feature']

                    if feature not in usage_table_list:
                        continue

                    in_second = in_event['timestamp_second']
                    in_time_str = datetime.datetime.fromtimestamp(in_second).strftime('%Y%m%d_%H%M%S')

                    select_condition = (
                        "WHERE server='" + str(license_server) + "'"
                        " AND feature='" + str(feature) + "'"
                        " AND user='" + str(in_event['user']) + "'"
                        " AND execute_host='" + str(in_event['host']) + "'"
                    )
                    existing = common_sqlite3.get_sql_table_data(
                        usage_db_file, usage_db_conn, feature,
                        ['id', 'start_second', 'sample_second', 'start_time'],
                        select_condition,
                    )

                    if not existing or not existing['id']:
                        continue

                    best_row_id = None
                    best_diff = None

                    for (i, start_second_val) in enumerate(existing['start_second']):
                        try:
                            start_sec = int(start_second_val)
                            sample_sec = int(existing['sample_second'][i])
                        except Exception:
                            continue

                        if in_second < start_sec:
                            continue

                        if sample_sec > in_second:
                            continue

                        diff = in_second - start_sec

                        if (best_diff is None) or (diff < best_diff):
                            best_diff = diff
                            best_row_id = existing['id'][i]

                    if best_row_id is not None:
                        set_condition = (
                            "SET sample_second='" + str(in_second) + "',"
                            " sample_time='" + str(in_time_str) + "'"
                        )
                        where_condition = "WHERE id='" + str(best_row_id) + "'"
                        common_sqlite3.update_sql_table_data(usage_db_file, usage_db_conn, feature, set_condition, where_condition, commit=False)

                usage_db_conn.commit()
                usage_db_conn.close()

    def integrate_log_events_into_utilization_db(self):
        """
        Rebuild utilization curve gaps using log OUT/IN events.

        Strategy:
          1. For each feature, collect all utilization.db snapshot points.
          2. Merge them with OUT/IN events into a single time-ordered timeline.
          3. Walk the timeline to maintain the correct in_use count.
          4. Insert a snapshot into utilization.db for every event time that
             is not already covered by an lmstat snapshot.
             (sample_second is PRIMARY KEY so duplicates are silently ignored
              by INSERT OR IGNORE.)

        This fills in gaps where sessions started and ended entirely between
        two lmstat polls - those gaps previously left zero points on the curve.
        """
        if not self.log_events_dic:
            return

        print('>>> Integrating license log events into utilization db ...')

        for license_server in self.license_dic.keys():
            if license_server not in self.log_events_dic:
                continue

            events = self.log_events_dic[license_server]
            if not events:
                continue

            events_by_vendor_feature = {}
            for event in events:
                vendor_daemon = self.find_vendor_for_feature(license_server, event['feature'])

                if vendor_daemon:
                    events_by_vendor_feature.setdefault(vendor_daemon, {}).setdefault(event['feature'], []).append(event)

            for vendor_daemon in events_by_vendor_feature.keys():
                db_path = str(config.db_path) + '/license_server/' + str(license_server) + '/' + str(vendor_daemon)
                utilization_db_file = str(db_path) + '/utilization.db'

                if not os.path.exists(utilization_db_file):
                    continue

                (result, util_conn) = common_sqlite3.connect_db_file(utilization_db_file, mode='write')

                if result != 'passed':
                    continue

                util_table_list = common_sqlite3.get_sql_table_list(utilization_db_file, util_conn)

                for feature, feature_events in events_by_vendor_feature[vendor_daemon].items():
                    if feature not in util_table_list:
                        continue

                    feature_events.sort(key=lambda e: e['timestamp_second'])

                    existing_data = common_sqlite3.get_sql_table_data(
                        utilization_db_file, util_conn, feature,
                        ['sample_second', 'issued', 'in_use', 'utilization'],
                    )

                    existing_snapshots = {}
                    if existing_data and existing_data['sample_second']:
                        for (i, ss) in enumerate(existing_data['sample_second']):
                            try:
                                sec = int(ss)
                                existing_snapshots[sec] = {
                                    'issued': existing_data['issued'][i],
                                    'in_use': int(existing_data['in_use'][i]),
                                    'utilization': existing_data['utilization'][i],
                                }
                            except Exception:
                                continue

                    issued_anchor = ''
                    for sec in sorted(existing_snapshots.keys()):
                        issued_anchor = existing_snapshots[sec]['issued']
                        if issued_anchor and issued_anchor != '':
                            break

                    if not issued_anchor:
                        continue

                    for event in feature_events:
                        ts = event['timestamp_second']

                        if ts in existing_snapshots:
                            continue

                        if event['event_type'] == 'OUT':
                            lic_num = int(event['lic_num']) if re.match(r'^\d+$', str(event['lic_num'])) else 1
                            prev_sec = None
                            for sec in sorted(existing_snapshots.keys()):
                                if sec <= ts:
                                    prev_sec = sec
                                else:
                                    break

                            if prev_sec is None:
                                base_in_use = 0
                            else:
                                base_in_use = existing_snapshots[prev_sec]['in_use']

                            new_in_use = base_in_use + lic_num
                        elif event['event_type'] == 'IN':
                            prev_sec = None
                            for sec in sorted(existing_snapshots.keys()):
                                if sec <= ts:
                                    prev_sec = sec
                                else:
                                    break

                            if prev_sec is None:
                                lic_num = 1
                                new_in_use = 0
                            else:
                                lic_num = 1
                                new_in_use = max(0, existing_snapshots[prev_sec]['in_use'] - lic_num)
                        else:
                            continue

                        if issued_anchor == 'Uncounted':
                            new_utilization = 'Uncounted'
                        else:
                            try:
                                issued_int = int(issued_anchor)
                                new_utilization = round(100 * new_in_use / issued_int, 1) if issued_int > 0 else 0.0
                            except Exception:
                                new_utilization = 0.0

                        sample_time = datetime.datetime.fromtimestamp(ts).strftime('%Y%m%d_%H%M%S')
                        value_list = [ts, sample_time, issued_anchor, new_in_use, new_utilization]
                        value_string = common_sqlite3.gen_sql_table_value_string(value_list)
                        common_sqlite3.insert_into_sql_table(utilization_db_file, util_conn, feature, value_string, commit=False)

                        existing_snapshots[ts] = {
                            'issued': issued_anchor,
                            'in_use': new_in_use,
                            'utilization': new_utilization,
                        }

                util_conn.commit()
                util_conn.close()

    def find_vendor_for_feature(self, license_server, feature):
        """
        Find which vendor_daemon serves the given feature on specified license_server.
        """
        if license_server not in self.license_dic:
            return None

        for vendor_daemon in self.license_dic[license_server]['vendor_daemon'].keys():
            if feature in self.license_dic[license_server]['vendor_daemon'][vendor_daemon]['feature']:
                return vendor_daemon

        return None

    def sampling(self):
        if hasattr(config, 'db_path') and config.db_path:
            if self.usage_sampling:
                p = Process(target=self.sample_usage_info)
                p.start()

            if self.utilization_sampling:
                p = Process(target=self.sample_utilization_info)
                p.start()

            p.join()

            if self.log_events_dic:
                if self.usage_sampling:
                    self.integrate_log_events_into_usage_db()

                if self.utilization_sampling:
                    self.integrate_log_events_into_utilization_db()
        else:
            common.bprint('No "db_path" is specified on config/config.py.', level='Error')
            sys.exit(1)


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