import json
import sys

sys.path.insert(0, ".")
from work import count

assert count(json.load(open("fixtures/records.json"))) == 2
