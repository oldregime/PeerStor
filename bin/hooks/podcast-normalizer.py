#!/usr/bin/env python3

import json
import os
import sys
import subprocess as sp


_ = r"""
sends all uploaded audio files through an aggressive
dynamic-range-compressor to even out the volume levels

dependencies:
    ffmpeg

being an xau hook, this gets eXecuted After Upload completion
    but before copyparty has started hashing/indexing the file, so
    we'll create a second normalized copy in a subfolder and tell
    copyparty to hash/index that additional file as well

example usage as global config:
    -e2d -e2t --xau j,c1,bin/hooks/podcast-normalizer.py

parameters explained,
    e2d/e2t = enable database and metadata indexing
    xau = execute after upload
    j   = this hook needs upload information as json (not just the filename)
    c1  = this hook returns json on stdout, so tell copyparty to read that

example usage as a volflag (per-volume config):
    -v srv/inc/pods:inc/pods:r:rw,ed:c,xau=j,c1,bin/hooks/podcast-normalizer.py
                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    (share fs-path srv/inc/pods at URL /inc/pods,
     readable by all, read-write for user ed,
     running this xau (exec-after-upload) plugin for all uploaded files)

example usage as a volflag in a copyparty config file:
    [/inc/pods]
      srv/inc/pods
      accs:
        r: *
        rw: ed
      flags:
        e2d  # enables file indexing
        e2t  # metadata tags too
        xau: j,c1,bin/hooks/podcast-normalizer.py

"""

########################################################################
### CONFIG

# filetypes to process; ignores everything else
EXTS = "mp3 flac ogg oga opus m4a aac wav wma"

# the name of the subdir to put the normalized files in
SUBDIR = "normalized"

########################################################################


# try to enable support for crazy filenames
try:
    from copyparty.util import fsenc
except:

    def fsenc(p):
        return p.encode("utf-8")


def main():
    # read info from copyparty
    inf = json.loads(sys.argv[1])
    vpath = inf["vp"]
    abspath = inf["ap"]

    # check if the file-extension is on the to-be-processed list
    ext = abspath.lower().split(".")[-1]
    if ext not in EXTS.split():
        return

    # jump into the folder where the file was uploaded
    # and create the subfolder to place the normalized copy inside
    dirpath, filename = os.path.split(abspath)
    os.chdir(fsenc(dirpath))
    os.makedirs(SUBDIR, exist_ok=True)

    # the input and output filenames to give ffmpeg
    fname_in = fsenc(f"./{filename}")
    fname_out = fsenc(f"{SUBDIR}/{filename}.opus")

    # fmt: off
    # create and run the ffmpeg command
    cmd = [
        b"ffmpeg",
        b"-nostdin",
        b"-hide_banner",
        b"-i", fname_in,
        b"-af", b"dynaudnorm=f=100:g=9",  # the normalizer config
        b"-c:a", b"libopus",
        b"-b:a", b"128k",
        fname_out,
    ]
    # fmt: on
    sp.check_output(cmd)

    # and finally, tell copyparty about the new file
    # so it appears in the database and rss-feed:
    vpath = f"{SUBDIR}/{filename}.opus"
    print(json.dumps({"idx": {"vp": [vpath]}}))

    # (it's fine to give it a relative path like that; it gets
    #  resolved relative to the folder the file was uploaded into)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print("podcast-normalizer failed; %r" % (ex,))
