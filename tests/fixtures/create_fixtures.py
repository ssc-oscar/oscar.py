#!/usr/bin/python2
# IMPORTANT: this script requires python-tokyocabinet, which is Py2 only

import binascii
from collections import defaultdict

from tokyocabinet import hash as tch


def ber(*numbers):
    def gen():
        for num in numbers:
            a = True
            while a:
                a, num = divmod(num, 128)
                yield chr(a + 0x80 if a else num)
    return b''.join(gen())


def unber(s):
    res = []
    acc = 0
    for char in s:
        b = ord(char)
        acc = (acc << 7) + (b & 0x7f)
        if not b & 0x80:
            res.append(acc)
            acc = 0
    return res


def shas2prefixes(shas, max_prefix):
    # type: (Iterable[str], int) -> Dict[int, str]
    prefixes = defaultdict(list)
    for sha in shas:
        key = binascii.unhexlify(sha)
        prefixes[ord(key[0]) & max_prefix].append(key)
    return prefixes


def create_fixture(shas, input_path, key_length=7, num_records=1000):
    # type: (Iterable[str], str, int) -> None
    """ Create fixtures for local testing.
    Object type is implicitly given in input_fmask - just copy the data, object
    structure is not relevant for fixture preparation purposes

    Special cases to handle:
      - create a placeholder for max prefix to make key length calculation work
      - prefix 0 .tch should contain num_records
      - the same prefix 0 .tch should contain a predefined key: value,
        b'test_key' -> b'\x00\x01\x02\x03'

    """
    max_prefix = 2**key_length - 1
    prefixes = shas2prefixes(shas, max_prefix)
    output_path = input_path.rsplit('/', 1)[-1]

    # - create a placeholder for max prefix to make key length calculation work
    with open(output_path.format(key=max_prefix), 'wb') as _:
        pass
    # - prefix 0 .tch should contain num_records - get enough keys
    db = tch.Hash(input_path.format(key=0), tch.HDBOREADER | tch.HDBONOLCK)
    # -1 is to reserve a record for the predefined key: value
    prefixes[0].extend(db.fwmkeys('')[:num_records-len(prefixes[0]) - 1])
    db.close()

    for prefix, keys in prefixes.items():
        db = tch.Hash(output_path.format(key=prefix),
                      tch.HDBOCREAT | tch.HDBOWRITER)
        data_db = tch.Hash(input_path.format(key=prefix),
                           tch.HDBOREADER | tch.HDBONOLCK)
        for key in keys:
            db.put(key, data_db[key])

        # prefix 0 .tch should contain a predefined key: value
        if not prefix:
            db.put(b'test_key', b'\x00\x01\x02\x03')
        db.close()
        data_db.close()


def create_blob_fixture(shas, key_length=7):
    max_prefix = 2**key_length - 1
    prefixes = shas2prefixes(shas, max_prefix)

    blob_content = b'*.egg-info/\ndist/\nbuild/\n*.pyc\n*.mo\n*.gz\n'

    offset_input_path = '/fast/All.sha1o/sha1.blob_{key}.tch'
    offset_output_path = offset_input_path.rsplit('/', 1)[-1]
    data_input_path = '/da4_data/All.blobs/blob_{key}.bin'
    data_output_path = data_input_path.rsplit('/', 1)[-1]

    with open(offset_output_path.format(key=max_prefix), 'wb') as _:
        pass
    with open(data_output_path.format(key=max_prefix), 'wb') as _:
        pass

    for prefix, keys in prefixes.items():
        offset_out = tch.Hash(offset_output_path.format(key=prefix),
                              tch.HDBOCREAT | tch.HDBOWRITER)
        data_out = open(data_output_path.format(key=prefix), 'wb')
        offset_in = tch.Hash(offset_input_path.format(key=prefix),
                             tch.HDBOREADER | tch.HDBONOLCK)
        data_in = open(data_input_path.format(key=prefix), 'rb')

        pos = 0
        for key in keys:
            offset, length = unber(offset_in[key])
            data_in.seek(offset, 0)
            blob_data = data_in.read(length)
            data_out.write(blob_data)
            offset_out.put(key, ber(pos, length))
            pos += length

        data_out.close()
        offset_out.close()


def main():
    # only 83d22195edc1473673f1bf35307aea6edf3c37e3 is actually used:
    create_blob_fixture([u'234a57538f15d72f00603bf086b465b0f2cda7b5',
                         u'83d22195edc1473673f1bf35307aea6edf3c37e3',
                         u'fda94b84122f6f36473ca3573794a8f2c4f4a58c',
                         u'46aaf071f1b859c5bf452733c2583c70d92cd0c8'])
    create_fixture([u'd4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d'],
                   '/fast/All.sha1c/tree_{key}.tch')
    create_fixture([u'f2a7fcdc51450ab03cb364415f14e634fa69b62c',
                    u'e38126dbca6572912013621d2aa9e6f7c50f36bc',
                    u'1cc6f4418dcc09f64dcbb0410fec76ceaa5034ab'],
                   '/fast/All.sha1c/commit_{key}.tch')


if __name__ == '__main__':
    main()
