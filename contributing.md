# Contributing to pylabrad

## Process

The following instructions are for pylabrad contributors.
Other users working in their own fork can will use whatever procedure they like for managing contributions.
Once those contributions are ready to be included in the main pylabrad repository, they should file a pull
request and allow the pylabrad contributors to carry out the rest of the steps.

We keep the git history of master linear by avoiding merge commits.
Details on how to do this are given below.

1. If the code changes would benefit from some initial discussion, for example because you're unsure of what code to modify or because
you're changing an important interface and want to make sure others agree with your intended change, make an issue in the pylabrad
issue tracker describing the proposed change.
This issue should explain what feature is to be added or what bug is to be fixed.
The issue is automatically assigned a unique number.
If this discussion isn't needed just move on to the next step.

  Examples of small fixes which do not need a corresponding issue are
    * Small whitespace or PEP8 fixes (that aren't related to existing feature branches).
    * Changing an error (or success) message to be more descriptive.
    * Updating docstrings.

1. Development proceeds in a branch
  * If there is no issue for the line of development, name the branch `u/your-name/description-of-changes`.
  * If there is a corresponding issue (see previous item) then name the branch `XX-description-of-issue` where `XX` is the issue number.
For example, the issue filed in which we stated the need for this contributing document was #134, so the branch was called `134-contributing`.
  * If the code change is particularly urgent (for example, a major bug was introduced in the previous commit), you can add the `hotfix` label to the pull request (or the issue, or both).
  * Reviewers are strongly urged to review `hotfix` labeled items at the earliest possible opportunity.

1. Development is done in the branch via a series of commits.
The commits do not have to be done all by the same person, but if multiple people are working on an issue in the same branch common sense says they should communicate well to ensure smooth workflow.

1. When the feature is nearly complete or the bug is fixed, a pull request is filed, usually by whoever wrote the new code.
This notifies other users that some new code is ready for review.
The user making the pull request can and should call out specific users who are qualified to review the code.
Those users review the code by reading the changes and running the new tests.
Comments on specific commits can be made via the github pull request page.
Try to focus comments on specific commits, but it's ok to put general discussion in the main pull request comment area.

1. Any user may add more commits to address outstanding issues with the code, but normally this should be done by the person who made the pull request.

1. Once you think the code is in good shape, comment "LGTM" (looks good to me) in the general comments area on the pull request.
This indicates that it is ok to merge the feature branch into master.
Writing LGTM on a pull requests indicates that you are convinced the code works as expected and that you now share responsibility with the author for any problems arising from the change.
**Only the person who filed the pull request may actually do the merge**.
For larger or more critical changes it is advised to get several LGTM's before merging.

1. Tests should be written for any new functionality. Here are a few guidelines for writing tests:
  * Tests for a package should exist in a subpackage of the package. For example, tests for modules in
    labrad.servers should go in labrad/servers/test.
  * Tests should stand alone as much as possible.
  * When in doubt, testing something is better than testing nothing.

  Finally, any changes to pylabrad should pass all existing tests. You can check this by running ```py.test``` from the command line when in the pyle directory.

1. **Rebase and squash:** Before merging we clean up the git history in two steps:
rebase the feature branch onto master so that the merge will be a fast-forward,
and squash the (potentially many) commits in the branch into fewer, more easily understood commits.
Fortunately, you can do both of these things at once from the command line:
  * `git checkout master` - switch to master branch
  * `git pull` - update master branch to remote
  * `git checkout XX-description-of-issue`
  * `git rebase -i master`. This opens up an editor with your commits listed at the top.
Changing a commit from "pick" to "squash" will cause that commit to be lumped in with the previous one.
You can re-order commits at this stage as well, which can be very useful for squasing e.g. non-consecutive whitespace commits together.
  * After this, you have the opportunity to write a new commit message for the combined commit. Use it to write a good, thorough commit message. Include the following elements
    * Description of changes
    * Reviewer(s)
    * Any issues fixed by the changes.

  For details of rebasing see the [official documentation](http://git-scm.com/docs/git-rebase).
After the rebase, check to make sure all tests still pass.

1. Merge the feature branch into master
  * `git checkout XX-description-of-issue`
  * `git push -f XX-description-of-issue` -- Force push (`-f`) rebased so GitHub automatically closes the pull request after merging to master.
  * `git checkout master`
  * `git merge --ff-only XX-description-of-issue` -- you should see "fast-forward" in the output. This will fail if a fast-forward merge is not possible, which probably indicates that something went wrong with rebasing.
  * `git push`
  * If you click the button on GitHub the master history gets your commit(s) and a merge commit.
If you do it as described here via the command line, the master history gets only your commit(s).
  * (Note: `git rebase` is a powerful command and this is only one aspect of it.
For an example of squashing, see [here](http://gitready.com/advanced/2009/02/10/squashing-commits-with-rebase.html).)


### Branch naming

* Branches dealing with a specific issue should be called `XX-description` where `XX` is the issue's number and description is a description of the issue.
Note that branches may be worked on by more than one user.

* A special case exists for branches named `u/someUserName`.
These branches are for messing around.
You are allowed to rebase and force push to branches prefixed by `u/yourName`.
Other people work on your branches at their peril.
Use of personal branches for working on issues in the issue tracker is discouraged.


### Commits

* Commits should focus on precisely one feature or bug.
* Group whitespace changes to existing code into their own commits.
* It is allowed to make whitespace commits in feature branches not focused on whitespace (making separate branches for whitespace would be really annoying).


### Commit messages

Your commit message documents your changes for all time. Take pride in it. Commits should follow this format:

```
Brief one sentence description of the change, using the active present tense.

After one blank line, a paragraph describing the change in more detail, i.e.
giving context of the changes and how they influence code use, why it was
done this way, etc. For very small changes, this may not be needed if the
brief description captures the essence of the change.

Meta data about the commit, such as who reviewed it and what issues it fixes.
```
Example:

```
Refactor quizzwopper to handle doodliwigs

Quizzwopper was assuming that all inputs were gizmos, but needed
special handling to deal with doodliwigs, which have extra fuzzbinkle
attributes internally. The quizzwopper interface is unchanged and
existing code does not need to be changed.

Reviewed-by: MisterX
Fixes #42 
```


## Coding Style

N.B. Use [Pycharm](https://www.jetbrains.com/pycharm/) and most of these will be either done for you, or underlined to let you know when it's not.

### First rule of coding style: [PEP8](https://www.python.org/dev/peps/pep-0008/)
Briefly, this means:
  * Indent with four spaces. There shall be no tabs.
  * Naming:
  * Functions, variables, and files: `lowercase_with_underscores`
  * Classes: `CamelCase`

### Second rule of coding style: [Google Python Style Guide](https://google-styleguide.googlecode.com/svn/trunk/pyguide.html)

### Additional coding style rules
  * Python version is 2.7.
  * Use "from __future__ import absolute_import" in new modules to avoid accidental relative imports
  * Use "from __future__ import division" in new modules to get floating point division.
  * Use // for floor division.  Note that // does not cast to int if the input args are floats:  5.0//3.0 == 1.0


## Dos

* **Do** Remove commented code before committing. Old code is in the version control history if you want to get it back. Until then commented out code just confuses the reader.
* **Do** use reversion commits to undo bad commits on master.
* **Do** add commits to master via merge.

## Do Nots

* **Do NOT** force push to master, ever.
* **Do not** push master until the changes are reviewed and approved.
