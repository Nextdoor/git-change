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

"""Git command to create and manage Gerrit changes.

Use git-change to create and manage changes for the Gerrit code review
tool. The default behavior is to create a new change. There are
subcommands to manage the change at later stages, including uploading
a new patch set, rebasing, and garbage-collecting the temporary change
branches this command creates.

See git-change(1) for full documentation.
"""

__author__ = 'jacob@nextdoor.com (Jacob Hesch)'
__version__ = '0.1.0'  # http://semver.org/

import sys
import time

import gflags

import git

# Used mainly to provide a usage summary with -h, consistent with
# other git commands.
gflags.DEFINE_bool('help-summary', False, 'Show a short usage message and exit.', short_name='h')

gflags.DEFINE_list('reviewers', list(), 'Comma-separated list of reviewers.', short_name='r')
gflags.DEFINE_list('cc', list(),
                   'Comma-separated list of addresses to copy on change notification mails.')
gflags.DEFINE_string('bug', None, 'Bug ID to include in the commit message header', short_name='b')
gflags.DEFINE_string('message', None, 'Use the given message as the commit message.',
                     short_name='m')
gflags.DEFINE_string('topic', None, 'Tag the change with the given topic name.')
gflags.DEFINE_string('skip', None, 'Comma-separated list of pre-commit checks to skip. '
                     'Options: tests, whitespace, linelength, pep8, pyflakes, jslint or all.')
gflags.DEFINE_bool('fetch', False,
                   'Run git-fetch so that remote branch is in sync with the central repository.')
gflags.DEFINE_bool('switch', False, 'Switch to the temporary change branch after creating it.')
gflags.DEFINE_bool('chain', False,
                   'Chain with the previous Gerrit change. Use when this change depends on '
                   'the previous one. Current branch must be a temporary change branch. '
                   'Implies --switch.')
gflags.DEFINE_bool('use-head-commit', False,
                   'Use the HEAD commit as the change to push rather than committing '
                   'staged changes.')
gflags.DEFINE_bool('merge-commit', False,
                   'Create a change for a merge commit. Implies --use-head-commit. '
                   'This flag assumes the current branch is a tracking branch and '
                   'that the HEAD commit is an unreviewed merge commit for which a '
                   'review is being created. A change branch will be created and '
                   'git-commit --amend invoked in order to have the commit-msg hook '
                   'add a change ID header. The usual check for unmerged commits is '
                   'skipped, so be sure all of the commits being merged have change '
                   'ID headers to avoid having Gerrit create a review for each one. '
                   'Finally, note that the HEAD (merge) commit in the original '
                   'tracking branch is removed after the change branch is created.')
gflags.DEFINE_bool('fake-push', False,
                   'Do everything except for actually pushing the change to Gerrit.')

FLAGS = gflags.FLAGS


def usage(include_flags=True):
    """Prints a usage message.

    Args:
        include_flags: Include flag descriptions in the message.
    """
    message = ('Usage: git change [create] [<create-options>]\n'
               '   or: git change update [<update-options>]\n'
               '   or: git change rebase\n'
               '   or: git change list\n'
               '   or: git change submit\n'
               '   or: git change gc\n'
               '\n'
               '<create-options>: [-r|--reviewers=] [--cc=] [-b|--bug=] [-m|--message=] '
               '[--topic=] [--fetch] [--switch] [--chain] '
               '[--use-head-commit] [--merge-commit] [--skip=]\n'
               '\n'
               '<update-options>[-r|--reviewers=] [--cc=] [-b|--bug=] [--skip=]\n'
               '\n'
               'See git-change(1) for full documentation.')
    print message
    if include_flags:
        print FLAGS


def exit_error(message, prefix='Error: ', status=1):
    """Prints the given message and exits the process.

    Args:
        message: A string representing the error message to
            print. 'Error: ' will be prepended to message.
        prefix: A string to prepend to message
        stautus: An integer representing the exit status code.
    """
    sys.stderr.write('%s%s\n' % (prefix, message))
    sys.exit(status)


def get_change_id_from_branch():
    """Returns the change ID embedded in the current branch name.

    Assumes the current branch is a temporary change branch created by
    a previous run of git-change. Example branch name:
    'change-Id06774ede265426f85d36cca50bba69d8aa54ed8'.

    Returns:
        A string representing the change ID embedded in the current
        branch name, or None if the current branch is not a temporary
        change branch.
    """
    branch = git.get_branch()
    if branch.startswith('change-I'):
        _, change_id = branch.split('-')
        return change_id
    return None


def get_change_id_from_head():
    """Returns the change ID of the last commit.

    If the change ID is available as the value of the Change-Id
    attribute in the HEAD commit message, that value is returned. If
    there is no Change-Id attribute, returns None.

    Returns:
        A string representing the HEAD commit's change ID if it is
        available, or None if not.
    """
    output = git.run_command('git cat-file -p HEAD', trap_stdout=True)
    lines = output.split('\n')
    for line in lines:
        if line.startswith('Change-Id:'):
            _, change_id = line.split(':')
            return change_id.strip()
    return None


def build_push_command(branch):
    """Builds a git push command string for pushing a Gerrit change.

    The command is built using the given branch and flag values to
    populate remote repository, reviewers, users to CC, etc.

    Args:
        branch: A string representing the branch to which to push.

    Returns:
        The git push command as a string.
    """
    command = 'git push %s' % FLAGS.remote
    receive_pack_args = []
    for reviewer in FLAGS.reviewers:
        if reviewer:  # trailing commas in flag value generate blank entries
            receive_pack_args.append('--reviewer=%s' % reviewer)
    for cc in FLAGS.cc:
        if cc:  # trailing commas in flag value generate blank entries
            receive_pack_args.append('--cc=%s' % cc)
    if receive_pack_args:
        command = '%s --receive-pack="git receive-pack %s"' % (
            command, ' '.join(receive_pack_args))
    command = '%s HEAD:refs/for/%s' % (command, branch)
    if FLAGS.topic:
        command = '%s/%s' % (command, FLAGS.topic)
    if FLAGS['fake-push'].value:
        print 'Fake pushing'
        command = 'echo %s' % command
    return command


def check_unmerged_commits(branch):
    """Checks whether the given branch has unmerged commits.

    Specifically, checks whether the given branch has unmerged commits
    relative to its remote branch. For example, assuming the branch is
    'master' and the remote is 'origin', checks whether 'master' has
    commits that have not been merged into 'origin/master'.

    Args:
        branch: A string representing the branch to check.

    Returns:
        True if the given branch has commits not yet merged in its
        remote branch. False if not, or if the user elected to proceed
        anyway.
    """
    output = git.run_command('git log --oneline %s ^%s/%s --' % (branch, FLAGS.remote, branch),
                             trap_stdout=True)
    if not output or FLAGS['dry-run'].value:
        return False

    print 'Your branch %s is ahead of its remote by the following %s commit(s):\n' % (
        branch, len(output.split('\n')))
    sys.stdout.write(output)
    user_input = raw_input(
        '\nIf we continue, each of the commits above may result in a new code\n'
        'review and a submit dependency in Gerrit. You might try syncing the\n'
        'remote branch by passing the --fetch flag.\n'
        'Continue? ')
    if user_input.lower().startswith('y'):
        return False

    print '\nAborted'
    return True


def get_change(change_id):
    """Returns the Gerrit change object for the given change ID.

    Queries Gerrit for the change_id and returns a Python object
    created from the JSON search result.

    This function exits with a non-zero status if the Gerrit search
    returns multiple results for change_id.

    Args:
        change_id: A string representing the ID of the desired change.

    Returns:
        A Python object representation of the Gerrit query JSON
        response. See git.search_gerrit and http://goo.gl/VMJih for
        the JSON data format.
    """
    results, _ = git.search_gerrit('change:%s' % change_id)
    if len(results) < 1:
        exit_error('Unable to find Gerrit change for ID %s.' % change_id)
    elif len(results) > 1:
        exit_error('Got multiple results searching Gerrit for %s.' % change_id)
    return results[0]


def check_for_change_branch():
    """Ensures that the current branch is a valid temporary change branch.

    If the current branch name does not begin with 'change-I', or if
    the HEAD commit message does not contain a matching change ID
    header, exits with a non-zero status.

    Returns:
        A string representing the change ID embedded in the current
        temporary change branch name.
    """
    change_id = get_change_id_from_branch()
    if change_id is None:
        exit_error('The current branch must be a change branch '
                   'previously created by git-change.')
    head_change_id = get_change_id_from_head()
    if head_change_id is None:
        exit_error('The commit message at HEAD does not contain a valid change ID header.')
    elif head_change_id != change_id:
        exit_error('The change ID in the commit message at HEAD (%s)\n'
                   'does not match the change ID embedded in the branch name (%s).' %
                   (head_change_id, change_id))
    return change_id


def update_change():
    """Updates an existing change with Gerrit.

    Runs a git push command to update an existing change. The change
    ID is taken from the current branch, which should be a temporary
    change branch created by a previous run of git-change.
    """
    change_id = check_for_change_branch()
    change = get_change(change_id)
    if not change['open']:
        exit_error('Change %s is no longer open.' % change_id)

    # Amend the HEAD commit if there are staged changes or if at least
    # one of the --reviewers, --cc or --bug flags was passed. Amending
    # the HEAD commit changes its SHA1 hash, signaling to Gerrit that
    # we have a new patch set.
    if (FLAGS.reviewers or FLAGS.cc or FLAGS.bug is not None or
        git.run_command('git diff --cached --name-status', trap_stdout=True)):

        commit_change(['--amend'])

    command = build_push_command(change['branch'])
    try:
        git.run_command(command)
    except git.CalledProcessError, e:
        # Run command prints an error message prior to raising.
        sys.exit(e.returncode)


def commit_change(args=None):
    """Commits the staged change.

    Runs 'git commit' to commit the staged change. If a bug number was
    specified in a flag, sets the BUG_ID environment variable so
    the prepare-commit-msg hook can inject the bug ID into the commit
    message.

    Args:
        args: A sequence of strings containing flags to pass to
            git-commit.

    Raises:
        git.CalledProcessError: 'git commit' exited with a non-zero
            status.
    """
    env = {}
    if FLAGS.bug is not None:
        env.update({'BUG_ID': FLAGS.bug})
    if FLAGS.skip is not None:
        env.update({'SKIP': FLAGS.skip})
    command = 'git commit'
    if args is not None:
        command = '%s %s' % (command, ' '.join(args))
    if FLAGS.message is not None:
        command = '%s -m "%s"' % (command, FLAGS.message)
    git.run_command_shell(command, env=env)


def check_for_pending_changes():
    """Checks the working tree and index for changed files.

    If there are any uncommitted changes, exits with an
    error. Untracked files are okay.
    """
    output = git.run_command('git status --porcelain --untracked-files=no', trap_stdout=True)
    if output:
        git.run_command('git status')
        exit_error('You have uncommitted changes in your working tree/index. '
                   'Please stash them and try again.')


def sanity_check_merge_commit():
    """Checks whether the HEAD commit looks like a merge.

    If the HEAD commit does not look like a merge, prompts the user to
    see if we should continue, and exits if not.
    """
    num_parents = 0
    merge_message_seen = False
    output = git.run_command('git cat-file -p HEAD', trap_stdout=True)
    lines = output.split('\n')
    for line in lines:
        if line.startswith('parent '):
            num_parents += 1
        elif line.startswith('Merge branch '):
            merge_message_seen = True
    if num_parents < 2 or not merge_message_seen:
        user_input = raw_input('The HEAD commit does not look like a merge. Continue? ')
        if user_input.lower().startswith('y'):
            return
        else:
            print 'Aborted'
            sys.exit(1)


def determine_branches():
    """Determines the current and target branches.

    The current branch is the current HEAD, and the target branch is
    the branch to which this change is to be merged. The current
    branch may or may not be a temporary change branch but the target
    branch is always a tracking branch.

    Exits with a non-zero status if --chain is true and the current
    branch is *not* a change branch, or if --chain is false and the
    current branch *is* a change branch.

    Returns:
        A tuple of two strings: the name of the current branch and
        that of the target branch.
    """
    original_branch = git.get_branch()
    if FLAGS.chain:
        # Extract the target branch from the previous change with
        # which we're chaining.
        previous_change_id = get_change_id_from_branch()
        if previous_change_id is None:
            exit_error('The current branch must be a change branch when you specify --chain.')
        previous_change = get_change(previous_change_id)
        target_branch = previous_change['branch']
    else:
        if original_branch.startswith('change-I'):
            exit_error('You are in a temporary change branch. '
                       'If you wish to chain commits, pass --chain.')
        target_branch = original_branch

    return original_branch, target_branch


def commit_staged_changes(original_branch, tmp_branch):
    """Commits staged changes.

    A change ID will be generated by the commit-msg hook as a
    side-effect. This function exits the process on errors.

    Args:
        original_branch: A string representing the name of the branch
            the user started with. Used for rolling back on error.
        tmp_branch: A string representing the name of the temporary
            change branch. Used for rolling back on error.
    """
    try:
        commit_change()
    except KeyboardInterrupt:
        # The user bailed with Control-C.
        git.run_command('git checkout %s' % original_branch)
        git.run_command('git branch -d %s' % tmp_branch)
        sys.exit(1)
    except git.CalledProcessError, e:
        # git-commit returned non-zero status. Maybe the user provided
        # an empty commit message.
        git.run_command('git checkout %s' % original_branch)
        git.run_command('git branch -d %s' % tmp_branch)
        sys.exit(e.returncode)


def create_change():
    """Creates a Gerrit code review change."""
    if not FLAGS['use-head-commit'].value:
        if not git.run_command('git diff --cached --name-status', trap_stdout=True):
            exit_error('You have no staged changes; exiting.\n'
                       '(You may want to specify --use-head-commit.)', prefix='')

    if FLAGS['merge-commit'].value:
        check_for_pending_changes()
        sanity_check_merge_commit()

    original_branch, target_branch = determine_branches()

    # Fetch from origin so that we can see how many commits ahead our
    # local branch is.
    if FLAGS.fetch:
        git.run_command('git fetch %s' % FLAGS.remote)

    # Make sure the original branch does not have any unmerged
    # commits relative to its remote. This check only makes sense if
    # original_branch is a tracking branch (i.e. if --chain is false).
    # The check is skipped in the case of a merge commit change, which
    # will likely have many (expected) unmerged commits.
    if not FLAGS.chain and not FLAGS['merge-commit'].value:
        if check_unmerged_commits(original_branch):
            sys.exit(1)

    # Create and switch to a temporary branch. Once we have a change
    # ID, it will be renamed to include the ID.
    tmp_branch = 'tmp-change-%s' % time.time()
    git.run_command('git checkout -b %s' % tmp_branch, trap_stdout=True)

    if not FLAGS['use-head-commit'].value:
        commit_staged_changes(original_branch, tmp_branch)

    # Now rename the branch according to the change ID.
    change_id = get_change_id_from_head()
    if FLAGS['use-head-commit'].value and change_id is None:
        # Amend the HEAD commit in order to force running the
        # commit-msg hook, which should insert a Change-Id header.
        commit_change(['--amend'])
        change_id = get_change_id_from_head()
    if change_id is None:
        print ('\nWARNING: Reading change ID from the HEAD commit failed. (You may need to\n'
               'install the Gerrit commit-msg hook.) Before continuing, you need to add\n'
               'the change ID header to the HEAD commit message (git commit --amend) and\n'
               'rename the branch %s to change-<change-ID> manaully.' % tmp_branch)
        new_branch = tmp_branch
    else:
        new_branch = 'change-%s' % change_id
        git.run_command('git branch -m %s %s' % (tmp_branch, new_branch))
    print '\nCreated branch: %s\n' % new_branch

    command = build_push_command(target_branch)
    try:
        git.run_command(command)
    except git.CalledProcessError, e:
        # Roll back the commit and remove the change branch.
        git.run_command('git reset --soft HEAD^')
        git.run_command('git checkout %s' % original_branch)
        git.run_command('git branch -d %s' % new_branch)
        sys.exit(e.returncode)

    if FLAGS['merge-commit'].value:
        # Remove the merge commit from the original branch to avoid
        # duplicating the commit in case the version of that commit in
        # the change branch is amended (i.e., its SHA1 hash changed).
        # The call to check_for_pending_changes above ensures that the
        # working tree and index are clean and thus 'git reset --hard'
        # is safe to run.
        git.run_command('git checkout %s' % original_branch)
        git.run_command('git reset --hard HEAD^')
        print 'Removed HEAD commit from branch %s' % original_branch
        if FLAGS.switch or FLAGS.chain:
            git.run_command('git checkout %s' % new_branch)
        return

    # Switch back to the original branch, but not if --chain is true
    # as the user may be want to make multiple commits in the
    # temporary change branch.
    if FLAGS.switch or FLAGS.chain:
        pass  # switch to (stay on) temporary change branch
    else:
        git.run_command_or_die('git checkout %s' % original_branch)


def rebase():
    """Rebases the target and temporary change branches.

    Rebases the target branch (the branch from which the temporary
    change branch was created) and then rebases the temporary change
    branch. This can be used to pull upstream changes down to both
    branches to resolve a failed Gerrit submission due to a path
    conflict.

    If there are conflicts with either rebase operation, the process
    terminates and it is up to the user to resolve the conflicts.
    """
    change_id = check_for_change_branch()
    change = get_change(change_id)
    target_branch = change['branch']
    change_branch = git.get_branch()

    git.run_command_or_die('git checkout %s' % target_branch)
    try:
        git.run_command('git pull --rebase', output_on_error=False)
    except git.CalledProcessError, e:
        print ('Rebase failed for branch %s. After resolving merge failure(s),\n'
               'check out the change branch (%s) and run "git change rebase" again.\n'
               'See "git help rebase" for help on resolving merge conflicts.' %
               (target_branch, change_branch))
        sys.exit(e.returncode)

    git.run_command_or_die('git checkout %s' % change_branch)
    try:
        git.run_command('git rebase %s' % target_branch)
    except git.CalledProcessError, e:
        print ('Rebase failed for branch %s. After resolving merge failure(s),\n'
               'run "git change rebase" again. See "git help rebase" for help\n'
               'on resolving merge conflicts.' % change_branch)
        sys.exit(e.returncode)


def get_change_branches():
    """Returns temporary change branches.

    Temporary change branch names match the pattern 'change-*'.

    Returns:
        A sequence of strings each representing a branch names, sorted
        in chronological order based on the author date of each
        branch's HEAD commit.
    """
    output = git.run_command(
        'git for-each-ref --format="%(refname:short)" --sort=authordate refs/heads/change-*',
        trap_stdout=True)
    if output:
        return output.strip().split('\n')
    else:
        return []


def list_change_branches():
    """Lists all temporary change branches.

    Lists the branches and prompts user with a menu to check one of
    them out.
    """
    branches = get_change_branches()
    if not branches:
        print 'You have no change branches to list'
        return
    print 'Change branches:\n'
    i = 0
    for branch in branches:
        i += 1
        output = git.run_command('git log --oneline -1 %s --' % branch, trap_stdout=True)
        sys.stdout.write('{0:>2}. {1} {2}'.format(i, branch, output))
    try:
        selection = raw_input('\nSelect a branch number to check out, '
                              'or hit enter to exit: ')
    except (EOFError, KeyboardInterrupt):
        # User pressed or Ctrl-D or Ctrl-C.
        return
    if selection.isdigit() and int(selection) <= len(branches):
        git.run_command_or_die('git checkout %s' % branches[int(selection) - 1])
    elif selection:
        print 'Not a valid selection'
    else:
        pass  # User hit enter; just exit.


def submit_change():
    """Submits the existing change to Gerrit."""
    change_id = check_for_change_branch()
    change = get_change(change_id)
    if not change['open']:
        exit_error('Change %s is no longer open.' % change_id)

    commit = git.run_command('git rev-parse --verify HEAD', trap_stdout=True)
    project = change['project']
    git.run_command_or_die('ssh %s gerrit review --project %s --submit %s' %
                           (FLAGS['gerrit-ssh-host'].value, project, commit))


def garbage_collect():
    """Removes temporary change branches which are fully merged."""
    unmerged_branches = []
    deleted = False
    for branch in get_change_branches():
        try:
            # Note: git branch -d prints 'Deleted branch ...' to stdout.
            git.run_command('git branch -d %s' % branch, trap_stderr=True, output_on_error=False)
        except git.CalledProcessError:
            unmerged_branches.append(branch)
        else:
            deleted = True

    if unmerged_branches:
        if deleted:
            print  # Blank line between deleted branches and the message below.
        print ('The following change branches could not be deleted, probably because they\n'
               'are not fully merged into the current branch. You might try first running\n'
               'git-pull or git-change rebase in order to sync with remote.\n')
        for branch in unmerged_branches:
            print branch


def print_push_command():
    """Prints the command to push a change to Gerrit."""
    change_id = get_change_id_from_branch()
    if change_id is not None:
        change = get_change(change_id)
        target_branch = change['branch']
    else:
        target_branch = git.get_branch()
    print build_push_command(target_branch)


def main(argv):
    if FLAGS['help-summary'].value:
        usage(include_flags=False)
        sys.exit()

    # Get remote from command-line flag or config option, otherwise
    # fall back to flag default.
    if not FLAGS['remote'].present:
        remote = git.get_config_option('git-change.remote')
        if remote is not None:
            FLAGS.remote = remote

    # Get Gerrit ssh host from command-line flag or config option,
    # otherwise exit with an error.
    gerrit_ssh_host = FLAGS['gerrit-ssh-host']
    if not gerrit_ssh_host.present:
        gerrit_ssh_host.value = git.get_config_option('git-change.gerrit-ssh-host')
    if gerrit_ssh_host.value is None:
        exit_error('Please define git config option "git-change.gerrit-ssh-host" '
                   'or pass --gerrit-ssh-host.')

    # --merge-commit implies --use-head-commit.
    if FLAGS['merge-commit'].value:
        FLAGS['use-head-commit'].value = True

    # Fail gracefully if run outside a git repository.
    git.run_command_or_die('git status')

    argc = len(argv)
    if argc > 2:
        usage(include_flags=False)
        sys.exit(1)
    elif argc == 2:
        subcommand = argv[1]
    else:
        subcommand = 'create'  # default subcommand

    if subcommand == 'create':
        create_change()
    elif subcommand == 'update':
        update_change()
    elif subcommand == 'rebase':
        rebase()
    elif subcommand == 'list':
        list_change_branches()
    elif subcommand == 'submit':
        submit_change()
    elif subcommand == 'gc':
        garbage_collect()
    elif subcommand == 'print':
        print_push_command()
    else:
        exit_error('Unknown subcommand: %s.' % subcommand)


def app():
    """Parses flags and starts the application."""
    FLAGS.UseGnuGetOpt(True)
    try:
        argv = FLAGS(sys.argv)
    except gflags.FlagsError, e:
        print e
        usage()
        sys.exit(1)

    main(argv)
