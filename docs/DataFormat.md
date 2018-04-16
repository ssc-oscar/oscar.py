

## Git objects

All git ogjects are stored basically the same way.
Each git object is uniquely identified by its SHA1 hash.
First, you need to convert this hash into a record number:

- Obtain a record number from da4:/fast1/All.sha1/sha1.{commit,tree,tag,blob}_{0..127}.tch
  Use proper object type (blob, commit, tree or tag) and index (first 8 bits of sha-1 hash)
  to refer to the right Tokyo Cabinet file

### Blobs


**How**: record contains just a number