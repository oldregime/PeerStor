import os
import random
from urllib.parse import quote


# assuming /foo/bar/ is a valid URL but /foo/bar/randpic.png does not exist,
# hijack the 404 with a redirect to a random pic in that folder
#
# thx to lia & kipu for the idea


def main(cli, vn, rem):
    req_fn = rem.split("/")[-1]
    if not cli.can_read or not req_fn.startswith("randpic"):
        return

    req_abspath = vn.canonical(rem)
    req_ap_dir = os.path.dirname(req_abspath)
    files_in_dir = os.listdir(req_ap_dir)

    if "." in req_fn:
        file_ext = "." + req_fn.split(".")[-1]
        files_in_dir = [x for x in files_in_dir if x.lower().endswith(file_ext)]

    if not files_in_dir:
        return

    selected_file = random.choice(files_in_dir)

    req_url = "/".join([vn.vpath, rem]).strip("/")
    req_dir = req_url.rsplit("/", 1)[0]
    new_url = "/".join([req_dir, quote(selected_file)]).strip("/")

    cli.reply(b"redirecting...", 302, headers={"Location": "/" + new_url})
    return "true"
