"""Decode output from native tools without locale-dependent reader threads."""
import subprocess


def decode_output(data):
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('cp1252')


def run_text_tool(command, timeout=180):
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    if result.returncode:
        diagnostic = result.stderr or result.stdout
        raise RuntimeError(f'{command[0]} : {decode_output(diagnostic).strip()}')
    return decode_output(result.stdout)
