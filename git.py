"""Utilities to support git subcommands."""

__author__ = 'jacob@nextdoor.com (Jacob Hesch)'

import inspect
import os
import shlex
import simplejson
import subprocess
import sys

import gflags

gflags.DEFINE_string('remote', 'origin',
                     'Name of the remote repository to fetch from and push to.')

gflags.DEFINE_bool('dry_run', False, 'Echo commands but do not execute them.', short_name='n')

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
    'output' attribute is kept for compatibility.

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


# Copied from subprocess.py of Python 2.7.
def check_output(*popenargs, **kwargs):
    r"""Run command with arguments and return its output as a byte string.

    If the exit code was non-zero it raises a CalledProcessError.  The
    CalledProcessError object will have the return code in the returncode
    attribute and output in the output attribute.

    The arguments are the same as for the Popen constructor.  Example:

    >>> check_output(['ls', '-l', '/dev/null'])
    'crw-rw-rw- 1 root root 1, 3 Oct 18  2007 /dev/null\n'

    The stdout argument is not allowed as it is used internally.
    To capture standard error in the result, use stderr=STDOUT.

    >>> check_output(['/bin/sh', '-c',
    ...               'ls -l non_existent_file ; exit 0'],
    ...              stderr=STDOUT)
    'ls: non_existent_file: No such file or directory\n'
    """
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    stdout, stderr = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get('args')
        if cmd is None:
            cmd = popenargs[0]
        raise CalledProcessError(retcode, cmd, output=stdout, stdout=stdout, stderr=stderr)
    return stdout


def check_output_separate(*popenargs, **kwargs):
    """Runs command with arguments and returns its stdout output.

    Like subprocess.check_output, but separates stdout and stderr.
    Note: check_output was added to subprocess as of Python 2.7.

    Returns stdout, unless the command exits with a non-zero
    status. If command exits with a non-zero status, a
    CalledProcessError exception is raised with command's stderr set
    in its 'output' property.

    Args:
        Same as subprocess.Popen, except stdout and stderr are not
        allowed as they are used internally.

    Returns:
        A string representing the command's stdout.

    Raises:
        CalledProcessError: The command exited with a non-zero
            status. Its stderr output is attached to the exception
            object's 'output' property.
    """
    if 'stdout' in kwargs or 'stderr' in kwargs:
        raise ValueError('stdout and stderr not allowed; they will be overridden.')
    process = subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.PIPE, *popenargs, **kwargs)
    stdout, stderr = process.communicate()
    return_code = process.poll()
    if return_code:
        command = kwargs.get('args')
        if command is None:
            command = popenargs[0]
        raise CalledProcessError(return_code, command, output=stderr, stdout=stdout, stderr=stderr)
    return stdout


def run_command(command, env=None, output_on_error=True):
    """Runs the given command.

    Args:
        command: A string representing the command to run.
        env: A dictionary representing command's environment. Note
            that these are added to the parent process's environment.
        output_on_error: A boolean to flag whether to print output if
            an error running command occurs.

    Returns:
        A string representing command's output. Note that stdout and
        stderr are combined.

    Raises:
        CalledProcessError: The command exited with a non-zero status.
    """
    if FLAGS.dry_run:
        print 'run_command >>> %s' % command
        return 'dry-run-no-output\n'

    new_env = os.environ.copy()
    if env is not None:
        new_env.update(env)

    command_list = shlex.split(command)

    try:
        return check_output_separate(command_list, env=new_env)
    except CalledProcessError, e:
        if isinstance(e.cmd, basestring):
            command = e.cmd
        else:
            command = ' '.join(e.cmd)
        if output_on_error:
            print 'Error running "%s"' % command
            print '  return code: %s' % e.returncode
            print '  stdout: %s' % e.stdout
            print '  stderr: %s' % e.stderr
        raise


def run_command_or_die(command, env=None):
    """Runs the given command and dies on error.

    If command exits with a non-zero status, its stderr is written on
    this process's stderr and then this process exits with the same
    exit status.

    Args:
        command: A string representing the command to run.
        env: A dictionary representing command's environment. Note
            that these are added to the parent process's environment.
    """
    try:
        run_command(command, env=env, output_on_error=False)
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
    if FLAGS.dry_run:
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


def get_branch():
    """Returns the current git branch name.

    Returns:
        The name of the current branch as a string.

    Raises:
        GitError: A valid branch name could not be read.
    """
    if FLAGS.dry_run:
        return 'fake-branch'
    output = run_command('git symbolic-ref HEAD')
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
           'owner': {'email': 'jacob@nextdoor.com', 'name': 'Jacob Hesch'},
           'project': 'nextdoor.com',
           'sortKey': '001b45410000002d',
           'status': 'NEW',
           'subject': 'Okeydokey',
           'trackingIds': [{'id': '442', 'system': 'Bugzilla'}],
           'url': 'http://review.nextdoortest.com/45'}],
         {'rowCount': 1, 'runTimeMilliseconds': 10, 'type': 'stats'})
    """
    results = []
    stats = None
    response = run_command('ssh review gerrit query --format=JSON %s' % query)
    for line in response.split('\n'):
        if not line:
            continue
        result = simplejson.loads(line)
        if 'type' in result and result['type'] == 'stats':
            stats = result
        else:
            results.append(result)
    return results, stats


def app(argv):
    """Bootstraps a command line app.

    Parses command line flags and calls the main module's main
    function. Meant to be used by git subcommand modules.

    Args:
        argv: A sequence of strings representing command line
            arguments.

    Example usage from a git subcommand module:

        import git

        gflags.DEFINE_string('name', 'anonymous, 'your name')
        FLAGS = gflags.FLAGS


        def main(argv):
            print 'hello, %s' % FLAGS.name

        if __name__ == '__main__':
            git.app(sys.argv)
    """
    main_module = sys.modules['__main__']
    FLAGS.UseGnuGetOpt(True)
    try:
        argv = FLAGS(argv)  # parse flags
    except gflags.FlagsError, e:
        if 'usage' in dir(main_module) and inspect.isfunction(main_module.usage):
            print e
            main_module.usage()
        else:
            print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
        sys.exit(1)

    main_module.main(argv)
