# MC打洞联机

本项目用于实现 **Minecraft 打洞联机**，通过 P2P 技术实现 NAT 穿透，客户端和服务端通过配置对应端口和 UUID 建立连接。

---

## 📂 项目文件

- `p2p_server.py` —— 打洞服务端脚本,部署在公网服务器上  **启动文件**
- `p2p_client_s.py` —— MC服务端代理的打洞功能文件  
- `p2p_client.py` —— MC客户端代理的打洞功能文件  
- `服务端代理.py` —— 并代理本地服务器端mc的默认25565端口,端口可自行修改 **启动文件**
- `客户端代理.py`  —— 客户端本地代理,运行前修改对应 `UUID` 启动即可连接打洞,默认监听25566端口,可在mc多人游戏输入0.0.0.0:25566联机 **启动文件**

---

## ⚙️ 打洞服务端（p2p_server.py）

```python
from socket import *
import json
import time
from threading import Thread
from uuid import uuid4, UUID
import struct
import traceback

# 数据包类型
TYPE_P2P = 0x10
TYPE_CLOSE = 0x03
TYPE_LOGOUT = 0x07
TYPE_GET_UUID = 0x09

HEADER_FMT = ">B16s16s?"

def gen_uuid():
    return uuid4()

server_conn = {}
conn_count = 0

class Server:
    def __init__(self):
        self.session_count = 0
        self.IP = "0.0.0.0"
        self.PORT = 3336   # 打洞服务器监听端口,修改这里
```
```bash
python3 p2p_server.py
```

---

## ⚙️ MC服务端代理的打洞功能文件（p2p_client_s.py）

```python
import traceback
from socket import *
from threading import *
import json
import time
import struct
from uuid import UUID

HEADER_FMT = ">B16s16s?"
TYPE_P2P = 0x10
TYPE_CLOSE = 0x03
TYPE_LOGOUT = 0x07
TYPE_GET_UUID = 0x09

# 打洞范围
COUNT = 500

# 探测包/会话保持包
Detection = "okgo"

# 网络信息
SERVER_IP = "penxia.dpdns.org"
SERVER_PORT = 3336   # 必须与服务端一致,修改这里
```

---

##  ⚙️ MC客户端代理的打洞功能文件（p2p_client.py）
```python
import traceback
from socket import *
from threading import *
import json
import time
import struct
from uuid import UUID

HEADER_FMT = ">B16s16s?"
TYPE_P2P = 0x10
TYPE_CLOSE = 0x03
TYPE_GET_UUID = 0x09

# 打洞范围
COUNT = 500

# 探测包/会话保持包
Detection = "okgo"

# 网络信息
SERVER_IP = "penxia.dpdns.org"
SERVER_PORT = 3336   # 与服务端端口一致,修改这里
```

---

# 🔑 代理配置
## 服务端代理（服务端代理.py）
```python
# relay.py
import time
from collections import OrderedDict
import socket
import threading
import struct
import traceback
from uuid import UUID
import p2p_client_s

Detection=p2p_client_s.Detection.encode("utf-8")
p2pExample=p2p_client_s.Run(UUID("60273221-458b-45be-9cb4-85f8db047c51")) #设置uuid

# 配置（按需修改）
MC_SERVER_ADDR = ('127.0.0.1', 25565)  # 真实 Minecraft 服务器地址,修改这里代理不同服务器端口
```
```cmd
# 与p2p_client_s.py同级目录
python 服务端代理.py
```

---

## 客户端代理（客户端代理.py）

```python
from collections import OrderedDict
import socket
import threading
import struct
import time
import traceback
from uuid import UUID, uuid4
import p2p_client

Detection = p2p_client.Detection.encode("utf-8")

# 在此处修改 UUID 为服务端代理提供的 UUID
p2pExample = p2p_client.Run(UUID("d1585c38-8f6f-4ff6-96ee-97eb3b413619")) #填入和服务端代理.py相同的uuid

# 配置（按需修改）
LOCAL_TCP_BIND = ('0.0.0.0', 25566)   # Minecraft 客户端连到这里
```
```cmd
# 与p2p_client.py同级目录
python 客户端代理.py
```

---

## 👉 注意：

# 默认ip是我的服务器,虽然可以随便用,但可能随时跑路,有条件9.9自己买个还能干其他事
