
import json, os, shutil
from datetime import datetime

DATA_FILE='data/students.json'
COURSE_FILE='data/courses.json'

def load_json(path):
    if os.path.exists(path):
        with open(path,'r') as f:
            return json.load(f)
    return []

def save_json(path,data):
    with open(path,'w') as f:
        json.dump(data,f,indent=4)

def backup():
    if os.path.exists(DATA_FILE):
        name=f"data/backup/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy(DATA_FILE,name)
        return name
