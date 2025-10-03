import traceback
from socket import *
from threading import *
import json
import time
import struct
from uuid import UUID

HEADER_FMT=">B16s16s?"
TYPE_P2P=0x10
TYPE_CLOSE=0x03
TYPE_LOGOUT=0x07
TYPE_GET_UUID=0x09

# 打洞范围
COUNT = 500

# 探测包或会话保持包
Detection = "okgo"

# 网络信息
SERVER_IP = "penxia.dpdns.org"
SERVER_PORT = 3336


class Run:
    def __init__(self,uuid):
        self.uuid=uuid
        self.sign=False
        self.info = {}
        self.yes = False #打洞是否成功
        self.gogogo_thread_count = 0

        self.server_session_thread = None
        self.client_session_thread=None
        self._gogogo_lock = Lock()
        self.gogogo_thread_list = []
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.sock.setsockopt(SOL_SOCKET, SO_RCVBUF, 1<<20)
        self.sock.bind(("", 0))
        self.uuid_init()
        self.signup_server()
        self.waken_thread=Thread(target=self.waken)
        self.waken_thread.start()


    def uuid_init(self):
        if self.uuid:
            print(f"uuid已设置:{self.uuid}")
            return
        while True:
            self.sock.sendto(struct.pack(HEADER_FMT, TYPE_GET_UUID, b"", b"", False), (SERVER_IP, SERVER_PORT))
            try:
                data, addr = self.sock.recvfrom(1024)
            except:
                time.sleep(1)
                continue
            self.uuid = UUID(bytes=data)
            print(f"uuid初始化:{self.uuid}")
            break


    def signup_server(self):
        print("开始注册")
        self.sock.setblocking(False)  # 非阻塞模式
        while True:
            self.sock.sendto(struct.pack(HEADER_FMT,TYPE_P2P,self.uuid.bytes,b"",True),(SERVER_IP,SERVER_PORT))
            time.sleep(0.5)
            try:
                data,addr=self.sock.recvfrom(1024)
            except Exception:
                print("注册失败,开始重试")
                self.sock.setblocking(True)
                continue
            tcpport=eval(data.decode("utf-8"))
            self.tcp=socket(AF_INET, SOCK_STREAM)
            self.tcp.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            try:
                self.tcp.connect_ex((SERVER_IP,tcpport))
            except Exception:
                self.sock.sendto(struct.pack(HEADER_FMT,TYPE_LOGOUT,self.uuid.bytes,b"",False), (SERVER_IP,SERVER_PORT))
                print("注册失败,端口:"+tcpport+"错误")
                continue
            print("注册成功")
            self.sock.setblocking(True)
            break


    def resignup_server(self,data):
        print("重新注册")
        tcpport = eval(data.decode("utf-8"))
        self.tcp = socket(AF_INET, SOCK_STREAM)
        self.tcp.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        try:
            self.tcp.connect_ex((SERVER_IP, tcpport))
        except Exception:
            traceback.print_exc()
            self.sock.sendto(struct.pack(HEADER_FMT, TYPE_LOGOUT, self.uuid.bytes, b"", False),(SERVER_IP, SERVER_PORT))
            print("注册失败,端口:" + tcpport + "错误")
            self.sock.sendto(struct.pack(HEADER_FMT, TYPE_P2P, self.uuid.bytes, b"", True), (SERVER_IP, SERVER_PORT))
            return
        print("注册成功")


    def waken(self):
        while True:
            time.sleep(1)
            try:
                self.tcp.settimeout(120) #发现tcp连接会莫名其妙断开而不知,设置重注册机制刷新连接
                data=self.tcp.recv(1024)
                if len(data)>3:
                    uuid=UUID(bytes=data)
                    print(f"{uuid} 发起打洞")
                    self.yes=False
                    self.sock.sendto(struct.pack(HEADER_FMT,TYPE_P2P,self.uuid.bytes,uuid.bytes,False), (SERVER_IP, SERVER_PORT)) #及时回复
                    Thread(target=self.server_session,args=(uuid,)).start()
                elif data==b"":
                    self.sock.sendto(struct.pack(HEADER_FMT, TYPE_P2P, self.uuid.bytes, b"", True),(SERVER_IP, SERVER_PORT))  # 发起新注册,回应会通过处理mc数据的recvfrom处理
                    try:
                        self.tcp.close()
                    except:pass
                    time.sleep(3)
            except:
                self.sock.sendto(struct.pack(HEADER_FMT, TYPE_P2P, self.uuid.bytes, b"", True),(SERVER_IP, SERVER_PORT))  # 发起新注册,回应会通过处理mc数据的recvfrom处理
                time.sleep(3)


    def server_session(self,uuid):
        while not self.yes:
            self.sock.sendto(struct.pack(HEADER_FMT,TYPE_P2P,self.uuid.bytes,uuid.bytes,False), (SERVER_IP, SERVER_PORT))
            time.sleep(1)  # 向服务器发送维持包
        self.sock.sendto(struct.pack(HEADER_FMT, TYPE_CLOSE, self.uuid.bytes, uuid.bytes, False),(SERVER_IP, SERVER_PORT))
        print("打洞成功")


    def recv_handle(self,data,addr):
        if not self.yes:
            try:
                data = data.decode("utf-8")
            except Exception:
                traceback.print_exc()
                return
            header=data.split("&")[0]
            uuid=UUID(data.split("&")[1])
            if header == "server_ok":  # 服务器消息头,对端数据交换
                try:
                    info = json.loads(data.split("&")[2])
                except Exception:
                    traceback.print_exc()
                    return
                if self.gogogo_thread_count >= 5:  #控制打洞线程数量
                    # 更新对方客户端信息
                    self.info[uuid] = info

                elif self.gogogo_thread_count < 5:
                    # 更新对方客户端信息
                    self.info[uuid] = info
                    # 创建端口轰炸线程
                    t = Thread(target=self.gogogo,args=(uuid,))
                    with self._gogogo_lock:
                        self.gogogo_thread_list.append(t)
                    t.start()

            elif header == Detection:
                self.info[uuid]={ "ip": addr[0], "port": addr[1]}
                self.sock.sendto(f"{Detection}&{self.uuid}&".encode("utf-8"), addr)
                self.yes=True


    def gogogo(self,uuid):
        print(f"gogogo{self.gogogo_thread_count}")
        try:
            self.gogogo_thread_count += 1  # 开始一个线程数量＋1
            for i in range(COUNT):
                time.sleep(0.006)
                if self.yes:
                    break
                self.sock.sendto(f"{Detection}&{self.uuid}&".encode("utf-8"), (self.info[uuid]["ip"], self.info[uuid]["port"] + i))
        finally:
            # 无论如何都要安全地更新状态和移除线程引用
            with self._gogogo_lock:
                self.gogogo_thread_count -= 1
                # 按对象移除，而不是 pop(0)
                try:
                    self.gogogo_thread_list.remove(current_thread())
                except:pass
