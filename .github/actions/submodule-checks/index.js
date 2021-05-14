const core = require('@actions/core');
const github = require('@actions/github');
const exec = require('@actions/exec');

// Run an external command.
// cwd: optional string
// check: whether to raise an exception if returnCode is non-zero. Defaults to true.
const run = async function (args, opts = {}) {
    let result = {};
    result.stdout = '';

    const execOpts = {};
    execOpts.listeners = {
        stdout: (data) => {
            result.stdout += data.toString();
        },
    };
    execOpts.ignoreReturnCode = !opts.check;

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
    const pattern = new RegExp('submodule\.(.+)\.(path|url)=(.+)');

    // build map with properties of each submodule
    let map = {};

    const lines = gitResult.stdout.split('\n');
    for (var i = 0; i < lines.length; i++) {
        const match = pattern.exec(lines[i]);
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

const diffSubmodule = async function (submodule, targetBranch) {
    const gitResult = await run(['git', 'diff', targetBranch, '--', submodule.path]);
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


const checkSubmodules = async function () {
    const rootDir = process.cwd();

    // TODO: figure out how to access target branch
    // instead of hardcoding 'main'
    const targetBranch = 'origin/main';

    const submodules = await getSubmodules();
    for (var i = 0; i < submodules.length; i++) {
        const submodule = submodules[i];

        // diff submodule against target branch
        // if there's no difference, there's no need to analyze further
        diff = await diffSubmodule(submodule, targetBranch);
        if (diff == null) {
            continue
        }
    }
}

async function main() {
    try {
        await checkSubmodules();
    } catch (error) {
        core.setFailed(error.message);
    }
}

main()
