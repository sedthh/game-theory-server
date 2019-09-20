Basic IRC-like chat server for VR headsets. 

# Running server
The server requires Python 3.7+ to run. It also requires the following libraries:

```pythom
pip install websockets
pip install asyncio
```

To run the server, either run **server.py** or import it and run the Server() class:
```python
import server

# all settings are optional, default value for server IP is your own 
backend = Server(ip="192.168.1.1", port=42069, fps=1, log_level=3)
backend.run()
```

# Sending messages
There are 2 kinds of messages that a client can send to the server:
* Login messages sent directly to the server (NOTE: authentication is not yet implemented)
```python
# log in using a username and password, after connecting to the server
# user will automatically join the room "lobby" after logging int
{"system": "login", "options": {"user": "Tibi", "pass": "1234"}}

# ping server
{"system": "ping"}

# list rooms on server (users can open more rooms)
{"system": "rooms"}
```          
            
* Messages sent to the participants of a certain room (can only be sent after logging in)
```python
# join a room (user can join multiple rooms at the same time)
{"room": "private_room_1", "type": "join", "data": ""}

# leave a room (user will automatically leave all rooms when disconnected)
{"room": "private_room_1", "type": "leave", "data": ""}

# list all users in the room (this is sent automatically when joining)
{"room": "lobby", "type": "list", "data": ""}

# send message in room
{"room": "lobby", "type": "msg", "data": "hello"}

# send headset position in room
{"room": "lobby", "type": "transform", "data": {
    "pos": {
        "x": 7.0,
        "y": 8.0,
        "z": 9.0
    },
    "rot": {
        "x": 4.0,
        "y": 5.0,
        "z": 6.0
    }
}}
```

As you can see, the contents of both "options" and "data" can vary based on context.

# Receiving messages from server
There are also 2 kinds of messages that a server can send to the client:
* System info and error messages ("info": "system" and "info": "error")
``` python
# information on authentication, etc.  (code from 200 to 300)
{'info': 'system', 'response': {'time': 1568979503.2808492, 'code': 202, 'msg': 'Access granted.', 'detail': {}}}

# errors (code from 400 to 600)
{'info': 'error', 'response': {'time': 1568979503.2798524, 'code': 403, 'msg': 'Access denied.', 'detail': {}}}
```

* Messages sent by other users to the room the user has joined. ("info": "user") 
NOTE: here multiple messages may be sent at the same time as one JSON! The "payload" variable is an array of objects!
``` python
# a user has joined the room
{'info': 'user', 'room': 'lobby', 'payload': [{'time': 1568979503.2808492, 'user': 'Tibi', 'type': 'join', 'data': ''}]}

# a user has left the room
{'info': 'user', 'room': 'lobby', 'payload': [{'time': 1568979503.2808492, 'user': 'Tibi', 'type': 'leave', 'data': ''}]}

# user has sent a message 
{'info': 'user', 'room': 'lobby', 'payload': [{'time': 1568979503.2828438, 'user': 'Tibi', 'type': 'msg', 'data': 'hello'}]}

# user has sent their headset position (this is only broadcasted at certain intervals, based on "fps")
{'info': 'user', 'room': 'lobby', 'payload': [{'time': 1568979503.8257432, 'user': 'Tibi', 'type': 'transform', 'data': {'pos': {'x': 0.0, 'y': 0.0, 'z': 0.0}, 'rot': {'x': 0.0, 'y': 0.0, 'z': 0.0}}}]}

```

The "payload" variable is an array of objects. When a user joins a room, the room's history will be sent to them as a list of previous messages. 

To minimize overhead, the headset positions are only updated at regular intervals, based on the "fps" settings, no matter how many time a user actually sends their position.

Time is always based on server time.  