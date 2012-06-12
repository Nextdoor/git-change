# Copyright 2012 Nextdoor.com, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utilities to support git subcommands."""

__author__ = 'jacob@nextdoor.com (Jacob Hesch)'

import os
import shlex
import simplejson
import subprocess
import sys

import gflags

gflags.DEFINE_string('remote', 'origin',
                     'Name of the remote repository to fetch from and push to. '
                     'Defaults to the `git-change.remote` git config option if '
                     'it is set, otherwise "origin".')
gflags.DEFINE_string('gerrit-ssh-host', None,
                     'Name of the Gerrit server hosting the Git repository. '
                     'Defaults to the `git-change.gerrit-host` git config '
                     'option if it is set. Required unless the config '
                     'option is set.')

gflags.DEFINE_bool('dry-run', False, 'Echo commands but do not execute them.', short_name='n')

FLAGS = gflags.FLAGS


class Error(Exception):
    """Base exception type."""


class GitError(Error):
    """Git exception type."""


# Copied from subprocess.py of Python 2.7 and modified.
class CalledProcessError(GitError):
    """Signals a failed subprocess execution.

    This exception type is like subprocess.CalledProcessError
    (introduced in PYthon 2.7), but has two additional instance
    attributes: stdout and stderr. The redundant and ambiguous
    'output' attribute is kept for compatibility and for cases
    where stdout and stderr are combined.

    This exception is raised when a process run by check_call() or
    check_output() returns a non-zero exit status.
    The exit status will be stored in the returncode attribute;
    check_output() will also store the output in the output attribute.
    """

    def __init__(self, returncode, cmd, output=None, stdout=None, stderr=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return 'Command "%s" returned non-zero exit status %d' % (self.cmd, self.returncode)


def run_command(command, env=None, trap_stdout=False,
                trap_stderr=False, output_on_error=True):
    """Runs the given command as a subprocess.

    By default, the subprocess inherits the stdout and stderr file
    handles from the calling process. This behavior can be changed by
    setting the trap_stdout and trap_stderr arguments to True.

    Args:
        command: A string representing the command to run.
        env: A dictionary representing command's environment. Note
            that these are added to the parent process's environment.
        trap_stdout: If True, command's stdout is captured and returned.
            If False, command inherits the stdout file handle of the
            calling process.
        trap_stderr: If True, command's stderr is captured and returned.
            If False, command inherits the stderr file handle of the
            calling process.
        output_on_error: A boolean to flag whether to print output if
            an error running command occurs.

    Returns:
        A string or tuple of strings representing the command's output
        or None depending on the values of the stdout and stderr
        arguments. Here are the return values according to those
        arguments:
            trap_stdout=False, trap_stderr=False (default): returns None
            trap_stdout=True, trap_stderr=False: returns stdout
            trap_stdout=False, trap_stderr=True: returns stderr
            trap_stdout=True, trap_stderr=True: returns (stdout, stderr)

    Raises:
        CalledProcessError: The command exited with a non-zero status.
            If stdout and stderr are trapped, the output to those file
            handles from the subprocess will be attached to the
            exception object.
    """
    if FLAGS['dry-run'].value:
        print 'run_command >>> %s' % command
        return 'dry-run-no-output\n'

    new_env = os.environ.copy()
    if env is not None:
        new_env.update(env)

    command_list = shlex.split(command)

    stdout = stderr = None
    if trap_stdout:
        stdout = subprocess.PIPE
    if trap_stderr:
        stderr = subprocess.PIPE

    process = subprocess.Popen(command_list, env=new_env, stdout=stdout, stderr=stderr)
    stdout, stderr = process.communicate()
    return_code = process.poll()
    if return_code:
        if output_on_error:
            print 'Error running "%s"' % command
            print '  return code: %s' % return_code
            if trap_stdout:
                print '  stdout: %s' % stdout
            if trap_stderr:
                print '  stderr: %s' % stderr
        raise CalledProcessError(return_code, command, output=stderr, stdout=stdout, stderr=stderr)

    if stdout is not None and stderr is not None:
        return stdout, stderr
    elif stdout is not None:
        return stdout
    elif stderr is not None:
        return stderr
    else:
        return None


def run_command_or_die(command, env=None):
    """Runs the given command and dies on error.

    Command's output is trapped. If it exits with a non-zero status,
    its stderr is written to the stderr of the calling process and
    then the calling process exits with the same status.

    Args:
        command: A string representing the command to run.
        env: A dictionary representing command's environment. Note
            that these are added to the parent process's environment.

    Returns:
        A tuple of strings representing the command's stdout and
        stderr.
    """
    try:
        return run_command(command, env=env, trap_stdout=True, trap_stderr=True,
                           output_on_error=False)
    except CalledProcessError, e:
        sys.stderr.write(e.stderr)
        sys.exit(e.returncode)


def run_command_shell(command, env=None):
    """Runs the given command in a shell.

    Normally, run_command should be used. Use run_command_shell if
    command needs to interact with the user, like with 'git commit'
    which invokes an editor for making changes to the commit mesage.

    The command's stdout and stderr use the corresponding file handles
    of the calling process.

    Args:
        command: A string representing the command to run.
        env: A dictionary representing command's environment. Note
            that these are applied to the parent process's environment.

    Raises:
        CalledProcessError: The command exited with a non-zero status.
    """
    if FLAGS['dry-run'].value:
        print 'run_command_shell >>> %s' % command
        return

    new_env = os.environ.copy()
    if env is not None:
        new_env.update(env)

    process = subprocess.Popen(command, shell=True, env=new_env)
    process.communicate()  # wait for process to terminate
    status = process.poll()
    if status:
        raise CalledProcessError(status, command)


def get_config_option(name):
    """Returns the config value identified by name.

    Args:
        name: A string representing the desired config option.

    Returns:
        A string representing the value of the desired config option
        or None if the option was not found.
    """
    try:
        return run_command('git config --get %s' % name,
                           trap_stdout=True, output_on_error=False).strip()
    except CalledProcessError:
        return None


def get_branch():
    """Returns the current git branch name.

    Returns:
        The name of the current branch as a string.

    Raises:
        GitError: A valid branch name could not be read.
    """
    if FLAGS['dry-run'].value:
        return 'fake-branch'
    output = run_command('git symbolic-ref HEAD', trap_stdout=True)
    parts = output.split('/')
    if len(parts) == 3:
        return parts[2].strip()
    else:
        raise GitError('Could not get a branch name from "%s"' % output)


def search_gerrit(query):
    """Searches Gerrit with the given query.

    Runs the search and parses the JSON response into python
    objects.

    See http://goo.gl/oC6mW for search operators and
    http://goo.gl/VMJih for data formats.

    Args:
        query: A string representing the Gerrit search query.

    Returns:
        A tuple (results, stats) where results is a sequence of
        dictionaries each representing a query result, and stats is a
        dictionary describing the results. Here is an example for the
        query [change:I661e6]:

        ([{'branch': 'master',
           'createdOn': 1330051281,
           'id': 'I661e66ee89a862de1f0c03c097b8d57302cade03',
           'lastUpdated': 1330051281,
           'number': '45',
           'open': True,
           'owner': {'email': 'ace@example.com', 'name': 'Ace Hacker'},
           'project': 'fooproj',
           'sortKey': '001b45410000002d',
           'status': 'NEW',
           'subject': 'Log interesting events',
           'trackingIds': [{'id': '442', 'system': 'Bugzilla'}],
           'url': 'http://review.example.com/45'}],
         {'rowCount': 1, 'runTimeMilliseconds': 10, 'type': 'stats'})
    """
    results = []
    stats = None
    response = run_command('ssh %s gerrit query --format=JSON %s' %
                           (FLAGS['gerrit-ssh-host'].value, query), trap_stdout=True)
    for line in response.split('\n'):
        if not line:
            continue
        result = simplejson.loads(line)
        if 'type' in result and result['type'] == 'stats':
            stats = result
        else:
            results.append(result)
    return results, stats
