

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

Mappings are stored in `/data/basemaps/`:

    Auth2Cmt.tch  # works
        Author to commits
        db[email] = bytestring of bin shas
        keys are non-normalized authors e.g. 'gsadaram <gsadaram@cisco.com>'
        9.35M keys
    b2cFullF.{0..15}.tch
        Blob to commits where this blob was added or removed
        db[blob_sha] = commit_bin_shas
    c2bFullF.{0..15}.tch  # bug #1
        Commit to blobs
        db[blob_sha] = commit_bin_shas
        Looks to be incomplete, see docs/Bugreport1 for details
    Prj2CmtG.{0..7}.tch  # works
        Project to Commits
        Project is a user_repo string, e.g. user2589_minicms
    Cmt2PrjG.{0..7}.tch  # works
        Commit to projects
        data is lzf compressed, semicolon separated list of projects
    Cmt2Chld.tch  # works
        Commit to children
        db[commit_sha] = children_commit_bin_shas
    f2cFullF.{0..7}.{tch,lst}  # bug #4
        File to commits where this file has been changed
        File is a full path, usually terminated with a newline
            e.g.: 'public_html/images/cms/flags/my.gif\n'
        There are 181M filenames as of Apr 2018 just in 0.tch
    t2pt0-127.{0..7}.{tch,lst}  # works
        Tree to parent trees
        db[tree_bin_sha] = parent_tree_bin_shas
    b2pt.00-15.{0..7}.tch  # bug #2 - deprecated
        Blob to parent trees

Python files:

    pyfiles.{0..7}.gz  # each line is a path to .py file (not just a filename)
    pyfilesC.{0..7}.gz  # hashes (trees or commits?)
        check 721141f28f0a15354e283eae26be43c2b81e6e52
    pyfilesCU.{0..7}.gz  # hashes (trees or commits?)
        check 0000000fcd1c59eac9dd76e7d75229065733de3b
    pyfilesP.{0..7}.gz  # projects (user_repo)


There is also a bunch of mappings in `/fast1/All.sha1c/*.tch`,
which looks to be outdated

    b2cFullE.{0..15}.tch  # blob to commits bin sha
    c2fFull.{0..7}.tch  # commit to filename?
    Cmt2Prj.{0..7}.tch
    commit_parent_{0..127}.tch
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
    setup.py.{1..127}.tch

