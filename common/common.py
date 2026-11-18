import os
import re
import pandas
import socket
import datetime
import getpass
import subprocess


def bprint(message, color='', background_color='', display_method='', date_format='', level='', indent=0, end='\n', save_file='', save_file_method='a'):
    """
    Enhancement of "print" function.

    color:            Specify font foreground color, default to follow the terminal settings.
    background_color: Specify font background color, default to follow the terminal settings.
    display_method:   Specify font display method, default to follow the terminal settings.
    date_format:      Will show date/time information before the message, such as "%Y_%m_%d %H:%M:%S". Default is "", means silent mode.
    level:            Will show message level information after date/time information, default is "", means show nothing.
    indent:           How much spaces to indent for specified message (with level information), default is 0, means no indentation.
    end:              Specify the character at the end of the output, default is "\n".
    save_file:        Save message into specified file, default is "", means save nothing.
    save_file_method: Save message with "append" or "write" mode, default is "append" mode.

    For "color" and "background_color":
    -----------------------------------------------
    字体色   |   背景色   |   Color    |   颜色描述
    -----------------------------------------------
    30       |   40       |   black    |   黑色
    31       |   41       |   red      |   红色
    32       |   42       |   green    |   绿色
    33       |   43       |   yellow   |   黃色
    34       |   44       |   blue     |   蓝色
    35       |   45       |   purple   |   紫色
    36       |   46       |   cyan     |   青色
    37       |   47       |   white    |   白色
    -----------------------------------------------

    For "display_method":
    ---------------------------
    显示方式   |   效果
    ---------------------------
    0          |   终端默认设置
    1          |   高亮显示
    4          |   使用下划线
    5          |   闪烁
    7          |   反白显示
    8          |   不可见
    ---------------------------

    For "level":
    -------------------------------------------------------------
    层级      |   说明
    -------------------------------------------------------------
    Debug     |   程序运行的详细信息, 主要用于调试.
    Info      |   程序运行过程信息, 主要用于将系统状态反馈给用户.
    Warning   |   表明会出现潜在错误, 但是一般不影响系统继续运行.
    Error     |   发生错误, 不确定系统是否可以继续运行.
    Fatal     |   发生严重错误, 程序会停止运行并退出.
    -------------------------------------------------------------

    For "save_file_method":
    -----------------------------------------------------------
    模式   |   说明
    -----------------------------------------------------------
    a      |   append mode, append content to existing file.
    w      |   write mode, create a new file and write content.
    -----------------------------------------------------------
    """
    # Check arguments.
    color_dic = {'black': 30,
                 'red': 31,
                 'green': 32,
                 'yellow': 33,
                 'blue': 34,
                 'purple': 35,
                 'cyan': 36,
                 'white': 37}

    if color:
        if (color not in color_dic.keys()) and (color not in color_dic.values()):
            bprint('*Warning* (bprint): Meet some setting problem with below message.', date_format='', color=33, display_method=1)
            bprint('                    ' + str(message), date_format='', color=33, display_method=1)
            bprint('*Warning* (bprint): "' + str(color) + '": Invalid color setting, it must follow below rules.', date_format='', color=33, display_method=1)
            bprint('''
                    ----------------------------------
                    字体色   |   Color    |   颜色描述
                    ----------------------------------
                    30       |   black    |   黑色
                    31       |   red      |   红色
                    32       |   green    |   绿色
                    33       |   yellow   |   黃色
                    34       |   blue     |   蓝色
                    35       |   purple   |   紫色
                    36       |   cyan     |   青色
                    37       |   white    |   白色
                    ----------------------------------
            ''', date_format='', color=33, display_method=1)

            return

    background_color_dic = {'black': 40,
                            'red': 41,
                            'green': 42,
                            'yellow': 43,
                            'blue': 44,
                            'purple': 45,
                            'cyan': 46,
                            'white': 47}

    if background_color:
        if (background_color not in background_color_dic.keys()) and (background_color not in background_color_dic.values()):
            bprint('*Warning* (bprint): Meet some setting problem with below message.', date_format='', color=33, display_method=1)
            bprint('                    ' + str(message), date_format='', color=33, display_method=1)
            bprint('*Warning* (bprint): "' + str(background_color) + '": Invalid background_color setting, it must follow below rules.', date_format='', color=33, display_method=1)
            bprint('''
                    ----------------------------------
                    背景色   |   Color    |   颜色描述
                    ----------------------------------
                    40       |   black    |   黑色
                    41       |   red      |   红色
                    42       |   green    |   绿色
                    43       |   yellow   |   黃色
                    44       |   blue     |   蓝色
                    45       |   purple   |   紫色
                    46       |   cyan     |   青色
                    47       |   white    |   白色
                    ----------------------------------
            ''', date_format='', color=33, display_method=1)

            return

    if display_method:
        valid_display_method_list = [0, 1, 4, 5, 7, 8]

        if display_method not in valid_display_method_list:
            bprint('*Warning* (bprint): Meet some setting problem with below message.', date_format='', color=33, display_method=1)
            bprint('                    ' + str(message), date_format='', color=33, display_method=1)
            bprint('*Warning* (bprint): "' + str(display_method) + '": Invalid display_method setting, it must be integer between 0,1,4,5,7,8.', date_format='', color=33, display_method=1)
            bprint('''
                    ----------------------------
                    显示方式   |    效果
                    ----------------------------
                    0          |    终端默认设置
                    1          |    高亮显示
                    4          |    使用下划线
                    5          |    闪烁
                    7          |    反白显示
                    8          |    不可见
                    ----------------------------
            ''', date_format='', color=33, display_method=1)

            return

    if level:
        valid_level_list = ['Debug', 'Info', 'Warning', 'Error', 'Fatal']

        if level not in valid_level_list:
            bprint('*Warning* (bprint): Meet some setting problem with below message.', date_format='', color=33, display_method=1)
            bprint('                    ' + str(message), date_format='', color=33, display_method=1)
            bprint('*Warning* (bprint): "' + str(level) + '": Invalid level setting, it must be Debug/Info/Warning/Error/Fatal.', date_format='', color=33, display_method=1)
            bprint('''
                    -------------------------------------------------------------
                    层级      |   说明
                    -------------------------------------------------------------
                    Debug     |   程序运行的详细信息, 主要用于调试.
                    Info      |   程序运行过程信息, 主要用于将系统状态反馈给用户.
                    Warning   |   表明会出现潜在错误, 但是一般不影响系统继续运行.
                    Error     |   发生错误, 不确定系统是否可以继续运行.
                    Fatal     |   发生严重错误, 程序会停止运行并退出.
                    -------------------------------------------------------------
            ''', date_format='', color=33, display_method=1)
            return

    if not re.match(r'^\d+$', str(indent)):
        bprint('*Warning* (bprint): Meet some setting problem with below message.', date_format='', color=33, display_method=1)
        bprint('                    ' + str(message), date_format='', color=33, display_method=1)
        bprint('*Warning* (bprint): "' + str(indent) + '": Invalid indent setting, it must be a positive integer, will reset to "0".', date_format='', color=33, display_method=1)

        indent = 0

    if save_file:
        valid_save_file_method_list = ['a', 'append', 'w', 'write']

        if save_file_method not in valid_save_file_method_list:
            bprint('*Warning* (bprint): Meet some setting problem with below message.', date_format='', color=33, display_method=1)
            bprint('                    ' + str(message), date_format='', color=33, display_method=1)
            bprint('*Warning* (bprint): "' + str(save_file_method) + '": Invalid save_file_method setting, it must be "a" or "w".', date_format='', color=33, display_method=1)
            bprint('''
                    -----------------------------------------------------------
                    模式   |   说明
                    -----------------------------------------------------------
                    a      |   append mode, append content to existing file.
                    w      |   write mode, create a new file and write content.
                    -----------------------------------------------------------
            ''', date_format='', color=33, display_method=1)

            return

    # Set default color/background_color/display_method setting for different levels.
    if level:
        if level == 'Warning':
            if not display_method:
                display_method = 1

            if not color:
                color = 33
        elif level == 'Error':
            if not display_method:
                display_method = 1

            if not color:
                color = 31
        elif level == 'Fatal':
            if not display_method:
                display_method = 1

            if not background_color:
                background_color = 41

            if background_color == 41:
                if not color:
                    color = 37
            else:
                if not color:
                    color = 35

    # Get final color setting.
    final_color_setting = ''

    if color or background_color or display_method:
        final_color_setting = '\033['

        if display_method:
            final_color_setting = str(final_color_setting) + str(display_method)

        if color:
            if not re.match(r'^\d{2}$', str(color)):
                color = color_dic[color]

            if re.match(r'^.*\d$', final_color_setting):
                final_color_setting = str(final_color_setting) + ';' + str(color)
            else:
                final_color_setting = str(final_color_setting) + str(color)

        if background_color:
            if not re.match(r'^\d{2}$', str(background_color)):
                background_color = background_color_dic[background_color]

            if re.match(r'^.*\d$', final_color_setting):
                final_color_setting = str(final_color_setting) + ';' + str(background_color)
            else:
                final_color_setting = str(final_color_setting) + str(background_color)

        final_color_setting = str(final_color_setting) + 'm'

    # Get current_time if date_format is specified.
    current_time = ''

    if date_format:
        try:
            current_time = datetime.datetime.now().strftime(date_format)
        except Exception:
            bprint('*Warning* (bprint): Meet some setting problem with below message.', date_format='', color=33, display_method=1)
            bprint('                    ' + str(message), date_format='', color=33, display_method=1)
            bprint('*Warning* (bprint): "' + str(date_format) + '": Invalid date_format setting, suggest to use the default setting.', date_format='', color=33, display_method=1)
            return

    # Print message with specified format.
    final_message = ''

    if current_time:
        final_message = str(final_message) + '[' + str(current_time) + '] '

    if indent > 0:
        final_message = str(final_message) + ' ' * indent

    if level:
        final_message = str(final_message) + '*' + str(level) + '*: '

    final_message = str(final_message) + str(message)

    if final_color_setting:
        final_message_with_color = final_color_setting + str(final_message) + '\033[0m'
    else:
        final_message_with_color = final_message

    print(final_message_with_color, end=end)

    # Save file.
    if save_file:
        try:
            with open(save_file, save_file_method) as SF:
                SF.write(str(final_message) + '\n')
        except Exception as warning:
            bprint('*Warning* (bprint): Meet some problem when saveing below message into file "' + str(save_file) + '".', date_format='', color=33, display_method=1)
            bprint('                    ' + str(message), date_format='', color=33, display_method=1)
            bprint('*Warning* (bprint): ' + str(warning), date_format='', color=33, display_method=1)
            return


def run_command(command, mystdin=subprocess.PIPE, mystdout=subprocess.PIPE, mystderr=subprocess.PIPE):
    """
    Run system command with subprocess.Popen, get returncode/stdout/stderr.
    """
    SP = subprocess.Popen(command, shell=True, stdin=mystdin, stdout=mystdout, stderr=mystderr)
    (stdout, stderr) = SP.communicate()

    return SP.returncode, stdout, stderr


def write_csv(csv_file, content_dic):
    """
    Write csv with content_dic.
    content_dic = {
        'title_1': [column1_1, columne1_2, ...],
        'title_2': [column2_1, columne2_2, ...],
        ...
    }
    """
    df = pandas.DataFrame(content_dic)
    df.to_csv(csv_file, index=False)


def ssh_client(host_name='', port=22, user_name=getpass.getuser(), password='', command='', reconnect=False, timeout=10):
    """
    Ssh specified host with the system ssh command (subprocess, the lowest
    level ssh operation), execute specified command, get stdout information
    (return stdout_list).

    This function is designed to be safe for automatic tasks (for example
    cron), ssh can never make the caller hang or wait for input:

      - BatchMode=yes: ssh never prompts for password/passphrase, it fails
        immediately when key authentication does not work.
      - stdin=DEVNULL: the ssh child process can never read any input, so
        there is no interactive password input any more.
      - ConnectTimeout bounds the tcp connect and the subprocess timeout
        bounds the whole command, therefore ssh_client is guaranteed to
        return even if the network or the remote sshd hangs.

    The "password/reconnect" arguments are kept for interface compatibility,
    they are not used any more (only key based authentication is supported).
    """
    stdout_list = []

    if (not host_name) or (not command):
        bprint('Ssh host_name and command are required.', level='Error')
        return stdout_list

    ssh_command = [
        'ssh',
        '-p', str(port),
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=' + str(timeout),
        '-o', 'StrictHostKeyChecking=no',
        str(user_name) + '@' + str(host_name),
        str(command),
    ]

    # "timeout" bounds the tcp connect (ConnectTimeout), the subprocess
    # timeout additionally bounds the whole command execution.
    subprocess_timeout = int(timeout) + 30

    try:
        completed_process = subprocess.run(
            ssh_command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            errors='replace',
            timeout=subprocess_timeout,
        )

        if completed_process.returncode == 0:
            stdout_list = str(completed_process.stdout).splitlines()
        elif completed_process.returncode == 1:
            # Remote command finished with exit status 1 (for example grep
            # found no match), stdout is still a valid (usually empty) result.
            stdout_list = str(completed_process.stdout).splitlines()
        else:
            # Ssh level failure (exit status 255 and so on): do not return
            # partial output, let the caller treat it as a failed connection.
            bprint('Ssh connection is failed on "' + str(user_name) + '@' + str(host_name) + '" (exit status: ' + str(completed_process.returncode) + ').', level='Error')

            stderr_message = str(completed_process.stderr).strip()

            if stderr_message:
                bprint(stderr_message.splitlines()[0], color='red', display_method=1, indent=9)
    except subprocess.TimeoutExpired:
        bprint('Ssh timeout on "' + str(user_name) + '@' + str(host_name) + '" after ' + str(subprocess_timeout) + ' seconds.', level='Error')
    except FileNotFoundError:
        bprint('Ssh command is not found, please make sure "ssh" is installed on this host.', level='Error')
    except Exception as error:
        bprint('Meet below error when ssh ' + str(host_name), level='Error')
        bprint(error, color='red', display_method=1, indent=9)

    return stdout_list


def parse_project_list_file(project_list_file):
    """
    Parse project_list_file and return list "project_list".
    """
    project_list = []

    if os.path.exists(project_list_file):
        with open(project_list_file, 'r') as PLF:
            for line in PLF.readlines():
                line = line.strip()

                if re.match(r'^\s*#.*$', line) or re.match(r'^\s*$', line):
                    continue
                else:
                    if line not in project_list:
                        project_list.append(line)

    return project_list


def parse_project_proportion_file(project_proportion_file, project_list=[]):
    """
    Parse project_*_file and return dictory "project_proportion_dic".
    """
    project_proportion_dic = {}

    if project_proportion_file and os.path.exists(project_proportion_file):
        with open(project_proportion_file, 'r') as PPF:
            for line in PPF.readlines():
                line = line.strip()

                if re.match(r'^\s*#.*$', line) or re.match(r'^\s*$', line):
                    continue
                elif re.match(r'^(\S+)\s*:\s*(\S+)$', line):
                    my_match = re.match(r'^(\S+)\s*:\s*(\S+)$', line)
                    item = my_match.group(1)
                    project = my_match.group(2)

                    if item in project_proportion_dic.keys():
                        bprint('"' + str(item) + '": repeated item on "' + str(project_proportion_file) + '", ignore.', level='Warning')
                        continue
                    else:
                        project_proportion_dic[item] = {project: 1}
                elif re.match(r'^(\S+)\s*:\s*(.+)$', line):
                    my_match = re.match(r'^(\S+)\s*:\s*(.+)$', line)
                    item = my_match.group(1)
                    project_string = my_match.group(2)
                    tmp_dic = {}

                    for project_setting in project_string.split():
                        if re.match(r'^(\S+)\((0.\d+)\)$', project_setting):
                            my_match = re.match(r'^(\S+)\((0.\d+)\)$', project_setting)
                            project = my_match.group(1)
                            project_proportion = my_match.group(2)

                            if project_list and (project not in project_list):
                                bprint('"' + str(project) + '": Invalid project on "' + str(project_proportion_file) + '", not on project_list.', level='Warning')
                                bprint(line, color='yellow', display_method=1, indent=11)
                                tmp_dic = {}
                                break

                            if project in tmp_dic.keys():
                                bprint('"' + str(project) + '": Repeated project on "' + str(project_proportion_file) + '".', level='Warning')
                                bprint(line, color='yellow', display_method=11, indent=11)
                                tmp_dic = {}
                                break

                            tmp_dic[project] = float(project_proportion)
                        else:
                            tmp_dic = {}
                            break

                    if not tmp_dic:
                        bprint('Invalid line on "' + str(project_proportion_file) + '", ignore.', level='Warning')
                        bprint(line, color='yellow', display_method=1, indent=11)
                        continue
                    else:
                        sum_proportion = sum(list(tmp_dic.values()))

                        if sum_proportion == 1.0:
                            project_proportion_dic[item] = tmp_dic
                        else:
                            bprint('Invalid line on "' + str(project_proportion_file) + '", ignore.', level='Warning')
                            bprint(line, color='yellow', display_method=1, indent=11)
                            continue

                else:
                    bprint('Invalid line on "' + str(project_proportion_file) + '", ignore.', level='Warning')
                    bprint(line, color='yellow', display_method=1, indent=11)
                    continue

    return project_proportion_dic


def parse_project_setting_db_path(db_path):
    """
    Parse project_setting db_path, and get project_list/project_submit_host/project_execute_host/project_user related settings.
    """
    project_setting_dic = {}
    valid_item_list = ['project_list', 'project_submit_host', 'project_execute_host', 'project_user']

    for create_time in os.listdir(db_path):
        create_time_path = str(db_path) + '/' + str(create_time)

        if os.path.isdir(create_time_path) and re.match(r'^\d{14}$', create_time):
            for item_name in os.listdir(create_time_path):
                if item_name in valid_item_list:
                    if item_name == 'project_list':
                        item_value = parse_project_list_file(str(create_time_path) + '/' + str(item_name))
                    else:
                        item_value = parse_project_proportion_file(str(create_time_path) + '/' + str(item_name))

                    project_setting_dic.setdefault(create_time, {})
                    project_setting_dic[create_time].setdefault(item_name, item_value)

    return project_setting_dic
