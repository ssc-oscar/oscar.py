

## Git objects

### Sequential access:

Read an index line from /data/All.blobs/{commit,blob,tag,tree}_{key}.idx
to get offset and length. 
Note that the key, a 1..127 uint, is 7 least significant bits of the
first byte of sha, and not 7 msb. 
So, to get the key, use `sha[0] & 7f`, NOT bit shift.

Content of .idx files for commits, trees and tags:

    id, offset, length, object sha

e.g.:

    0;0;267;80b4ca99f8605903d8ac6bd921ebedfdfecdd660
    1;267;185;0017b852ce7b49225c5a797b3d4221d363c0acdd
    2;452;167;0054bab7302b386ddf2350a3fb2db08d59e125e1
    3;619;235;8028315640bac6eae17297270d4ee1892abf6add


Blobs:

    id, offset, length, ??int, blob sha, ??sha, ??int

e.g.

    0;0;461;647;00b31262da21c4f57d5b207372b6ded0bb332911;c88e5561832d1fe25a5e19cf15dc7de2fd81aae5;365420358
    1;461;2836;7145;00ad7956ac3c0227c0abf2e59b3270c54837bf46;c83d8bfb7c8aef24c8c2efd0abf4d90c7e0cc421;366044154
    2;3297;1170;2524;00b9870d283215cbe9eeca5433f211b702a749a1;00549bb056793128f1f35b1ada0a375466a69905;366711281

You can also obtain index line number for an arbitrary object from
`/fast1/All.sha1/sha1.{commit,tree,tag}_{key}.tch` or
`/fast/All.sha1/sha1.blob_{key}.tch`, but it doesn't look very useful
neither for sequential nor random access.


### Accessing an arbitrary git object:

Full content is available for commits, trees and tags in
`/fast1/All.sha1c/{tree,commit}_{0..127}.tch`

For blobs,

    /data/All.sha1o/sha1.blob_{1..127}

1. Get index line number from
    /fast1?/All.sha1/sha1.{commit,blob,tag,tree}_{key}.tch
3. read compressed data by the given offset/length from /data/All.blobs/{commit,blob,tag,tree}_{key}.bin
4. Uncompress with LZF. Note that unlike vanilla LZF used by python-lzf
    Perl `Compress::LZF` also prepends variable length header with uncompressed
    chunk size.


## Mappings

There is a bunch of .tch files in /fast1/All.sha1c/ holding mappings:

    b2cFullE.{0..7}.tch
    c2fFull.{0..7}.tch
    Cmt2Prj.{0..7}.tch -
    commit_parent_{0..127}.tch


## Unknown

    /fast1/All.sha1c/:
        Auth2Cmt.tch
        author_class.tch
        author_commit.tch
        class2commit.tch
        commit_atime.tch
        commit_child.tch
        commit_class.tch
        f2b.tch
        NAMESPACE.tch
        package.json.{1..127}.tch
        setup.py.{key}.tch

