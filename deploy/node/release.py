"""Validate node release metadata before checkout/build or publishing."""
import os
import re


def metadata(event, ref_type, ref_name, version):
    if event == 'push' or ref_type == 'tag':
        tag = ref_name
        if event == 'workflow_dispatch' and version:
            requested = version if version.startswith('node-v') else 'node-v' + version.removeprefix('v')
            if requested != tag:
                raise ValueError('version must match the selected tag')
    else:
        tag = version if version.startswith('node-v') else 'node-v' + version.removeprefix('v')
    if not re.fullmatch(r'node-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:beta|rc)\.(0|[1-9][0-9]*))?', tag):
        raise ValueError('expected node-v1.2.3, node-v1.2.3-beta.1 or node-v1.2.3-rc.1')
    return tag, '-' in tag[len('node-v'):]


if __name__ == '__main__':
    tag, prerelease = metadata(os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_REF_TYPE'], os.environ['GITHUB_REF_NAME'], os.environ.get('INPUT_VERSION', ''))
    with open(os.environ['GITHUB_ENV'], 'a') as output:
        output.write(f'NODE_TAG={tag}\nNODE_PRERELEASE={str(prerelease).lower()}\n')
