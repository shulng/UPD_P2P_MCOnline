# MC打洞联机

本项目用于实现 **Minecraft 联机打洞穿透**，通过 P2P 技术实现 NAT 穿透，客户端和服务端通过配置对应端口和 UUID 建立连接。

---

## 📂 项目结构

- `p2p_server22.py` —— 打洞服务端脚本,启动以打洞,部署在公网服务器上  
- `p2p_client_s.py` —— 客户端配置文件  
- `p2p_client.py` —— 客户端配置文件  
- `服务端代理.py` —— 运行后会生成 `UUID` 并监听本地服务器端mc的默认25565端口,端口可自行修改
- `客户端代理.py`  —— 客户端本地代理，修改对应 `UUID` 启动即可连接打洞,默认监听25566端口,可在mc多人游戏输入0.0.0.0:25566联机

---

## ⚙️ 服务端配置（p2p_server22.py）

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
---

## ⚙️ 客户端配置1（p2p_client_s.py）

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

---

##  ⚙️ 客户端配置2（p2p_client.py）

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

---

🔑 代理配置
服务端代理（服务端代理.py）

运行后会生成一个 UUID，客户端需要使用此 UUID 进行连接。

客户端代理（客户端代理.py 或 local_proxy.py）

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

# 在此处修改 UUID 为服务端提供的 UUID
p2pExample = p2p_client.Run(UUID("d1585c38-8f6f-4ff6-96ee-97eb3b413619")) #修改这里

---

👉 注意：

UUID 需要替换为服务端生成的真实值。

确保客户端和服务端端口一致，否则无法打洞成功。
