import os
import sys
import yaml

def load_config(config_path):
    """load config in given 'config_path', on any error fail critical & exit!"""
    if not os.path.exists(config_path):
        print("config path: {config_path} not found, exiting...")
        sys.exit(1)
    cfg = yaml.safe_load(open(config_path))

   #if "file_destination" not in cfg:
   #    print("you must set 'file_destintion' to a writable path (dir), exiting...")
   #    sys.exit(1)

   #if not os.path.exists(cfg["file_destination"]) \
   #  or not os.path.isdir(cfg["file_destination"]):
   #    print ("your 'file_destination' is not existing or not r/w/x + (dir)")
   #    # @todo: writeable check missing...
   #    sys.exit(1)

    if not "secret_key" in cfg:
        print ("'secret_key' missing in configuration, exiting...")
        sys.exit(1)

    if not "user" in cfg or not "pwd" in cfg:
        print ("no 'user' and 'pwd' provided in configuration, exiting...")
        sys.exit(1)

    return cfg




def save_config(cfg, config_path):
    with open(config_path, "w") as fd:
        yaml.safe_dump(cfg, fd)




