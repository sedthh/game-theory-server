#!/usr/bin/env python

import asyncio
import websockets
import json


async def hello():
    async with websockets.connect(f'ws://192.168.0.241:42069') as ws:
        msg = [
            {"room": "lobby", "cmd": "msg", "data": "this will fail because I am not logged in"},
            {"system": "login", "options": {"user": "Tibi", "pass": "1234"}},
            {"system": "ping"},
            {"room": "test", "cmd": "join", "data": ""},
            {"system": "rooms"},
            {"room": "lobby", "cmd": "msg", "data": "hello"},
            {"room": "lobby", "cmd": "transform", "data": {
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
            }},
            {"room": "lobby", "cmd": "msg", "data": "hello again"},
            {"room": "lobby", "cmd": "leave", "data": ""},
            {"room": "lobby", "cmd": "msg", "data": "this will also fail"},
        ]
        for m in msg:
            await ws.send(json.dumps(m))
            print(json.loads(await ws.recv()))
        await ws.send(json.dumps(m))
        print(json.loads(await ws.recv()))
        await ws.send(json.dumps(m))
        print(json.loads(await ws.recv()))

asyncio.get_event_loop().run_until_complete(hello())


