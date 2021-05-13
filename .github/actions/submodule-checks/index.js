const core = require('@actions/core');
const github = require('@actions/github');
const exec = require('@actions/exec');

// cwd: optional string
// check: set false
const run = async function(args, opts={}) {
    let result = {};
    result.stdout = '';

    const execOpts = {};
    execOpts.listeners = {
      stdout: (data) => {
        result.stdout += data.toString();
      },
    };

    if ('cwd' in opts) {
        execOpts.cwd = opts.cwd;
    }

    result.returnCode = await exec.exec(args[0], args.slice(1), execOpts);
    return result;
}

// Returns array of submodules, where each item has properties: name, path, url
const getSubmodules = async function() {
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
    return Object.values(map).sort((a,b) => a.name.localeCompare(b.name));
}


const main = async function() {
    core.info(`GITHUB_SHA: ${github.context.sha}`)
    core.info(`GITHUB_REF: ${github.context.ref}`)
    core.info(`GITHUB_BASE_REF: ${process.env.GITHUB_BASE_REF}`)
    const rootDir = process.cwd();

    const submodules = await getSubmodules();
    for (var i = 0; i < submodules.length; i++) {
        const submodule = submodules[i];
        //diff = await diffSubmodule(submodule);
    }
}

try {
    main();
} catch (error) {
    core.setFailed(error.message);
}
