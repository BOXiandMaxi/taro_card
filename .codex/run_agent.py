"""Run one project role, or validate its effective configuration without inference."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import tomllib

PROJECT = Path(__file__).resolve().parent.parent
ROLE_KEYS = ('model', 'model_reasoning_effort', 'sandbox_mode', 'developer_instructions')


def resolve_cli(explicit):
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ValueError('Codex executable does not exist: ' + str(path))
        return str(path)
    # Prefer the installed CLI, which may be newer than VS Code's bundled binary.
    found = shutil.which('codex.cmd') or shutil.which('codex')
    if found:
        return found
    found = shutil.which('codex.exe')
    if found:
        return found
    extensions = Path.home() / '.vscode/extensions'
    candidates = sorted(extensions.glob('openai.chatgpt-*/bin/windows-x86_64/codex.exe'), reverse=True)
    if candidates:
        return str(candidates[0])
    raise ValueError('Codex CLI not found. Supply --codex with its executable path.')


def role_settings(role):
    path = PROJECT / '.codex/agents' / (role + '.toml')
    config = tomllib.loads(path.read_text(encoding='utf-8'))
    assert config['name'] == role and config['description']
    assert all(config.get(key) for key in ROLE_KEYS)
    return config


def override_args(config):
    # JSON quoted strings are valid TOML strings. Pass argument arrays without a shell.
    args = []
    for key in ROLE_KEYS:
        args.extend(['-c', key + '=' + json.dumps(config[key], ensure_ascii=False)])
    # This is a leaf role: never create unrequested nested agents.
    args.extend(['-c', 'agents.enabled=false'])
    return args


def check(cli, config, env):
    process = subprocess.Popen([cli, 'app-server', '--strict-config', '--stdio', *override_args(config)], cwd=PROJECT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    output = queue.Queue()
    diagnostics = []
    def consume():
        for line in process.stdout:
            output.put(line)
        output.put(None)
    def consume_errors():
        for line in process.stderr:
            diagnostics.append(line)
    threading.Thread(target=consume, daemon=True).start()
    threading.Thread(target=consume_errors, daemon=True).start()
    def request(id, method, params):
        process.stdin.write(json.dumps({'id': id, 'method': method, 'params': params}) + '\n')
        process.stdin.flush()
        while True:
            line = output.get(timeout=30)
            if line is None:
                raise RuntimeError('Codex app-server exited: ' + ''.join(diagnostics)[-2000:])
            result = json.loads(line)
            if result.get('id') == id:
                if 'error' in result:
                    raise RuntimeError(str(result['error']))
                return result['result']
    try:
        request(1, 'initialize', {'clientInfo': {'name': 'project-role-check', 'version': '1.0'}, 'capabilities': {'experimentalApi': True}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        result = request(2, 'config/read', {'cwd': str(PROJECT), 'includeLayers': True})
        effective = result['config']
        # The full layer retains settings omitted from the public Config response.
        merged = {}
        for layer in reversed(result.get('layers', [])):
            if not layer.get('disabledReason'):
                merged.update(layer.get('config', {}))
        for key in ROLE_KEYS:
            actual = effective.get(key, merged.get(key))
            assert actual == config[key], 'Role setting did not load: ' + key
        project_layers = [layer for layer in result.get('layers', []) if layer.get('name', {}).get('type') == 'project']
        assert project_layers and not any(layer.get('disabledReason') for layer in project_layers), 'Trust this project before using its configuration.'
        assert effective.get('agents', {}).get('enabled') is False
        print(config['name'] + ': OK | ' + config['model'] + ' | ' + config['model_reasoning_effort'] + ' | ' + config['sandbox_mode'] + ' | instructions loaded')
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=('explorer', 'logic', 'coder', 'reviewer', 'ui', 'all'))
    parser.add_argument('prompt', nargs='?', help='Task for this role; use - to read UTF-8 task text from stdin.')
    parser.add_argument('--check', action='store_true', help='Validate role loading through Codex without making a model request.')
    parser.add_argument('--codex', help='Explicit Codex executable path.')
    args = parser.parse_args()
    if args.role == 'all' and not args.check:
        parser.error('all is permitted only with --check; do not automatically run every role.')
    if not args.check and not args.prompt:
        parser.error('Supply a scoped task or use --check.')
    cli = resolve_cli(args.codex)
    env = os.environ.copy()
    if not env.get('CODEX_HOME'):
        env['CODEX_HOME'] = str(Path.home() / '.codex')
    roles = ('explorer', 'logic', 'coder', 'reviewer', 'ui') if args.role == 'all' else (args.role,)
    for role in roles:
        config = role_settings(role)
        if args.check:
            check(cli, config, env)
        else:
            prompt = sys.stdin.read() if args.prompt == '-' else args.prompt
            result = subprocess.run([cli, 'exec', '--strict-config', '--ephemeral', '--skip-git-repo-check', '-C', str(PROJECT), *override_args(config), '-'], input=prompt, text=True, encoding='utf-8', env=env, cwd=PROJECT)
            return result.returncode
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, AssertionError, RuntimeError, queue.Empty) as error:
        print('Configuration check failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
