import requests

r = requests.get("http://henry.cutler.is/nursery/server.py", auth=("rpi", "HenryIsGreat"))
print(r.json())
