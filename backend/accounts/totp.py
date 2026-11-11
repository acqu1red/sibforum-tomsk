import base64
import hashlib
import hmac
import struct
import time


def counter_at(timestamp=None):
    return int((timestamp or time.time()) // 30)


def totp_code(secret, counter):
    padded = secret + '=' * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f'{value:06d}'


def verify_totp(secret, code, last_counter=None, timestamp=None):
    code = str(code or '').strip()
    if not code.isdigit() or len(code) != 6:
        return None
    counter = counter_at(timestamp)
    for candidate in (counter - 1, counter, counter + 1):
        if last_counter is not None and candidate <= last_counter:
            continue
        if hmac.compare_digest(totp_code(secret, candidate), code):
            return candidate
    return None
