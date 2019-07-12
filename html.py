#!/usr/bin/env python

import asyncio
import websockets
import time
import codecs
import json
from socket import gethostbyname, gethostname

class Server:

    SERVER_NAME = "system"
    DEFAULT_ROOM = "main"
    DEFAULT_HISTORY = 100

    def __init__(self, ip="", port=8765, admin="SERVER"):
        self.ip = ip
        if not self.ip:
            # run on current address by default
            self.ip = gethostbyname(gethostname())
        self.port = port
        self.admin = admin

        self.rooms = {}
        self.open(self.DEFAULT_ROOM)
        self.users = {}
        self.service = None

    # start server
    def run(self):
        self.service = websockets.serve(self._connection, self.ip, self.port)
        self.log(f"Server starting at {self.ip}:{self.port}")
        asyncio.get_event_loop().run_until_complete(self.service)
        asyncio.get_event_loop().run_forever()

    @staticmethod
    def log(msg):
        print(f'{time.strftime("%H:%M:%S")} > {str(msg)}')

    @staticmethod
    def validate(data):
        result = {
            "time": time.time()
        }
        for must in ("room", "data"):
            if must not in data:
                raise KeyError(f"payload missing key {must}")
            result[must] = data[must]
        if "cmd" in data:
            result["cmd"] = data["cmd"]
        else:
            result["cmd"] = "msg"
        return result

    async def _connection(self, user, path):
        # connect user
        self.connect(user)
        self.log(f'{self.id(user)} connected')
        try:
            # wait for data from user once the connection is established
            while True:
                try:
                    self.users[user]["updated"] = time.time()
                    message = json.loads(await user.recv())
                    if self.users[user]["nick"]:
                        # look for general messages
                        try:
                            message = self.validate(message)
                        except KeyError as e:
                            self.log(f'Invalid data received from {self.id(user)}: {e}')
                            continue

                        # check payload
                        if message["cmd"] == "join":
                            await self.join(user, message["room"])
                        elif message["cmd"] == "leave":
                            await self.leave(user, message["room"])
                        else:
                            if message["cmd"] in ("msg", ):
                                self.history(message["room"], {"user": self.users[user]["nick"], **message})
                            await self.broadcast(user, message["room"], {"cmd": message["cmd"], "data": message["data"]})

                    else:
                        # look for credentials
                        if "cmd" in message and message["cmd"] == "login":
                            await self.login(user, message)
                        else:
                            await self.system(user, "Please login first.")
                except json.decoder.JSONDecodeError:
                    self.log(f'Invalid data received from {self.id(user)}: malformed JSON')
                    continue

        # disconnect user
        except websockets.ConnectionClosed:
            self.log(f'{self.id(user)} closed connection')
        except websockets.WebSocketProtocolError:
            self.log(f'{self.id(user)} broke protocol')
        except websockets.PayloadTooBig:
            self.log(f'{self.id(user)} generated payload overflow')
        except Exception as e:
            self.log(f'Unknown error for {self.id(user)}: {e}')
        finally:
            self.log(f'{self.id(user)} disconnected')
            try:
                await self.disconnect(user)
            except Exception as e:
                del self.users[user]
                self.log(f'Failed to disconnect: {e}')

    def id(self, user):
        if not self.users[user]["nick"]:
            return f'{self.users[user]["ip"]}'
        return f'{self.users[user]["nick"]} ({self.users[user]["ip"]})'

    # create user data when connection is established
    def connect(self, user, data={}):
        if user in self.users:
            return
        default = {
            "nick": "",
            "level": "user",
            "status": "online",
            "connected": time.time(),
            "updated": time.time(),
            "ip": (user.remote_address[0] if user.remote_address else "0.0.0.0"),
            "rooms": set(),
            "meta": {}
        }
        self.users[user] = {**default, **data}

    # remove user data when connection is closed
    async def disconnect(self, user):
        if user in self.users:
            for room in self.users[user]["rooms"].copy():
                await self.leave(user, room)
            del self.users[user]

    # user sends credentials
    async def login(self, user, payload):
        if user in self.users:
            if "data" in payload and type(payload["data"]) is dict:
                if "user" in payload["data"]:
                    if payload["data"]["user"] != self.admin:
                        # TODO: do actual credential check
                        self.users[user]["nick"] = payload["data"]["user"]
                        self.log(f"{self.id(user)} logged in")
                        await self.system(user, "Access granted.")
                        return
        await self.system(user, "Access denied.")

    # open a new room
    def open(self, room, payload={}):
        if room == self.SERVER_NAME:
            return
        if room in self.rooms:
            return
        default = {
            "history": [],
            "topic": "",
            "welcome": "",
            "created": time.time(),
            "users": set(),
            "nicks": set(),
            "size": self.DEFAULT_HISTORY,
            "blacklist": {
                "ips": {},
                "nicks": {}
            },
        }
        self.rooms[room] = {**default, **payload}

    # close an existing room
    async def close(self, room):
        if room in (self.SERVER_NAME, self.DEFAULT_ROOM):
            return
        if room in self.rooms:
            for user in self.users:
                await self.leave(user, room, True)
            del self.rooms[room]

    # join an existing room
    async def join(self, user, room):
        if user in self.users:
            if not self.users[user]["nick"]:
                await self.system(user, "Please login first.")
                return
            if room not in self.rooms:
                self.open(room)
            if self.users[user]["nick"] in self.rooms[room]["blacklist"]["nicks"]:
                await self.system(user, "User is banned from this room.")
                return
            elif self.users[user]["ip"] in self.rooms[room]["blacklist"]["ips"]:
                await self.system(user, "User is banned from this room.")
                return
            self.users[user]["rooms"].add(room)
            self.rooms[room]["users"].add(user)
            self.rooms[room]["nicks"].add(self.users[user]["nick"])
            # send history to user
            await self.send(user, room, {"cmd": "history", "data": self.history(room)})
            # broadcast to everyone but the user
            await self.broadcast(user, room, {"cmd": "join", "data": ""})

    async def leave(self, user, room, force=False):
        if user in self.users:
            if room in self.rooms:
                self.users[user]["rooms"].discard(room)
                self.rooms[room]["users"].discard(user)
                self.rooms[room]["nicks"].discard(self.users[user]["nick"])
                if len(self.rooms[room]["users"]) == 0:
                    await self.close(room)
                if not force:
                    # broadcast to everyone but the user
                    await self.broadcast(user, room, {"cmd": "leave", "data": ""})
                else:
                    await self.send(user, room, {"cmd": "kick", "data": ""})

    # handle sending messages

    # send payload to user
    async def post(self, user, payload):
        payload["time"] = time.time()
        try:
            await user.send(json.dumps(payload))
        except Exception as e:
            self.log(f"Unable to send to {self.id(user)}: {e}")

    # send to user only
    async def send(self, user, room, payload):
        payload["room"] = room
        payload["user"] = self.users[user]["nick"]
        if "cmd" not in payload:
            payload["cmd"] = "msg"
        await self.post(user, payload)

    # send user's payload to everyone (sometimes to the user as well)
    async def broadcast(self, user, room, payload):
        if room in self.rooms:
            if self.users[user]["nick"]:
                if len(self.rooms[room]["users"]):
                    payload["room"] = room
                    payload["user"] = self.users[user]["nick"]
                    skip_self = False
                    if "cmd" not in payload:
                        payload["cmd"] = "msg"
                    elif payload["cmd"] in ("transform", "join", "leave"):
                        skip_self = True
                    if "data" not in payload:
                        payload["data"] = ""
                    for recipient in self.rooms[room]["users"]:
                        if skip_self and recipient == user:
                            continue
                        await self.post(recipient, payload)

    # send system message directly to user (NOTE: takes msg data instead of payload)
    async def system(self, user, data):
        payload = {
            "room": self.SERVER_NAME,
            "user": self.admin,
            "cmd": "msg",
            "data": data
        }
        await self.post(user, payload)

    # broadcast to room by system
    async def system_broadcast(self, room, data):
        if room in self.rooms:
            if len(self.rooms[room]["users"]):
                payload = {
                    "room": room,
                    "user": self.admin,
                    "cmd": "msg",
                    "data": data
                }
                for recipient in self.rooms[room]["users"]:
                    await self.post(recipient, payload)

    def history(self, room, payload=None):
        if room in self.rooms:
            if payload is not None:
                self.rooms[room]["history"].append(payload)
                self.rooms[room]["history"] = self.rooms[room]["history"][-self.rooms[room]["size"]:]
            return self.rooms[room]["history"]
        else:
            return []


if __name__ == "__main__":
    server = Server()
    server.run()
