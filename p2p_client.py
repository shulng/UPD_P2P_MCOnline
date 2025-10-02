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
TYPE_GET_UUID=0x09

# 打洞范围
COUNT = 500

# 探测包或会话保持包
Detection = "okgo"

# 网络信息
SERVER_IP = "penxia.dpdns.org"
SERVER_PORT = 3336


class Run:
    def __init__(self,s_uuid):
        self.s_uuid = s_uuid #对端uuid
        self.info = { #对端信息
            "uuid": "",  #多余,但不着急管,空闲再重构
            "ip": "",
            "port": -1
        }
        self.uuid = None #自己的uuid
        self.yes = False #打洞是否成功
        #打洞管理
        self.gogogo_thread_count = 0
        self.gogogo_thread_list = []
        self._gogogo_lock = Lock()

        self.recv_handle_thread = None #处理打洞的线程
        self.server_session_thread = None #请求交换信息的线程
        self.client_session_thread=None #心跳
        #套接字
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.sock.setsockopt(SOL_SOCKET, SO_RCVBUF, 1<<20)
        self.sock.bind(("", 0))

        self.uuid_init()#uuid初始化
        #启动工作线程
        self.server_session_thread = Thread(target=self.server_session,daemon=True)
        self.recv_handle_thread = Thread(target=self.recv_handle,daemon=True)
        self.server_session_thread.start()
        self.recv_handle_thread.start()
        self.recv_handle_thread.join() #这个线程结束就说明打洞完成或失败了


    def uuid_init(self):
        print("uuid_init")
        while True:
            self.sock.sendto(struct.pack(HEADER_FMT, TYPE_GET_UUID, b"", b"", False), (SERVER_IP, SERVER_PORT)) #uuid可以在本地创建,但当时脑抽让去服务器要了
            try:
                data, addr = self.sock.recvfrom(1024)
            except:
                time.sleep(1)
                continue
            self.uuid = UUID(bytes=data)
            print(self.uuid)
            break


    def server_session(self):
        print("server_session")
        while not self.yes: #打洞完成不再请求
            self.sock.sendto(struct.pack(HEADER_FMT,TYPE_P2P,self.uuid.bytes,self.s_uuid.bytes,False), (SERVER_IP, SERVER_PORT))
            time.sleep(1)
        self.sock.sendto(struct.pack(HEADER_FMT, TYPE_CLOSE, self.uuid.bytes, self.s_uuid.bytes, False),(SERVER_IP, SERVER_PORT))
        time.sleep(0.1)
        self.sock.sendto(struct.pack(HEADER_FMT, TYPE_CLOSE, self.uuid.bytes, self.s_uuid.bytes, False),(SERVER_IP, SERVER_PORT)) #暂时解决丢包问题,但不完全
        print("打洞成功")


    def recv_handle(self):
        print("recv_handle")
        while not self.yes:
            try:
                self.sock.setblocking(True)
                data, addr = self.sock.recvfrom(1024)
                data = data.decode("utf-8")
                if data=="no": #服务器找不到打洞对象的注册会返回
                    print("打洞失败")
                    quit()
                header = data.split("&")[0]
                uuid = UUID(data.split("&")[1])
                if header == Detection:  # 探测头,表示对方客户端找到你了
                    self.info["uuid"] = uuid
                    self.info["ip"] = addr[0]
                    self.info["port"] = addr[1]
                    header = struct.pack(">BIIHH16s", TYPE_P2P, 0, 0, 0, 0 ,self.uuid.bytes) #这里是因为服务端需要持续接受打洞,共用recvfrom需要格式化头,有机会会想办法
                    chunk = f"{Detection}&{self.uuid}&".encode("utf-8")
                    pkt = header + chunk
                    self.sock.sendto(pkt, addr)#及时回应对方客户端,让对方知道打洞成功
                    self.yes = True #打洞成功状态
                    self.client_session_thread = Thread(target=self.client_session) #心跳线程
                    self.client_session_thread.start()
                    time.sleep(0.5)
                    self.clear_udp_buffer() #清理延迟到的包

                elif header == "server_ok":  # 服务器消息头,对端数据交换
                    if data.split("&")[2]=="{}": #第一次请求,对端还来不及响应,会回个空的
                        continue
                    try:
                        info = json.loads(data.split("&")[2])
                    except:
                        continue
                    d={"uuid":uuid,"ip":info["ip"],"port":info["port"]}
                    if self.gogogo_thread_count >= 5:  #控制打洞线程数量
                        # 更新对方客户端信息
                        self.info = d

                    elif self.gogogo_thread_count < 5:
                        # 更新对方客户端信息
                        self.info = d
                        # 创建端口轰炸线程
                        t = Thread(target=self.gogogo)
                        with self._gogogo_lock:
                            self.gogogo_thread_list.append(t)
                        t.start()
            except Exception as e:
                traceback.print_exc()


    def client_session(self):
        while True:
            self.sock.sendto(Detection.encode("utf-8"), (self.info["ip"], self.info["port"]))
            time.sleep(9)


    def gogogo(self):
        print(f"gogogo{self.gogogo_thread_count}")
        try:
            self.gogogo_thread_count += 1  # 开始一个线程数量＋1
            for i in range(COUNT):
                time.sleep(0.006)
                if self.yes:
                    break
                header=struct.pack(">BIIHH16s",TYPE_P2P,0,0,0,0,self.uuid.bytes)
                chunk=f"{Detection}&{self.uuid}&".encode("utf-8")
                pkt=header+chunk
                self.sock.sendto(pkt, (self.info["ip"], self.info["port"] + i))
        finally:
            # 无论如何都要安全地更新状态和移除线程引用
            with self._gogogo_lock:
                self.gogogo_thread_count -= 1
                try:
                    self.gogogo_thread_list.remove(current_thread())
                except:pass


    def clear_udp_buffer(self):
        self.sock.setblocking(False)  # 非阻塞模式
        try:
            while True:
                self.sock.recvfrom(65535)  # 把所有缓存里的包读出来丢掉
        except BlockingIOError:
            pass  # 没包可读就跳出
        finally:
            self.sock.setblocking(True)  # 记得恢复阻塞模式