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
p2pExample=p2p_client_s.Run(UUID("60273221-458b-45be-9cb4-85f8db0d7c51"))

# 配置（按需修改）
MC_SERVER_ADDR = ('127.0.0.1', 25565)  # 真实 Minecraft 服务器地址

HEADER_FMT = ">BIIHH16s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
TYPE_MC = 0x01
TYPE_ACK   = 0x02
TYPE_CLOSE = 0x05
TYPE_P2P=0x10

MAX_PAYLOAD = 15000 # 保守一点，避免超过UDP上限
conns = {}
pending   = {}
fragments = {} #标记,只增不减,短时间内存泄漏不重不影响使用,后续再做处理
msg_id_s={}
completed_msgs = OrderedDict()
conns_lock = threading.Lock()
msg_lock = threading.Lock()

def send_fragmented(conn_id, data,addr,uuid):
    """分片并发送，每个分片要求 ACK，超时重发"""
    with msg_lock:
        msg_id = msg_id_s[(conn_id,uuid)]
        msg_id_s[(conn_id,uuid)]= msg_id+1
    total = (len(data) + MAX_PAYLOAD - 1) // MAX_PAYLOAD
    t=0 #MC/tp命令的优化,tp会发一个很大的包需要延时发送,提升不大但推荐用上
    if total >11:
        t=0.018
        # t=0.025 #最慢,但最大限度避免重发
    for seq in range(total):
        time.sleep(t)
        chunk = data[seq*MAX_PAYLOAD:(seq+1)*MAX_PAYLOAD]
        header = struct.pack(HEADER_FMT, TYPE_MC, conn_id, msg_id, seq, total,uuid)
        pkt = header + chunk
        with msg_lock:
            pending[(conn_id, msg_id, seq ,uuid)] = (pkt, addr, time.time())
        p2pExample.sock.sendto(pkt, addr)


def resend_loop():
    """定时重发未确认分片"""
    while True:
        time.sleep(0.05)
        now = time.time()
        with msg_lock:
            for key, (pkt, addr, last) in list(pending.items()):
                if now - last > 1:
                    p2pExample.sock.sendto(pkt, addr)
                    # print(key[0], key[1], key[2])
                    pending[key] = (pkt, addr , now)


def tcp_to_local_loop(conn_id, tcp_sock, udp_addr,uuid):
    msg_id_s[(conn_id,uuid)]=1
    ################################
    # last = time.time()
    # count = 0
    ##################################
    MAX_RECV = 8 * 1024 * 1024
    try:
        while True:
            data = tcp_sock.recv(MAX_RECV)
            ##############################################################
            # now = time.time()
            # diff = (now - last) * 1000  # 毫秒
            # print(f"recv {len(data)} bytes, interval: {diff:.2f}ms")
            # last = now
            # count += 1
            ###############################################################
            if not data:
                break
            send_fragmented(conn_id, data, udp_addr, uuid)
    except :pass
    finally:
        # 后端断开，通知 local 并清理
        time.sleep(0.3)
        p2pExample.sock.sendto(struct.pack(HEADER_FMT, TYPE_CLOSE, conn_id, 0, 0, 0,uuid), udp_addr)
        try:
            tcp_sock.close()
        except: pass
        with conns_lock:
            conns.pop((conn_id,uuid), None)
            msg_id_s.pop((conn_id,uuid), None)
        print(f"conn_id: {conn_id} 关闭")


def udp_recv_loop():
    """接收来自 local 的 UDP 包并路由到对应的后端 TCP"""
    while True:
        try:
            data, src = p2pExample.sock.recvfrom(60000)
            if not data or len(data) < HEADER_SIZE or data==Detection:
                if data==Detection:
                    p2pExample.sock.sendto(Detection, src)
                    continue
                elif type(eval(data.decode("utf-8")))==type(1):
                    p2pExample.resignup_server(data)
                    continue
            t, conn_id,msg_id,seq,total,uuid = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
            payload = data[HEADER_SIZE:]
            if t == TYPE_MC:
                ack = struct.pack(HEADER_FMT, TYPE_ACK, conn_id, msg_id, seq, total,uuid)
                p2pExample.sock.sendto(ack, src)
                if (conn_id, msg_id, uuid) in completed_msgs:
                    continue
                with conns_lock:
                    info = conns.get((conn_id,uuid))
                if info is None:
                    # 新连接：创建到 MC 后端的 TCP 连接，并保存 udp 源地址用于回复
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.connect_ex(MC_SERVER_ADDR)
                        with conns_lock:
                            conns[(conn_id,uuid)] = {'tcp': s, 'udp_addr': src}
                        threading.Thread(target=tcp_to_local_loop, args=(conn_id, s, src, uuid), daemon=True).start()
                        print(f"[relay] 为 conn {conn_id} 建立到 MC 后端的 TCP 连接")
                    except Exception as e:
                        print(f"[relay] 无法连接 MC 后端: {e}")
                        # 通知 local 断开
                        p2pExample.sock.sendto(struct.pack(HEADER_FMT, TYPE_CLOSE, conn_id, 0, 0, 0,uuid), src)
                        continue
                    info = conns.get((conn_id,uuid))
                # 分片拼接
                buf = fragments.setdefault((conn_id, msg_id,uuid), {})
                buf[seq] = payload
                if len(buf) == total and all(i in buf for i in range(total)): #分片集齐,开始拼接
                    assembled = b''.join(buf[i] for i in range(total))
                    fragments.pop((conn_id, msg_id,uuid), None)
                    mark_completed((conn_id, msg_id, uuid))
                    try:
                        info['tcp'].sendall(assembled)
                    except Exception:
                        traceback.print_exc()
                        try:
                            info['tcp'].close()
                        except:pass
                        with conns_lock:
                            conns.pop((conn_id,uuid), None)
                            msg_id_s.pop((conn_id,uuid), None)
                        p2pExample.sock.sendto(struct.pack(HEADER_FMT, TYPE_CLOSE, conn_id, 0, 0, 0,uuid), src)
            elif t == TYPE_CLOSE:
                # local 告知关闭，关闭后端 TCP
                with conns_lock:
                    info = conns.pop((conn_id,uuid))
                    msg_id_s.pop((conn_id,uuid), None)
                if info:
                    try:
                        info['tcp'].close()
                    except: pass
                lst=[]
                for k in fragments.keys():
                    if (k[0],k[2]) == (conn_id,uuid):
                        lst.append(k)
                for k in lst:
                    del fragments[k]
                lst=[]
                for k in pending.keys():
                    if (k[0],k[3])==(conn_id,uuid):
                        lst.append(k)
                for k in lst:
                    del pending[k]
            elif t==TYPE_P2P:
                p2pExample.recv_handle(payload,src)
            elif t == TYPE_ACK:
                with msg_lock:
                    if (conn_id, msg_id, seq ,uuid) in pending:
                        del pending[(conn_id, msg_id, seq ,uuid)]
        except :pass
        # print("udp_recv_loop接收接收到 ICMP Unreachable")


def mark_completed(msg_id):
    completed_msgs[msg_id] = time.time()
    completed_msgs.move_to_end(msg_id)


def cleanup_loop():
    """定期清理过期 completed_msgs，但保留最后一个"""
    while True:
        now = time.time()
        keys = list(completed_msgs.keys())
        for k in keys[:-1]:  # 保留最后一个
            if now - completed_msgs[k] > 5:
                del completed_msgs[k]
        time.sleep(1)

if __name__ == "__main__":
    print("[relay] 启动 relay")
    threading.Thread(target=resend_loop, daemon=True).start()
    threading.Thread(target=cleanup_loop, daemon=True).start()
    udp_recv_loop()
