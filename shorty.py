import sys
import os
from functools import wraps

import hashlib
import mimetypes

from flask import Flask, render_template, request, flash, redirect, Response, url_for, send_file
from flask import Blueprint, render_template, jsonify

from werkzeug.utils import secure_filename

#main = Blueprint("main", __name__, template_folder="pages")

from urllib.parse import quote, urlparse
from uuid import uuid4 as create_uid

import yaml

from utils import load_config, save_config

# where to find the .yaml config file
YAML_CFG_PATH = sys.argv[1]
cfg = load_config(YAML_CFG_PATH)

# global url prefix, if flask is located in a sub-directory
URL_PREFIX = cfg.get("url_prefix", "/")

# flask init
app = Flask(__name__)
app.secret_key = cfg["secret_key"]

####
#### utils
####

#def render_page(dirname, msgs=None, editor_target=None, tmpl="tmpl.html"):
#    parent = os.path.dirname(dirname)
#    return render_template(tmpl,
#        editor_target=editor_target,
#        parent_dir="" if dirname == "" else os.path.basename(parent),
#        parent_path="" if dirname == "" else parent,
#        base_dir=dirname if dirname != "" else ".",
#        base_dir_name=os.path.basename(dirname if dirname != "" else "."),
#        messages=msgs if msgs is not None else [],
#        url_prefix=URL_PREFIX
#    )

def make_pass(pwd):
    return pwd

def check_auth_global(username, password):
    return username == cfg["user"] and cfg["pwd"] == make_pass(password)

def check_auth_shared(share, username, password):
    return username == cfg["user"] and cfg["pwd"] == make_pass(password)

def http_authenticate():
    return Response("No access!", 401, {
      "WWW-Authenticate": 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth_global(auth.username, auth.password):
            return http_authenticate()
        return f(*args, **kwargs)
    return decorated
requires_zone_auth = requires_auth


####
#### endpoints
####

@app.route("/local/<path:target>", methods=["GET"])
#@requires_auth
def get_static(target=""):
    if ".." in target:
        return;

    p = os.path.join("static", target)
    data = None
    with open(p, "r") as fd:
        data = fd.read()
    mime_info = mimetypes.guess_type(p)
    return Response(data, mimetype=mime_info[0])

@app.route("/local/icon/<string:icon>", methods=["GET"])
def get_icon(icon):
    if ".." in icon:
        return;

    p = os.path.join("static", "icons", "svg", icon + ".svg")
    data = None
    with open(p, "r") as fd:
        data = fd.read()
    mime_info = mimetypes.guess_type(p)
    return Response(data, mimetype=mime_info[0])


@app.route("/new/", methods=["POST"])
@app.route("/new/<path:dirname>", methods=["POST"])
@requires_auth
def create(dirname=""):
    state = "ok"
    try:
        if request.form.get("what") == "create" and \
          len(request.form.get("new_dirname").strip()) > 0:
            new_dirname = request.form.get("new_dirname")
            filedb.create_dir(dirname, new_dirname)
            msg = f"directory created: {new_dirname}"

        elif request.form.get("what") == "upload":
            app.config["UPLOADS_FILES_DEST"] = filedb.get_path(dirname)
            req_file = request.files.get("target")
            if not req_file:
                msg = f"Error: no uploaded file found..."
                state = "fail"
            else:
                filename = filedb.create_file(dirname, req_file)
                msg = f"Saved to: {filename}"

        elif request.form.get("what") in ["save", "savenew"]:
            app.config["UPLOADS_FILES_DEST"] = filedb.get_path(dirname)
            if filedb.isfile(os.path.join(dirname, request.form.get("filename"))):
                filename = filedb.update_file(dirname,
                    request.form.get("filename"), request.form.get("data"))
                msg = f"Updated file: {filename}"
            else:
                filename = filedb.create_raw_file(dirname,
                    request.form.get("filename"), request.form.get("data"))
                msg = f"Created file: {filename}"
        else:
            msg = "invalid request"
            state = "fail"
    except FileDBError as e:
        msg = repr(e)
        state = "fail"
    return jsonify({"dirname": dirname, "msgs": [msg], "state": state})

@app.route("/")
@app.route("/dir/")
@app.route("/dir/<path:dirname>")
@requires_auth
def show(dirname=""):
    #return render_page(dirname, msgs=[request.args.get("msg")])
    #print (list(request.args), request.args.get("msg"))
    return render_page(dirname, msgs=[request.args.get("msg")])


@app.route("/list/<string:what>/")
@app.route("/list/<string:what>/<path:dirname>")
@requires_auth
def ls(what, dirname=""):
    raw_list = map(lambda p: {
            "name": p,
            "path": os.path.join(dirname, p),
            "meta": filedb.get_meta_from_yaml(os.path.join(dirname, p))
        },
        filedb.get_dirs(dirname) if what == "dirs" else \
        filedb.get_files(dirname))

    get_mime = lambda tar: mimetypes.guess_type(filedb.get_path(tar))[0]
    data = list(map(lambda dct: {
          "name": dct["name"],
          "path": dct["path"],
          "uid": str(create_uid())[:8],
          "mimetype": get_mime(dct["path"]),
          "size": filedb.get_size(dct["path"]),
          #"zones": ",".join(z[0] for z in dct["meta"].get("zones")),
          "short": dct["meta"].get("short"),
          "delete_url": url_for("delete", target=dct["path"]),
          "move_url": url_for("move", target=dct["path"]),
          "click_url": url_for("ls", what=what, dirname=dct["path"]) \
            if what == "dirs" else url_for("get_file", target=dct["path"]),
          "visit_url": url_for("show", dirname=dct["path"]) \
            if what == "dirs" else url_for("get_file", target=dct["path"]),
        }, raw_list))

    data = {"data": data, "upload_url": url_for("create", dirname=dirname)}
    return jsonify(data)


@app.route("/edit/<path:target>", methods=["GET"])
@requires_auth
def edit(target):
    return render_page(dirname=os.path.dirname(target), editor_target=target)

@app.route("/move/<path:target>", methods=["POST"])
@requires_auth
def move(target):

    old_parent = os.path.dirname(target)
    new_target = os.path.join(old_parent, request.form.get("new_target"))
    try:
        filedb.move_path(target, new_target)
        filedb.update_path_in_yaml(target, new_target)
    except OSError as e:
        return jsonify({"msg": repr(e), "state": "fail"})

    shortinfo = ""
    new_short = request.form.get("new_short")
    if not (new_short is None or new_short == "None"):
        if filedb.get_meta_from_yaml(new_target).get("short", "") != new_short:
            ret = filedb.update_meta_in_yaml(new_target, new_short)
            shortinfo = f"[new short: '{new_short}' already taken!]" \
                    if not ret else \
                (f"[new short: '{new_short}']" if new_short != "" else \
                 "[REMOVED SHORT]")

    return jsonify({"msg": f"'{target}' moved to '{new_target}' {shortinfo}",
                    "state": "ok"})

@app.route("/del/<path:target>", methods=["POST"])
@requires_auth
def delete(target):
    try:
        if filedb.isdir(target):
            filedb.delete_dir(target)
        elif filedb.isfile(target):
            filedb.delete_file(target)
        else:
            raise ValueError(target)
    except FileDBError as e:
        return jsonify({"msg": repr(e), "state": "fail"})
    return jsonify({"msg": f"'{target}' deleted", "state": "ok"})

def file_get_helper(target, raw=False):
    try:
        fn = filedb.get_path(target)
        mime_info = mimetypes.guess_type(fn)
        if raw:
            out = None
            with open(fn, "r") as fd:
                out = fd.read()
            return out
        else:
            return send_file(fn, mimetype=mime_info[0])

    except FileDBError as e:
        msg = repr(e)
        return render_page(os.path.dirnane(target), [msg])


#@app.route("/s/<zone>/<s_id>", methods=["POST", "GET", "DELETE"])
#@app.route("/s/<zone>", methods=["POST", "DELETE"])
#@app.route("/s/x/<s_id>",   methods=["GET"])
#@app.route("/s/x",          methods=["POST", "DELETE"])
#@requires_zone_auth
#def safe_shorties(zone, s_id=None):
#    return shorties(zone, s_id)

@app.route("/s/<s_id>", methods=["GET"])
#@app.route("/s/",       methods=["POST", "DELETE"])
def shorties(s_id):
    rel_path = filedb.get_short_from_yaml(s_id)
    if not rel_path:
        #return jsonify({"msg": f"invalid request", "state": "fail"})
        return redirect(url_for("custom_err", code=404))
    return file_get_helper(rel_path)

@app.route("/err/<int:code>", methods=["GET"])
def custom_err(code):
   desc = {
     404: "Not Found",
     403: "Not Allowed",
   }.get(code, "")
   return render_template("custom_err.html", err_code=code, err_desc=desc)


#### @TODO: same here -> rework!!!!
#@app.route("/pastebin", methods=["GET", "POST"])
@app.route("/pastebin", methods=["GET"])
def pastebin():
    targetdir = "pastebin"
    uid = str(create_uid())[:8]
    while uid in filedb.get_contents(targetdir):
        uid = str(create_uid())[:8]
    targetpath = os.path.join(targetdir, uid)
    return render_page(editor_target=targetpath, dirname=targetdir)

############
## just write / load database
## add 404 for the errors, they shall not be forwarded on misses
## yeah and what about the frontend ...


@app.route("/get/download/<path:target>", methods=["GET"])
@requires_auth
def get_file(target):
    return file_get_helper(target)

@app.route("/get/raw/<path:target>", methods=["GET"])
@requires_auth
def get_raw_file(target):
    try:
        return jsonify(file_get_helper(target, raw=True))
    except UnicodeDecodeError as e:
        return jsonify({"state": "fail", "msgs":
            ["Failed to load file as unicode...",
             repr(e)[:50]] })

@app.route("/get/<path:target>", methods=["GET"])
def get_file_short(target):
    return get_file(target)

#@app.route("/get/<file_id>", methods=["GET"])
#def get_pub_file(file_id):
#  pass


#@app.route('/photo/<id>')
#def show(id):
#    photo = Photo.load(id)
#    if photo is None:
#        abort(404)
#    url = photos.url(photo.filename)
#    return render_template('show.html', url=url, photo=photo)




if __name__ == "__main__":
    URL_PREFIX = ""
    app.run(host='0.0.0.0', port=5001, debug=True)
