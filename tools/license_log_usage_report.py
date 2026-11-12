#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import sys
import time
import datetime
import argparse
from collections import defaultdict


DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def read_args():
    parser = argparse.ArgumentParser(
        description='Generate a day-by-day, user-by-user license usage report from a FlexNet debug log.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python license_log_usage_report.py --log /flexnet/logs/debug.log
  python license_log_usage_report.py --log /flexnet/logs/debug.log --start 2025-11-01 --end 2025-11-07
  python license_log_usage_report.py --log /flexnet/logs/debug.log --user zhangsan
  python license_log_usage_report.py --log /flexnet/logs/debug.log --feature cadence_virtuoso --days 30
'''
    )

    parser.add_argument('-l', '--log', required=True, help='Path to the FlexNet license debug log file.')
    parser.add_argument('-s', '--start', default='', help='Start date filter (YYYY-MM-DD). Inclusive.')
    parser.add_argument('-e', '--end', default='', help='End date filter (YYYY-MM-DD). Inclusive.')
    parser.add_argument('-d', '--days', type=int, default=0, help='Report the most recent N days (overrides --start).')
    parser.add_argument('-u', '--user', default='', help='Only show sessions for this user (case-insensitive substring match).')
    parser.add_argument('-f', '--feature', default='', help='Only show sessions for this feature (case-insensitive substring match).')
    parser.add_argument('--host', default='', help='Only show sessions from this host (case-insensitive substring match).')

    args = parser.parse_args()

    if not os.path.exists(args.log):
        print('ERROR: Log file does not exist: ' + str(args.log))
        sys.exit(1)

    return args


def convert_log_timestamp(ts_str):
    now = datetime.datetime.now()

    if re.match(r'^\d{1,2}:\d{2}:\d{2}$', ts_str):
        ts = datetime.datetime.strptime(ts_str, '%H:%M:%S')
        full = now.replace(hour=ts.hour, minute=ts.minute, second=ts.second, microsecond=0)
        if full > now + datetime.timedelta(minutes=5):
            full = full - datetime.timedelta(days=1)
        return full
    elif re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}:\d{2}$', ts_str):
        ts = datetime.datetime.strptime(ts_str, '%m/%d/%Y %H:%M:%S')
        return ts
    else:
        return None


def parse_log_file(log_path, start_dt=None, end_dt=None):
    out_pattern = re.compile(
        r'^(\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2}:\d{2})\s+'
        r'\(\S+\)\s+'
        r'OUT:\s+"([^"]+)"\s+'
        r'(\S+)@(\S+)'
    )
    in_pattern = re.compile(
        r'^(\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2}:\d{2})\s+'
        r'\(\S+\)\s+'
        r'IN:\s+"([^"]+)"\s+'
        r'(\S+)@(\S+)'
    )
    pcount_pattern = re.compile(r'LICENSE\s+pcount:\s*(\d+)')

    out_events = []
    in_events = []

    with open(log_path, 'r', errors='ignore') as LF:
        for line in LF:
            line = line.strip()
            if not line:
                continue

            m = out_pattern.match(line)
            if m:
                ts = convert_log_timestamp(m.group(1))
                if ts is None:
                    continue
                if start_dt and ts.date() < start_dt.date():
                    continue
                if end_dt and ts.date() > end_dt.date():
                    continue

                pcount_m = pcount_pattern.search(line)
                lic_num = int(pcount_m.group(1)) if pcount_m else 1

                out_events.append({
                    'timestamp': ts,
                    'feature': m.group(2),
                    'user': m.group(3),
                    'host': m.group(4),
                    'lic_num': lic_num,
                    'lic_num_raw': str(pcount_m.group(1)) if pcount_m else '1',
                })
                continue

            m = in_pattern.match(line)
            if m:
                ts = convert_log_timestamp(m.group(1))
                if ts is None:
                    continue
                if start_dt and ts.date() < start_dt.date():
                    continue
                if end_dt and ts.date() > end_dt.date():
                    continue

                in_events.append({
                    'timestamp': ts,
                    'feature': m.group(2),
                    'user': m.group(3),
                    'host': m.group(4),
                })

    out_events.sort(key=lambda e: e['timestamp'])
    in_events.sort(key=lambda e: e['timestamp'])

    return out_events, in_events


def pair_sessions(out_events, in_events):
    open_out = defaultdict(list)
    sessions = []

    for out in out_events:
        key = (out['user'], out['host'], out['feature'])
        open_out[key].append(out)

    consumed_in = [False] * len(in_events)

    for in_idx, in_ev in enumerate(in_events):
        key = (in_ev['user'], in_ev['host'], in_ev['feature'])
        candidates = open_out.get(key, [])

        best_idx = None
        best_diff = None

        for ci, co in enumerate(candidates):
            if co['timestamp'] > in_ev['timestamp']:
                break
            diff = (in_ev['timestamp'] - co['timestamp']).total_seconds()
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_idx = ci

        if best_idx is not None:
            co = candidates.pop(best_idx)
            sessions.append({
                'user': co['user'],
                'host': co['host'],
                'feature': co['feature'],
                'lic_num': co['lic_num'],
                'lic_num_raw': co['lic_num_raw'],
                'checkout': co['timestamp'],
                'checkin': in_ev['timestamp'],
                'duration_sec': (in_ev['timestamp'] - co['timestamp']).total_seconds(),
                'status': 'closed',
            })
            consumed_in[in_idx] = True

    for key, candidates in open_out.items():
        for co in candidates:
            sessions.append({
                'user': co['user'],
                'host': co['host'],
                'feature': co['feature'],
                'lic_num': co['lic_num'],
                'lic_num_raw': co['lic_num_raw'],
                'checkout': co['timestamp'],
                'checkin': None,
                'duration_sec': (datetime.datetime.now() - co['timestamp']).total_seconds(),
                'status': 'active',
            })

    return sessions


def fmt_duration(sec):
    sec = int(sec)
    days, remainder = divmod(sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    if days > 0:
        return '{d}d {h}h {m}m'.format(d=days, h=hours, m=minutes)
    elif hours > 0:
        return '{h}h {m}m'.format(h=hours, m=minutes)
    elif minutes > 0:
        return '{m}m'.format(m=minutes)
    else:
        return '<1m'


def fmt_time(dt):
    return dt.strftime('%H:%M:%S')


def fmt_date(dt):
    return dt.strftime('%Y-%m-%d')


def filter_sessions(sessions, user_filter='', feature_filter='', host_filter=''):
    result = []
    u_lower = user_filter.lower()
    f_lower = feature_filter.lower()
    h_lower = host_filter.lower()

    for s in sessions:
        if u_lower and u_lower not in s['user'].lower():
            continue
        if f_lower and f_lower not in s['feature'].lower():
            continue
        if h_lower and h_lower not in s['host'].lower():
            continue
        result.append(s)

    return result


def report(sessions, log_path, start_dt, end_dt):
    sessions.sort(key=lambda s: (s['checkout'].date(), s['user'].lower(), s['feature'].lower(), s['checkout']))

    print('=' * 90)
    print('  LICENSE USAGE REPORT')
    print('  Generated: ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print('  Log file : ' + log_path)
    print('  Range    : ' + fmt_date(start_dt) + '  →  ' + fmt_date(end_dt) + '  (' + str((end_dt - start_dt).days + 1) + ' days)')
    print('  Sessions : ' + str(len(sessions)) + '  (' + str(sum(1 for s in sessions if s['status'] == 'active')) + ' active)')
    print('=' * 90)

    if not sessions:
        print('\n  No sessions found.\n')
        return

    day_user_feature = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for s in sessions:
        day_user_feature[s['checkout'].date()][s['user'].lower()][s['feature']].append(s)

    print('')
    print('-' * 90)
    print('  SESSION DETAIL (grouped by date, then user, then feature)')
    print('-' * 90)

    for day in sorted(day_user_feature.keys()):
        dt_obj = datetime.datetime.combine(day, datetime.time())
        print('')
        print('  DATE: ' + fmt_date(day) + ' (' + DAY_NAMES[dt_obj.weekday()] + ')')
        print('  ' + '-' * 86)

        for user in sorted(day_user_feature[day].keys()):
            user_sessions_total = sum(
                sum(s['lic_num'] for s in day_user_feature[day][user][feat])
                for feat in day_user_feature[day][user]
            )
            user_duration_total = sum(
                sum(s['duration_sec'] for s in day_user_feature[day][user][feat])
                for feat in day_user_feature[day][user]
            )
            user_session_count = sum(
                len(day_user_feature[day][user][feat])
                for feat in day_user_feature[day][user]
            )

            print('')
            print('    User: ' + user)
            print('      Sessions: ' + str(user_session_count) + '  |  Licenses acquired (total): ' + str(user_sessions_total) + '  |  Total duration: ' + fmt_duration(user_duration_total))

            for feature in sorted(day_user_feature[day][user].keys()):
                sessions_of = day_user_feature[day][user][feature]
                sessions_of.sort(key=lambda s: s['checkout'])

                print('')
                print('      Feature: ' + feature + '  (' + str(len(sessions_of)) + ' session(s))')
                print('      ' + '-' * 80)
                print('      ' + '{:<12} {:<12} {:<12} {:>9} {:<18} {:<8}'.format(
                    'CHECKOUT', 'CHECKIN', 'HOST', 'LICENSES', 'DURATION', 'STATUS'))
                print('      ' + '-' * 80)

                for s in sessions_of:
                    ckout = fmt_time(s['checkout'])
                    if s['status'] == 'closed':
                        ckin = fmt_time(s['checkin'])
                        duration_str = fmt_duration(s['duration_sec'])
                        status_str = ''
                    else:
                        ckin = '—'
                        duration_str = fmt_duration(s['duration_sec']) + '(running)'
                        status_str = 'ACTIVE'

                    print('      ' + '{:<12} {:<12} {:<12} {:>9} {:<18} {:<8}'.format(
                        ckout,
                        ckin,
                        s['host'][:10],
                        str(s['lic_num']),
                        duration_str,
                        status_str))

    print('')
    print('')
    print('-' * 90)
    print('  USER SUMMARY (across entire report range)')
    print('-' * 90)

    user_total = defaultdict(lambda: {'sessions': 0, 'licenses': 0, 'duration_sec': 0, 'days_active': set()})
    for s in sessions:
        u = s['user'].lower()
        user_total[u]['sessions'] += 1
        user_total[u]['licenses'] += s['lic_num']
        user_total[u]['duration_sec'] += s['duration_sec']
        user_total[u]['days_active'].add(s['checkout'].date())

    print('')
    print('  {:<16} {:>10} {:>10} {:>14} {:>10}'.format(
        'USER', 'SESSIONS', 'LICENSES', 'TOTAL DURATION', 'DAYS USED'))
    print('  ' + '-' * 66)

    for u in sorted(user_total.keys(), key=lambda x: -user_total[x]['duration_sec']):
        ut = user_total[u]
        print('  {:<16} {:>10} {:>10} {:>14} {:>10}'.format(
            u,
            str(ut['sessions']),
            str(ut['licenses']),
            fmt_duration(ut['duration_sec']),
            str(len(ut['days_active']))))

    print('')
    print('')
    print('-' * 90)
    print('  FEATURE SUMMARY (across entire report range)')
    print('-' * 90)

    feat_total = defaultdict(lambda: {'sessions': 0, 'licenses': 0, 'duration_sec': 0, 'users': set()})
    for s in sessions:
        f = s['feature']
        feat_total[f]['sessions'] += 1
        feat_total[f]['licenses'] += s['lic_num']
        feat_total[f]['duration_sec'] += s['duration_sec']
        feat_total[f]['users'].add(s['user'].lower())

    print('')
    print('  {:<30} {:>10} {:>10} {:>14} {:>10}'.format(
        'FEATURE', 'SESSIONS', 'LICENSES', 'TOTAL DURATION', 'USERS'))
    print('  ' + '-' * 86)

    for f in sorted(feat_total.keys(), key=lambda x: -feat_total[x]['duration_sec']):
        ft = feat_total[f]
        print('  {:<30} {:>10} {:>10} {:>14} {:>10}'.format(
            f[:30],
            str(ft['sessions']),
            str(ft['licenses']),
            fmt_duration(ft['duration_sec']),
            str(len(ft['users']))))

    print('')


def main():
    args = read_args()

    now = datetime.datetime.now()

    if args.days and args.days > 0:
        start_dt = now - datetime.timedelta(days=args.days - 1)
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif args.start:
        start_dt = datetime.datetime.strptime(args.start, '%Y-%m-%d')
    else:
        start_dt = now - datetime.timedelta(days=29)
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    if args.end:
        end_dt = datetime.datetime.strptime(args.end, '%Y-%m-%d') + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
    else:
        end_dt = now

    print('')
    print('  Parsing license log: ' + args.log)
    print('  Date range: ' + fmt_date(start_dt) + ' → ' + fmt_date(end_dt))

    out_events, in_events = parse_log_file(args.log, start_dt=start_dt, end_dt=end_dt)
    print('  OUT events: ' + str(len(out_events)))
    print('  IN  events: ' + str(len(in_events)))

    sessions = pair_sessions(out_events, in_events)
    sessions = filter_sessions(
        sessions,
        user_filter=args.user,
        feature_filter=args.feature,
        host_filter=args.host,
    )
    print('  Paired sessions: ' + str(len(sessions)))
    print('')

    report(sessions, args.log, start_dt, end_dt)


if __name__ == '__main__':
    main()