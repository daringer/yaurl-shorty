import sys
import os
from functools import wraps

import hashlib
import mimetypes

from flask import Flask, render_template, request, flash, redirect, Response, url_for, send_file
from flask import Blueprint, jsonify, abort

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from werkzeug.utils import secure_filename

from urllib.parse import quote, urlparse, urlencode
from uuid import uuid4 as create_uid
from time import time as now
from datetime import timedelta as td
from copy import copy as cpy

import yaml

from mmpy import get_rest_decorator

# where to find the .yaml config file
YAML_CFG_PATH = sys.argv[1]

# not used currently
DEFAULT_TTL = 60 * 60 * 24 * 30


# @TODO: set server_name if needed?!?!

###
### yaml helper
###

def my_save_config(cfg, config_path=YAML_CFG_PATH):
    cfg["shorts"] = dict((short, dict(obj)) \
        for short, obj in cfg["shorts"].items())
    with open(config_path, "w") as fd:
        yaml.safe_dump(cfg, fd)
    return True

def my_load_config(config_path=YAML_CFG_PATH, obj=None):
    if not os.path.exists(config_path):
        print("config path: {config_path} not found, exiting...")
        sys.exit(1)
    cfg = yaml.safe_load(open(config_path))

    if not "secret_key" in cfg:
        print ("'secret_key' missing in configuration, exiting...")
        sys.exit(1)

    if "shorts" not in cfg or not isinstance(cfg["shorts"], dict):
      cfg["shorts"] = {}

    for short in cfg["shorts"]:
        cfg["shorts"][short] = Short(cfg["shorts"].get(short, {}))

    if obj is None:
        return cfg, cfg["shorts"]
    else:
        return cfg, cfg["shorts"], (obj and cfg["shorts"].get(obj, None))

pre_cfg, _ = my_load_config()

# length of auto-generated short-url
MAX_UUID_LEN = pre_cfg.get("max_url_len", 6)

# flask init
app = Flask(__name__)
app.secret_key = pre_cfg.get("secret_key", "123456")

limiter = Limiter(app,
    key_func=get_remote_address,
    default_limits=pre_cfg.get("limits", ["100 per day", "10 per hour"])
)

####
#### short-class
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

####
#### endpoints
####

rest = get_rest_decorator(app)
forbidden_shorts = {"gen", "short", "test"}

@rest.get("/<string:short>/gen/<path:url>")
def create_with_short(url, ttl=DEFAULT_TTL, short=None):
    return create(url, ttl, short)

@rest.get("/gen/<path:url>")
def create(url, ttl=DEFAULT_TTL, short=None):

    if len(request.args) > 0:
        url += "?" + urlencode(request.args)

    # @TODO: validate url @FIXME, more more more
    if not "." in url or not url.startswith("http"):
        #return jsonify(state="fail", url=url,
        #    msg=f"cannot gen short, not a valid url: '{url}'")
        abort(404)

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

    if short in forbidden_shorts:
        #return jsonify(state="fail", url=url,
        #               msg=f"short: {short} not allowed (reserved word)")
        abort(409)

    if short not in shorts:
        cfg["shorts"][short] = {"short": short,
          "url": url, "ttl": ttl, "created": int(now())}

        my_save_config(cfg)

        return jsonify(state="ok", url=url, ttl=ttl,
                       msg=f"new short-url: '{url}' as '{short}'",
                       short_url=url_for("goto", short=short, _external=True))

    abort(409)
    #return jsonify(state="fail", url=url,
    #               msg=f"cannot gen short: '{short}' (already taken...)")

#@rest.get("/test/<path:url>")
#def has_short(url):
#    if len(request.args) > 0:
#        url += "?" + urlencode(request.args)
#    cfg, shorts = my_load_config()
#    for short, obj in shorts.items():
#        if obj.url == url:
#            return jsonify({"state": "ok", **obj.info})
#    return jsonify({"state": "fail", "msg": f"url: '{url}' no short found"})

@rest.get("/<string:short>")
def goto(short):
    cfg, shorts, obj = my_load_config(obj=short)
    if obj is None:
        #return jsonify({"state": "fail",
        #                "msg": f"short: '{short}' not in database"})
        abort(404)

    #if obj.inactive:
    #    return jsonify({"state": "fail", "msg": "short is inactive!"})
    return redirect(obj.url)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5005, debug=True)
