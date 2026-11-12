# -*- coding: utf-8 -*-
import os
import re
import sys
import json
import time
import datetime
import yaml

sys.path.append(os.environ['LICENSE_MONITOR_INSTALL_PATH'])
from common import common


class LicenseLogParser():
    """
    Incrementally parse FlexNet license debug log files.
    Tracks file position across runs so only new lines are processed each time.
    """

    def __init__(self, log_config_file='', db_path=''):
        self.log_config_file = log_config_file
        self.db_path = db_path
        self.state_file = str(db_path) + '/license_log_state.json' if db_path else ''
        self.log_dic = {}
        self.state_dic = {}

        self.load_state()
        self.load_log_config()

    def load_state(self):
        """
        Load saved file offsets from previous run.
        """
        if self.state_file and os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as SF:
                    self.state_dic = json.load(SF)
            except Exception as error:
                common.bprint('Failed on loading license log state from "' + str(self.state_file) + '".', level='Warning')
                common.bprint(error, color='yellow', display_method=1, indent=9)
                self.state_dic = {}

    def save_state(self):
        """
        Save current file offsets for next run.
        """
        if self.state_file:
            state_dir = os.path.dirname(self.state_file)

            if state_dir and (not os.path.exists(state_dir)):
                try:
                    os.makedirs(state_dir, mode=0o755)
                except Exception as error:
                    common.bprint('Failed on creating directory "' + str(state_dir) + '" for license log state.', level='Warning')
                    return

            try:
                with open(self.state_file, 'w') as SF:
                    json.dump(self.state_dic, SF, indent=2)
            except Exception as error:
                common.bprint('Failed on saving license log state to "' + str(self.state_file) + '".', level='Warning')

    def load_log_config(self):
        """
        Load license log path mapping from yaml config file.
        Config format: {license_server: license_log_path}
        """
        if self.log_config_file and os.path.exists(self.log_config_file):
            try:
                with open(self.log_config_file, 'r') as LCF:
                    self.log_dic = yaml.load(LCF, Loader=yaml.FullLoader)
            except Exception as error:
                common.bprint('Failed on loading license log config from "' + str(self.log_config_file) + '".', level='Warning')
                common.bprint(error, color='yellow', display_method=1, indent=9)
                self.log_dic = {}

    def get_log_events(self, license_server):
        """
        Parse new lines from the license log for specified license_server.
        Return a list of event dicts, each with keys:
          - timestamp_second: unix timestamp (int)
          - timestamp_str:    original timestamp string from log
          - event_type:       'OUT' (checkout) or 'IN' (checkin)
          - feature:          feature name
          - user:             user name
          - host:             execute host
          - lic_num:          number of licenses (default 1)
        """
        event_list = []

        if license_server not in self.log_dic:
            return event_list

        log_path = self.log_dic[license_server]

        if not os.path.exists(log_path):
            common.bprint('License log file "' + str(log_path) + '" does not exist for server "' + str(license_server) + '".', level='Warning')
            return event_list

        current_size = os.path.getsize(log_path)
        last_offset = self.state_dic.get(log_path, {}).get('offset', 0) if self.state_dic else 0

        if current_size < last_offset:
            common.bprint('License log "' + str(log_path) + '" appears to have been rotated (size=' + str(current_size) + ' < offset=' + str(last_offset) + '). Will read from beginning.', level='Info')
            last_offset = 0

        try:
            with open(log_path, 'r', errors='ignore') as LF:
                LF.seek(last_offset)
                new_content = LF.read()
                new_offset = LF.tell()
        except Exception as error:
            common.bprint('Failed on reading license log "' + str(log_path) + '".', level='Warning')
            common.bprint(error, color='yellow', display_method=1, indent=9)
            return event_list

        for line in new_content.split('\n'):
            event = self.parse_log_line(line.strip())

            if event:
                event['license_server'] = license_server
                event_list.append(event)

        self.state_dic.setdefault(log_path, {})
        self.state_dic[log_path]['offset'] = new_offset
        self.save_state()

        return event_list

    def parse_log_line(self, line):
        """
        Parse a single license log line, return event dict or None.
        Handles common FlexNet log formats:
          09:45:11 (vendor) OUT: "feature" user@host
          11/12/2025 09:45:11 (vendor) OUT: "feature" user@host
          09:45:11 (vendor) OUT: "feature" user@host  (LICENSE pcount: 3)
          09:45:11 (vendor) IN: "feature" user@host
          09:45:11 (vendor) IN: "feature" user@host  (delay: 1234)
        """
        if not line:
            return None

        out_pattern = re.compile(
            r'^(\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2}:\d{2})\s+'
            r'\(\S+\)\s+'
            r'OUT:\s+"([^"]+)"\s+'
            r'(\S+)@(\S+)'
        )
        pcount_pattern = re.compile(r'LICENSE\s+pcount:\s*(\d+)')
        in_pattern = re.compile(
            r'^(\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2}:\d{2})\s+'
            r'\(\S+\)\s+'
            r'IN:\s+"([^"]+)"\s+'
            r'(\S+)@(\S+)'
        )

        my_match = out_pattern.match(line)
        if my_match:
            timestamp_str = my_match.group(1)
            feature = my_match.group(2)
            user = my_match.group(3)
            host = my_match.group(4)
            pcount_match = pcount_pattern.search(line)
            lic_num = pcount_match.group(1) if pcount_match else '1'
            event_type = 'OUT'
        else:
            my_match = in_pattern.match(line)
            if not my_match:
                return None

            timestamp_str = my_match.group(1)
            feature = my_match.group(2)
            user = my_match.group(3)
            host = my_match.group(4)
            lic_num = '1'
            event_type = 'IN'

        timestamp_second = self.convert_log_timestamp(timestamp_str)
        if timestamp_second is None:
            return None

        return {
            'timestamp_second': timestamp_second,
            'timestamp_str': timestamp_str,
            'event_type': event_type,
            'feature': feature,
            'user': user,
            'host': host,
            'lic_num': lic_num,
        }

    def convert_log_timestamp(self, timestamp_str):
        """
        Convert license log timestamp string to unix timestamp (seconds).
        Supports two common formats:
          - "09:45:11"           (no date, assume today)
          - "11/12/2025 09:45:11"  (with MM/DD/YYYY date)
        """
        now = datetime.datetime.now()

        try:
            if re.match(r'^\d{1,2}:\d{2}:\d{2}$', timestamp_str):
                ts = datetime.datetime.strptime(timestamp_str, '%H:%M:%S')
                full_dt = now.replace(hour=ts.hour, minute=ts.minute, second=ts.second, microsecond=0)

                if full_dt > now + datetime.timedelta(minutes=5):
                    full_dt = full_dt - datetime.timedelta(days=1)

                return int(time.mktime(full_dt.timetuple()))
            elif re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}:\d{2}$', timestamp_str):
                ts = datetime.datetime.strptime(timestamp_str, '%m/%d/%Y %H:%M:%S')
                return int(time.mktime(ts.timetuple()))
            else:
                return None
        except Exception:
            return None