#passenger_wsgi.py
import os
import sys
import importlib.util

sys.path.insert(0, os.path.dirname(__file__))

# Load manager.py dynamically
spec = importlib.util.spec_from_file_location('wsgi', 'manager.py')
wsgi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wsgi)
application = wsgi.app2