import hashlib
import re

def sha256_file(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()

def safe_name(name):
    cleaned = re.sub('[\\\\/:*?"<>|\\x00-\\x1f]', '_', name).strip(' .')
    return cleaned[:90] or 'audio'
