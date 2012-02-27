"""Utilities to support git subcommands."""

import os
import shlex
import subprocess
import sys

import gflags

gflags.DEFINE_bool('dry_run', False, 'echo commands but do not execute them', short_name='n')

FLAGS = gflags.FLAGS


def run_command(command, env=None, shell=False, want_status=False):
    """Runs the given command.

    Args:
        command: A string representing the command to run.
        env: A dictionary representing command's environment. Note
            that these are applied to the parent process's environment.
        shell: If True, command is run in a subshell. If False
            (default) command is run using os.execvp().

    Returns:
        A tuple consisting of the return code and command's
        stdout. Note that with shell=True, stdout is None.
    """
    if FLAGS.dry_run:
        print 'dry_run>>> %s' % command
        return None
    if env is None:
        env = {}
    new_env = os.environ.copy()
    new_env.update(env)
    if shell:
        process = subprocess.Popen(command, shell=True, env=new_env)
        stdout, stderr = process.communicate()
    else:
        process = subprocess.Popen(command_list, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=new_env)
        stdout, stderr = process.communicate()
        stdout = stdout.strip()
    if want_status:
        return process.returncode, stdout
    else:
        return stdout


def get_branch():
    """Returns the current git branch.

    Returns:
        The name of the current branch as a string.
    """
    output = run_command('git symbolic-ref HEAD')
    if output is None:
        return None
    else:
        return output.split('/')[2]


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
    try:
        argv = FLAGS(argv)  # parse flags
    except gflags.FlagsError, e:
        print '%s\\nUsage: %s ARGS\\n%s' % (e, sys.argv[0], FLAGS)
        sys.exit(1)
    sys.modules['__main__'].main(argv)
