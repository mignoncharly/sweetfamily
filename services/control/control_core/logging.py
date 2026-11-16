import json
import logging


class SafeFormatter(logging.Formatter):
    def format(self, record):
        # Never serialize arbitrary messages, args, exceptions or request bodies.
        return json.dumps({"level": record.levelname, "event": "application_log"})
