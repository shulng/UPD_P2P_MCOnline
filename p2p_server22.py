from socket import *
import json
import time
from threading import Thread
from uuid import uuid4,UUID
import struct
import traceback

TYPE_P2P=0x10
TYPE_CLOSE=0x03
TYPE_LOGOUT=0x07
TYPE_GET_UUID=0x09

HEADER_FMT=">B16s16s?"

def gen_uuid():
    return uuid4()

server_conn={}
conn_count=0

class Server:
    def __init__(self):
        self.session_count = 0
        self.IP = "0.0.0.0"
        self.PORT = 3336
        self.client1 = {
            "uuid": "",
            "ip": "",
            "port": -1
        }
        self.client2 = {
            "uuid": "",
            "ip": "",
            "port": -1
        }
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.sock.bind((self.IP, self.PORT))
        print("服务器启动")
        self.run()

    def run(self):
        global conn_count
        while True:
            try:
                data, addr = self.sock.recvfrom(1024)
            except:
                traceback.print_exc()
                continue
            t,u1,u2,f= struct.unpack(HEADER_FMT, data) #请求类型,自己uuid,要找uuid,是否注册
            u1=UUID(bytes=u1)
            u2=UUID(bytes=u2)
            if t==TYPE_CLOSE: #打洞完毕,清除会话
                self.client1={}
                self.client2={}
                self.session_count=0
                print("清除会话")
                time.sleep(0.5)
                self.clear_udp_buffer()
                continue
            elif t==TYPE_P2P: #P2P类请求
                if f: #注册新服务端槽位,仅注册
                    print(f"{u1}注册请求")
                    conn_count+=1
                    s=socket(AF_INET, SOCK_STREAM)
                    s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                    s.bind((self.IP, self.PORT+conn_count))
                    s.listen(1)
                    Thread(target=self.sign,args=(u1,s)).start()
                    Thread(target=self.logout_timeout,args=(u1,)).start()
                    self.sock.sendto(f"{self.PORT+conn_count}".encode("utf-8"), addr)

                elif self.session_count==0: #没有人打洞,可以使用
                    print(f"{u1}向请求打洞{u2}")
                    self.session_count=1
                    self.client1["uuid"]=u1
                    self.client1["ip"] = addr[0]
                    self.client1["port"] = addr[1]
                    if u2 in server_conn.keys(): #服务端存在,唤醒服务端
                        print("尝试唤醒")
                        server_conn[u2].send(u1.bytes)
                        self.sock.sendto(f"server_ok&{u2}&{'{}'}".encode("utf-8"), addr)
                        Thread(target=self.clear_session_timeout).start()
                    else: #服务端不存在,不打洞
                        print("请求的服务端不存在")
                        self.sock.sendto("no".encode("utf-8"), addr)
                        self.client1 = {}
                        self.session_count = 0
                        continue

                elif self.session_count == 1: #等待另一个人
                    if self.client1["uuid"] == u1: #是会话1自己,不做操作
                        self.sock.sendto(f"server_ok&{u2}&{'{}'}".encode("utf-8"), addr)
                        print("是会话1自己,不做操作")
                    elif self.client1["uuid"] == u2: #服务端找会话1,回应
                        print("服务端找会话1")
                        self.client2["uuid"] = u1
                        self.client2["ip"] = addr[0]
                        self.client2["port"] = addr[1]
                        d=json.dumps({"ip":self.client1["ip"],"port":self.client1["port"]})
                        uuid=self.client1["uuid"]
                        self.sock.sendto(f"server_ok&{uuid}&{d}".encode("utf-8"), addr)
                        self.session_count = 2
                elif self.session_count==2: #两个会话已开始工作,外人勿进
                    print("会话1的请求,回应会话2的信息")
                    if u1==self.client1["uuid"]: #会话1的请求,回应(会话2信息)
                        self.client1["port"] = addr[1]
                        d = json.dumps({ "ip": self.client2["ip"], "port": self.client2["port"]})
                        uuid=self.client2["uuid"]
                        self.sock.sendto(f"server_ok&{uuid}&{d}".encode("utf-8"), addr)
                    elif u1==self.client2["uuid"]: #会话2的请求,回应(会话1信息)
                        print("会话2的请求,回应会话1的信息")
                        self.client2["port"] = addr[1]
                        d = json.dumps({"ip": self.client1["ip"], "port": self.client1["port"]})
                        uuid=self.client1["uuid"]
                        header = struct.pack(">BIIHH16s", TYPE_P2P, 0, 0, 0, 0 ,u1.bytes)
                        chunk=f"server_ok&{uuid}&{d}".encode("utf-8")
                        pkt=header+chunk
                        self.sock.sendto(pkt, addr)

            elif t==TYPE_LOGOUT: #服务端注销请求
                try:
                    tcp = server_conn[u1]
                    tcp.close()
                    del server_conn[u1]
                except:pass
                conn_count-=1
                print(f"服务{u1}注销")

            elif t==TYPE_GET_UUID: #获取uuid
                self.sock.sendto(gen_uuid().bytes, addr)
                print(addr,"请求uuid")


    def sign(self,uuid,sock): #注册功能
        s,addr=sock.accept()
        server_conn[uuid] = s
        print(f"服务{uuid}注册成功")


    def clear_udp_buffer(self):
        self.sock.setblocking(False)  # 非阻塞模式
        try:
            while True:
                self.sock.recvfrom(65535)  # 把所有缓存里的包读出来丢掉
        except BlockingIOError:
            pass  # 没包可读就跳出
        finally:
            self.sock.setblocking(True)  # 记得恢复阻塞模式


    def clear_session_timeout(self):
        time.sleep(20)
        print("会话清理")
        s=socket(AF_INET,SOCK_DGRAM)
        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 3340))
        s.sendto(struct.pack(HEADER_FMT, TYPE_CLOSE, b"", b"", False),("127.0.0.1", 3336))


    def logout_timeout(self,uuid):
        time.sleep(60)
        s = socket(AF_INET, SOCK_DGRAM)
        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 3341))
        s.sendto(struct.pack(HEADER_FMT, TYPE_LOGOUT, uuid.bytes, b"", False), ("127.0.0.1", 3336))  # 暂时解决丢包问题,但不完全


if __name__ == "__main__":
    server= Server()
    print("服务器停止运行")


