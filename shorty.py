import sys
import os
from functools import wraps

import hashlib
import mimetypes

from flask import Flask, render_template, request, flash, redirect, Response, url_for, send_file
from flask import Blueprint, jsonify

from werkzeug.utils import secure_filename

from urllib.parse import quote, urlparse, urlencode
from uuid import uuid4 as create_uid
from time import time as now
from datetime import timedelta as td
from copy import copy as cpy

import yaml

from utils import load_config, save_config
from mmpy import get_rest_decorator

# where to find the .yaml config file
YAML_CFG_PATH = sys.argv[1]
cfg = load_config(YAML_CFG_PATH)

DEFAULT_TTL = 60 * 60 * 24 * 30
MAX_UUID_LEN = 6

# global url prefix, if flask is located in a sub-directory
URL_PREFIX = cfg.get("url_prefix", "/")

# @TODO: set server_name if needed?!?!

# flask init
app = Flask(__name__)
app.secret_key = cfg["secret_key"]

####
#### utils
####

class Short(dict):
    attrs = ["short", "url", "created", "ttl"]

    @property
    def active_for(self):
        if self.ttl == -1:
            return td(years=100)
        return td(seconds=(self.created + self.ttl) - now())

    @property
    def inactive(self):
        return self.active_for < td(0)

    @property
    def info(self):
        return {
            "url":       self.url,     "ttl": self.ttl,
            "short_url": url_for("goto", short=self.short, _external=True),
            "created":   self.created, "active_for": str(self.active_for),
            "inactive":  self.inactive }

    def __getattr__(self, key):
        if key in self.attrs:
            if key not in self:
                return None
            return self[key]

    def __setattr__(self, key, val):
        if key in self.attrs:
            self[key] = val

def my_save_config(cfg, config_path=YAML_CFG_PATH):
    cfg["shorts"] = dict((short, dict(obj)) \
        for short, obj in cfg["shorts"].items())
    return save_config(cfg, config_path)

def my_load_config(config_path=YAML_CFG_PATH, obj=None):
    cfg = load_config(config_path)
    if "shorts" not in cfg or not isinstance(cfg["shorts"], dict):
      cfg["shorts"] = {}

    for short in cfg["shorts"]:
        cfg["shorts"][short] = Short(cfg["shorts"].get(short, {}))

    if obj is None:
        return cfg, cfg["shorts"]
    else:
        return cfg, cfg["shorts"], (obj and cfg["shorts"].get(obj, None))

def make_pass(pwd):
    return pwd

def check_auth_global(username, password):
    return username == cfg["user"] and cfg["pwd"] == make_pass(password)

#def check_auth_shared(share, username, password):
#   return username == cfg["user"] and cfg["pwd"] == make_pass(password)

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

rest = get_rest_decorator(app)
forbidden_shorts = {"gen", "unlink", "shorts", "list", "prune", "own", "del"}

@rest.get("/<string:short>/gen/<path:url>")
@requires_auth
def create_with_short(url, ttl=DEFAULT_TTL, short=None):
    return create(url, ttl, short)

@rest.get("/gen/<path:url>")
def create(url, ttl=DEFAULT_TTL, short=None):

    if len(request.args) > 0:
        url += "?" + urlencode(request.args)

    # @TODO: validate url @FIXME, more more more
    if not "." in url or not url.startswith("http"):
        return jsonify(state="fail", url=url,
            msg=f"cannot gen short, not a valid url: '{url}'")

    cfg, shorts = my_load_config()

    # short already exists -> fail
    if short and short in shorts:
        return jsonify(state="fail", url=url,
                       msg=f"cannot gen short: '{short}', already taken")

    # create short from uuid
    # @TODO: validate short is proper uri like this: ([a-Z0-9\-_]) ?
    if short is None:
        short = str(create_uid())[:MAX_UUID_LEN]
        while short in shorts:
            short = str(create_uid())[:MAX_UUID_LEN]

    if short not in shorts:
        if short in forbidden_shorts:
            return jsonify(state="fail", url=url,
                           msg=f"short: {short} not allowed (reserved word)")

        cfg["shorts"][short] = {"short": short,
          "url": url, "ttl": ttl, "created": int(now())}

        my_save_config(cfg)

        return jsonify(state="ok", url=url, ttl=ttl,
                       msg=f"new short-url: '{url}' as '{short}'",
                       short_url=url_for("goto", short=short, _external=True))

    return jsonify(state="fail", url=url,
                   msg=f"cannot gen short: '{short}' (already taken...)")

@rest.get("/list")
@requires_auth
def show_list():
    cfg, shorts = my_load_config()
    out = []
    for short, obj in sorted(shorts.items()):
        out.append(obj.info)
    return jsonify(out)

@rest.get("/<string:short>/del")
@requires_auth
def remove(short):
    cfg, shorts, obj = my_load_config(obj=short)
    if obj is None:
        return jsonify({"state": "fail",
                        "msg": "short: {short} not in database"})

    out = dict(obj.info)
    del shorts[short]
    out["state"] = "ok (deleted)"
    my_save_config(cfg)
    return out

@rest.get("/<string:short>")
def goto(short):
    cfg, shorts, obj = my_load_config(obj=short)
    if obj is None:
        return jsonify({"state": "fail",
                        "msg": "short: {short} not in database"})
    if obj.inactive:
        return jsonify({"state": "fail", "msg": "short is inactive!"})

    return redirect(obj.url)

# @TODO, @FIXME: NOT deleting right now...
@rest.get("/prune")
def prune():
    out = []
    cfg, shorts = my_load_config()
    for short, obj in shorts.items():
        if obj is None:
            out.append({"state": "fail", "short": short,
                        "msg": "short: {short} not in db"})
        if obj.inactive:
            out.append({"state": "inactive", "short": short,
                        "msg": "not usable anymore"})

    if len(out) == 0:
        out = {"state": "ok", "msg": "all done, no issues"}
    return jsonify(out)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5005, debug=True)
