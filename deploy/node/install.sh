#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf '%s\n' 'Usage: bash install.sh [--version node-v1.2.3[-prerelease]]
       [--api-host https://panel.example.com] [--server-id 1]
       [--secret-key KEY] [--repo OWNER/REPO]

Install PPanel-node on Linux with systemd (root required except --help).
Default repository: jaoau0803/ppanel. Without --version, paginate GitHub
releases and choose the newest non-draft, non-prerelease node-v* release.
Explicit versions may be prereleases. Existing config.yml is preserved;
first installation requires all API settings or interactive /dev/tty input.
Dependencies are checked, never automatically installed.'
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

# Standard-library-only helpers; arguments are never evaluated as code or YAML.
helper() {
    python3 - "$@" <<'PY'
import datetime
import json
import pathlib
import re
import shutil
import sys
import tarfile
import urllib.parse

command, *args = sys.argv[1:]
version = r'node-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?'
try:
    if command == 'validate':
        ver, repo, host, sid, key = args
        if ver and not re.fullmatch(version, ver):
            raise ValueError('invalid --version (expected node-v1.2.3 or prerelease)')
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9][A-Za-z0-9._-]{0,99}', repo) or repo.split('/')[1] in ('.', '..'):
            raise ValueError('invalid --repo (expected OWNER/REPO)')
        if host:
            url = urllib.parse.urlsplit(host)
            if url.scheme not in ('http', 'https') or not url.hostname or url.username is not None or url.password is not None or url.query or url.fragment or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in host) or '\\' in host:
                raise ValueError('invalid --api-host (expected HTTP(S) URL without credentials/query/fragment)')
            port = url.port
        if sid and (not re.fullmatch(r'[1-9][0-9]*', sid) or int(sid) > 2147483647):
            raise ValueError('invalid --server-id (expected 1..2147483647)')
        if key and (len(key) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in key)):
            raise ValueError('invalid --secret-key (control characters or excessive length)')
    elif command == 'select':
        releases = json.load(open(args[0]))
        if not isinstance(releases, list):
            raise ValueError('GitHub releases API did not return a list')
        candidates = []
        for release in releases:
            tag = release.get('tag_name', '')
            if not release.get('draft', True) and not release.get('prerelease', True) and re.fullmatch(version, tag) and '-' not in tag[len('node-v'):]:
                published = release.get('published_at')
                if published:
                    timestamp = datetime.datetime.fromisoformat(published.replace('Z', '+00:00')).timestamp()
                    candidates.append((timestamp, tag))
        print(len(releases))
        if candidates:
            timestamp, tag = max(candidates)
            print(f'{timestamp:.0f} {tag}')
    elif command == 'config':
        host, sid, key, target = args
        quote = lambda value: json.dumps(value, ensure_ascii=True)
        pathlib.Path(target).write_text('Log:\n  Level: "warn"\n  Output: ""\n  Access: "none"\nApi:\n  ApiHost: ' + quote(host) + '\n  ServerID: ' + sid + '\n  SecretKey: ' + quote(key) + '\n  Timeout: 30\n', encoding='utf-8')
    elif command == 'checksum':
        sums, asset, target = args
        matches = []
        for line in pathlib.Path(sums).read_text().splitlines():
            match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *](.+)', line)
            if match and match[2] == asset:
                matches.append(match[1])
        if len(matches) != 1:
            raise ValueError('SHA256SUMS must contain exactly one checksum for ' + asset)
        pathlib.Path(target).write_text(matches[0] + '  ' + asset + '\n')
    elif command == 'unpack':
        archive, destination = args
        required = ('ppnode', 'geoip.dat', 'geosite.dat', 'LICENSE', 'THIRD_PARTY_NOTICES.md')
        with tarfile.open(archive, 'r:gz') as tar:
            members = tar.getmembers()
            for name in required:
                found = [member for member in members if member.name == name]
                if len(found) != 1 or not found[0].isreg():
                    raise ValueError('archive must contain one flat regular file: ' + name)
            for name in required:
                with tar.extractfile(name) as source, open(pathlib.Path(destination) / name, 'wb') as target:
                    shutil.copyfileobj(source, target)
    else:
        raise ValueError('unknown helper command')
except (ValueError, OSError, KeyError, TypeError, tarfile.TarError) as error:
    sys.exit('Error: ' + str(error))
PY
}

main() {
    local version='' repo='jaoau0803/ppanel' host='' sid='' key='' option value
    local seen=' '
    while (($#)); do
        option=$1
        case "$option" in
            --help|-h) usage; return 0 ;;
            --version|--repo|--api-host|--server-id|--secret-key)
                [[ "$seen" != *" $option "* ]] || fail "duplicate option: $option"
                seen+="$option "
                (($# >= 2)) || fail "missing value for $option"
                value=$2
                [[ -n "$value" && "$value" != --* ]] || fail "missing value for $option"
                case "$option" in
                    --version) version=$value ;; --repo) repo=$value ;;
                    --api-host) host=$value ;; --server-id) sid=$value ;;
                    --secret-key) key=$value ;;
                esac
                shift 2 ;;
            *) fail "unknown argument: $option" ;;
        esac
    done
    command -v python3 >/dev/null 2>&1 || fail 'missing dependency: python3'
    helper validate "$version" "$repo" "$host" "$sid" "$key"
    [[ $(uname -s) == Linux ]] || fail 'Linux is required'
    [[ $EUID == 0 ]] || fail 'run this installer as root'
    local dependency
    for dependency in curl sha256sum systemctl mktemp mkdir install ln mv rm chmod cat; do
        command -v "$dependency" >/dev/null 2>&1 || fail "missing dependency: $dependency"
    done
    [[ -d /run/systemd/system ]] || fail 'systemd must be running as the system service manager'
    local arch
    case "$(uname -m)" in
        x86_64|amd64) arch=amd64 ;; aarch64|arm64) arch=arm64 ;;
        s390x) arch=s390x ;; *) fail 'unsupported architecture (need amd64, arm64 or s390x)' ;;
    esac
    if [[ ! -e /etc/PPanel-node/config.yml ]]; then
        if [[ -z "$host" || -z "$sid" || -z "$key" ]]; then
            exec 3<>/dev/tty || fail 'first installation requires --api-host, --server-id and --secret-key, or /dev/tty'
            if [[ -z "$host" ]]; then printf 'API host: ' >&3; IFS= read -r host <&3; fi
            if [[ -z "$sid" ]]; then printf 'Server ID: ' >&3; IFS= read -r sid <&3; fi
            if [[ -z "$key" ]]; then printf 'Secret key: ' >&3; IFS= read -rs key <&3; printf '\n' >&3; fi
            exec 3>&-
        fi
        [[ -n "$host" && -n "$sid" && -n "$key" ]] || fail 'API settings must not be empty'
        helper validate "$version" "$repo" "$host" "$sid" "$key"
    fi
    umask 077
    local tmp
    tmp=$(mktemp -d)
    # Keep the path available to EXIT after main returns.
    trap "rm -rf -- $(printf '%q' "$tmp")" EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    if [[ -z "$version" ]]; then
        local page=1 count candidate best='' stamp best_stamp=0 tag
        while :; do
            download "https://api.github.com/repos/$repo/releases?per_page=100&page=$page" "$tmp/releases.json"
            helper select "$tmp/releases.json" > "$tmp/selection"
            { IFS= read -r count; IFS= read -r candidate || true; } < "$tmp/selection"
            if [[ -n "$candidate" ]]; then
                read -r stamp tag <<< "$candidate"
                if ((stamp > best_stamp)); then best_stamp=$stamp; best=$tag; fi
            fi
            ((count == 100)) || break
            page=$((page + 1))
        done
        [[ -n "$best" ]] || fail 'no stable node-v* release found'
        version=$best
    fi
    local asset="ppanel-node-linux-$arch.tar.gz"
    local base="https://github.com/$repo/releases/download/$version"
    download "$base/$asset" "$tmp/$asset"
    download "$base/SHA256SUMS" "$tmp/SHA256SUMS"
    helper checksum "$tmp/SHA256SUMS" "$asset" "$tmp/checksum"
    (cd "$tmp" && sha256sum -c checksum)
    mkdir "$tmp/files"
    helper unpack "$tmp/$asset" "$tmp/files"
    helper config "$host" "${sid:-1}" "$key" "$tmp/config.yml"
    cat > "$tmp/PPanel-node.service" <<'EOF'
[Unit]
Description=PPanel Node
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/usr/local/PPanel-node
ExecStart=/usr/local/PPanel-node/ppnode server --config /etc/PPanel-node/config.yml
Restart=on-failure
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
    # No installation files or service state are touched before all staging succeeds.
    install -d -m 755 /usr/local/PPanel-node /usr/local/bin /etc/PPanel-node /etc/systemd/system
    local name
    for name in ppnode geoip.dat geosite.dat LICENSE THIRD_PARTY_NOTICES.md; do
        install -m 644 "$tmp/files/$name" "/usr/local/PPanel-node/.$name.new"
        if [[ "$name" == ppnode ]]; then chmod 755 "/usr/local/PPanel-node/.$name.new"; fi
        mv -f "/usr/local/PPanel-node/.$name.new" "/usr/local/PPanel-node/$name"
    done
    if [[ ! -e /etc/PPanel-node/config.yml ]]; then
        install -m 600 "$tmp/config.yml" /etc/PPanel-node/config.yml
    fi
    ln -sfn /usr/local/PPanel-node/ppnode /usr/local/bin/ppnode
    install -m 644 "$tmp/PPanel-node.service" /etc/systemd/system/PPanel-node.service
    systemctl daemon-reload
    systemctl enable PPanel-node
    systemctl restart PPanel-node
    printf 'Installed %s. Config: /etc/PPanel-node/config.yml\n' "$version"
    printf 'Manage: systemctl {status|start|stop|restart} PPanel-node\nLogs: journalctl -u PPanel-node -f\n'
}

download() {
    curl -f --silent --show-error --location --proto '=https' --proto-redir '=https' \
        --connect-timeout 15 --max-time 300 --retry 3 --output "$2" "$1"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
