const core = require('@actions/core');
const github = require('@actions/github');
const exec = require('@actions/exec');

// Run an external command.
// cwd: optional string
// check: whether to raise an exception if returnCode is non-zero. Defaults to true.
const run = async function (args, opts = {}) {
    var result = {};
    result.stdout = '';

    var execOpts = {};
    execOpts.listeners = {
        stdout: (data) => {
            result.stdout += data.toString();
        },
    };
    execOpts.ignoreReturnCode = opts.check == false;

    if ('cwd' in opts) {
        execOpts.cwd = opts.cwd;
    }

    result.returnCode = await exec.exec(args[0], args.slice(1), execOpts);
    return result;
}

// Returns array of submodules, where each item has properties: name, path, url
const getSubmodules = async function () {
    const gitResult = await run(['git', 'config', '--file', '.gitmodules', '--list']);
    // output looks like:
    // submodule.aws-common-runtime/aws-c-common.path=crt/aws-c-common
    // submodule.aws-common-runtime/aws-c-common.url=https://github.com/awslabs/aws-c-common.git
    // ...
    const re = /submodule\.(.+)\.(path|url)=(.+)/;

    // build map with properties of each submodule
    var map = {};

    const lines = gitResult.stdout.split('\n');
    for (var i = 0; i < lines.length; i++) {
        const match = re.exec(lines[i]);
        if (!match) {
            continue;
        }

        const submoduleId = match[1];
        const property = match[2];
        const value = match[3];

        let mapEntry = map[submoduleId] || {};
        if (property === 'path') {
            mapEntry.path = value;
            // get "name" from final directory in path
            mapEntry.name = value.split('/').pop()
        } else if (property === 'url') {
            mapEntry.url = value;
        } else {
            continue;
        }

        map[submoduleId] = mapEntry;
    }

    // return array, sorted by name
    return Object.values(map).sort((a, b) => a.name.localeCompare(b.name));
}

// Diff the submodule's current commit against a target branch
// Returns null if they're the same.
// Otherwise returns something like {sourceCommit: 'c74534c', targetCommit: 'b6656aa'}
const diffSubmodule = async function (submodule, targetBranch) {
    const gitResult = await run(['git', 'diff', `origin/${targetBranch}`, '--', submodule.path]);
    const stdout = gitResult.stdout;

    // output looks like this:
    //
    // diff --git a/crt/aws-c-auth b/crt/aws-c-auth
    // index b6656aa..c74534c 160000
    // --- a/crt/aws-c-auth
    // +++ b/crt/aws-c-auth
    // @@ -1 +1 @@
    // -Subproject commit b6656aad42edd5d11eea50936cb60359a6338e0b
    // +Subproject commit c74534c13264868bbbd14b419c291580d3dd9141
    try {
        // let's just be naive and only look at the last 2 lines
        // if this fails in any way, report no difference
        var result = {}
        result.targetCommit = stdout.match('\\-Subproject commit ([a-f0-9]{40})')[1];
        result.sourceCommit = stdout.match('\\+Subproject commit ([a-f0-9]{40})')[1];
        return result;
    } catch (error) {
        return null;
    }
}

// Returns whether one commit is an ancestor of another.
const isAncestor = async function (ancestor, descendant, cwd) {
    const gitResult = await run(['git', 'merge-base', '--is-ancestor', ancestor, descendant], { check: false, cwd: cwd });
    if (gitResult.returnCode == 0) {
        return true;
    }
    if (gitResult.returnCode == 1) {
        return false;
    }
    throw new Error(`The process 'git' failed with exit code ${gitResult.returnCode}`);
}

// Returns the release tag for a commit, or null if there is none
const getReleaseTag = async function (commit, cwd) {
    const gitResult = await run(['git', 'describe', '--tags', '--exact-match', commit], { cwd: cwd, check: false });
    if (gitResult.returnCode != 0) {
        return null;
    }

    // ensure it's a properly formatted release tag
    const match = gitResult.stdout.match(/^(v[0-9]+\.[0-9]+\.[0-9]+)$/m);
    if (!match) {
        return null;
    }

    return match[1];
}


const checkSubmodules = async function () {
    // TODO: figure out how to access target branch
    // instead of hardcoding 'main'
    const targetBranch = 'main';

    const submodules = await getSubmodules();
    for (var i = 0; i < submodules.length; i++) {
        const submodule = submodules[i];

        // diff submodule against target branch
        // if there's no difference, there's no need to analyze further
        const diff = await diffSubmodule(submodule, targetBranch);
        if (diff == null) {
            continue;
        }

        // Ensure submodule is at an acceptable commit:
        // For repos the Common Runtime team controls, it must be at a tagged release.
        // For other repos, where we can't just cut a release ourselves, it needs to at least be on the main branch.
        const sourceTag = await getReleaseTag(diff.sourceCommit, submodule.path);
        if (!sourceTag) {
            const nonCrtRepo = /^(aws-lc|s2n|s2n-tls)$/
            if (nonCrtRepo.test(submodule.name)) {
                const isOnMain = await isAncestor(diff.sourceCommit, 'origin/main', submodule.path);
                if (!isOnMain) {
                    core.setFailed(`Submodule ${submodule.name} is using a branch`);
                    return;
                }
            } else {
                core.setFailed(`Submodule ${submodule.name} is not using a tagged release`);
                return;
            }
        }

        // prefer to use tags for further operations since they're easier to grok than commit hashes
        const targetTag = await getReleaseTag(diff.targetCommit, submodule.path);
        const sourceCommit = sourceTag || diff.sourceCommit;
        const targetCommit = targetTag || diff.targetCommit;

        // freak out if our branch's submodule is older than where we're merging
        if (await isAncestor(sourceCommit, targetCommit, submodule.path)) {
            core.setFailed(`Submodule ${submodule.name} is newer on ${targetBranch}:`
                + ` ${targetCommit} vs ${sourceCommit} on this branch`);
            return;
        }

    }
}

const main = async function () {
    try {
        await checkSubmodules();
    } catch (error) {
        core.setFailed(error.message);
    }
}

main()
