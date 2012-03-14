#!/usr/bin/env python

"""Git command which creates and manages a Gerrit change.

Use git-change for creating and managing a change for the Gerrit code
review tool. The default behavior is to create a new change. There are
subcommands to manage the change at later staging, including uploading
a new patch set, rebasing, and garbage-collecting the temporary change
branches this command creates.

The files that make up the change must be staged for commit, and are
committed in a new branch meant to exist exclusively for this change.

Performs the following operations:
  1. Notes the current tracking branch
  2. Creates a temporary, local change branch
  3. Commits staged changes
  4. Pushes to the previously current branch
  5. Renames the branch to reflect the Gerrit Change-Id

If there are commits in the tracking branch not yet merged in the
remote branch prior to step 3 above, a warning is issued to explain
that continuing would result in multiple changes being added to the
temporary branch and pushed to Gerrit.
"""

__author__ = 'jacob@nextdoor.com (Jacob Hesch)'

import sys
import time

import gflags

import git

gflags.DEFINE_bool('help', False, 'Show a usage and exit.', short_name='h')

gflags.DEFINE_list('reviewers', list(), 'Comma separated list of reviewers.', short_name='r')
gflags.DEFINE_list('cc', list(),
                   'Comma separated list of addresses to copy on change notification mails.')
gflags.DEFINE_string('bug', None, 'Bug ID to include in the commit message header', short_name='b')
gflags.DEFINE_string('message', None, 'Use the given message as the commit message.',
                     short_name='m')
gflags.DEFINE_string('topic', None, 'Tag the change with the given topic name.')
gflags.DEFINE_bool('fetch', False,
                   'Run git-fetch so that remote branch is in sync with the central repository.')
gflags.DEFINE_bool('switch', False, 'Switch to the temporary change branch after creating it.')
gflags.DEFINE_bool('chain', False,
                   'Chain with the previous Gerrit change. Use when this change depends on '
                   'the previous one. Current branch must be a temporary change branch. '
                   'Implies --switch.')
gflags.DEFINE_bool('fake_push', False,
                   'Do everything except for actually pushing the change to Gerrit.')

FLAGS = gflags.FLAGS


def usage(include_flags=True):
    """Prints a usage message.

    Args:
        include_flags: Include flag descriptions in the message.
    """
    message = ('Usage: git change [create] [<create-options>]\n'
               '   or: git change update\n'
               '   or: git change gc\n'
               '\n'
               '<create-options>: [-r|--reviewers=] [--cc=] [-b|--bug=] [-m|--message=] [--topic=] '
               '[--[no]fetch] [--[no]switch] [--[no]chain]\n'
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
    print '%s%s' % (prefix, message)
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
    output = git.run_command('git cat-file -p HEAD')
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
        receive_pack_args.append('--reviewer=%s' % reviewer)
    for cc in FLAGS.cc:
        receive_pack_args.append('--cc=%s' % cc)
    if receive_pack_args:
        command = '%s --receive-pack="git receive-pack %s"' % (
            command, ' '.join(receive_pack_args))
    command = '%s HEAD:refs/for/%s' % (command, branch)
    if FLAGS.topic:
        command = '%s/%s' % (command, FLAGS.topic)
    if FLAGS.fake_push:
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
    output = git.run_command('git log --oneline %s ^%s/%s' % (branch, FLAGS.remote, branch))
    if not output or FLAGS.dry_run:
        return False

    print 'Your branch %s is ahead of its remote by the following %s commit(s):\n' % (
        branch, len(output.split('\n')))
    print output
    user_input = raw_input(
        '\nIf we continue, multiple commits will be added to the new branch and\n'
        'pushed for review. Those commits will have submit dependencies in Gerrit.\n'
        'You might try syncing the remote branch by passing the --fetch flag.\n'
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
        exit_error('The current branch must be a change branch, '
                   'usually previously created by git-change.')
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
        exit_error('Change %s is no longer open.')

    # If there are staged changes commit them, amending the HEAD
    # commit.
    if git.run_command('git diff --cached --name-status'):
        git.run_command_shell('git commit --amend')

    command = build_push_command(change['branch'])
    print git.run_command(command)


def commit_change():
    """Commits the staged change.

    Runs 'git commit' to commit the staged change. If a bug number was
    specified in a flag, sets the ND_BUG_ID environment variable so
    the prepare-commit-msg hook can inject the bug ID into the commit
    message.

    Raises:
        git.CalledProcessError: 'git commit' exited with a non-zero
            status.
    """
    if FLAGS.bug is None:
        env = None
    else:
        env = {'ND_BUG_ID': FLAGS.bug}
    command = 'git commit'
    if FLAGS.message is not None:
        command = '%s -m "%s"' % (command, FLAGS.message)
    git.run_command_shell(command, env=env)


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


def create_change():
    if not git.run_command('git diff --cached --name-status'):
        exit_error('You have no staged changes; exiting', prefix='')

    original_branch, target_branch = determine_branches()

    # Fetch from origin so that we can see how many commits ahead our
    # local branch is.
    if FLAGS.fetch:
        output = git.run_command('git fetch %s' % FLAGS.remote)
        if output:
            print output

    # Make sure the original branch does not have any unmerged commits
    # relative to its remote. This check only makes sense if
    # original_branch is a tracking branch (i.e. if --chain is false).
    if not FLAGS.chain:
        if check_unmerged_commits(original_branch):
            sys.exit(1)

    # Create and switch to a temporary branch. Once we have a change
    # ID, it will be renamed to include the ID.
    tmp_branch = 'tmp-change-%s' % time.time()
    git.run_command('git checkout -b %s' % tmp_branch)

    # Commit the change. A change ID will be generated by the
    # commit-msg hook as a side-effect.
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

    # Now rename the branch according to the change ID.
    change_id = get_change_id_from_head()
    if change_id is None:
        # We couldn't read a change ID for some reason so just keep
        # the temp name.
        new_branch = tmp_branch
    else:
        new_branch = 'change-%s' % change_id
        git.run_command('git branch -m %s %s' % (tmp_branch, new_branch))
    print '\nCreated branch: %s\n' % new_branch

    command = build_push_command(target_branch)
    print git.run_command(command)

    # Switch back to the original branch, but not if --chain is true
    # as the user may be want to make multiple commits in the
    # temporary change branch.
    if FLAGS.switch or FLAGS.chain:
        pass  # switch to (stay on) temporary change branch
    else:
        git.run_command('git checkout %s' % original_branch)


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
    original_branch = git.get_branch()
    git.run_command('git checkout %s' % target_branch)
    git.run_command('git pull --rebase')
    git.run_command('git checkout %s' % original_branch)
    git.run_command('git rebase %s' % target_branch)


def get_temp_branches():
    """Returns temporary change branches.

    Temporary change branch names match the pattern 'change-*'.

    Returns:
        A sequence of strings each representing a branch names.
    """
    output = git.run_command(
        'git for-each-ref --format="%(refname:short)" refs/heads/change-*')
    if output:
        return output.split('\n')
    else:
        return []


def garbage_collect():
    """Removes temporary change branches which are fully merged."""
    unmerged_branches = []
    for branch in get_temp_branches():
        try:
            git.run_command('git branch -d %s' % branch, output_on_error=False)
        except git.CalledProcessError, e:
            unmerged_branches.append(branch)
        else:
            print '\nDeleted branch %s\n' % branch

    if unmerged_branches:
        print ('The following change branches could not be deleted, probably because they\n'
               'are not fully merged into the current branch. You might try first running\n'
               'git-change rebase in order to sync with remote.\n')
        for branch in unmerged_branches:
            print branch


def main(argv):
    if FLAGS.help:
        usage(include_flags=False)
        sys.exit()

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
    elif subcommand == 'gc':
        garbage_collect()
    else:
        exit_error('Unknown subcommand: %s.' % subcommand)


if __name__ == '__main__':
    git.app(sys.argv)
