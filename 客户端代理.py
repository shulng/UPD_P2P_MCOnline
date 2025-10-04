# local_proxy.py
from collections import OrderedDict
import socket
import threading
import struct
import time
import traceback
from uuid import UUID
import p2p_client

Detection=p2p_client.Detection.encode("utf-8")
p2pExample=p2p_client.Run(UUID("60273221-458b-45be-9cb4-85f8db0d7c51")) #

# 配置（按需修改）
LOCAL_TCP_BIND = ('0.0.0.0', 25566)   # Minecraft 客户端连到这里
RELAY_UDP_ADDR = (p2pExample.info["ip"],p2pExample.info["port"]) # Relay 的 UDP 地址

HEADER_FMT = ">BIIHH16s"  # type(1) + conn_id(4) + seq(2) + last_flag(1)
HEADER_SIZE = struct.calcsize(HEADER_FMT)

TYPE_MC = 0x01
TYPE_ACK   = 0x02
TYPE_CLOSE = 0x05

MAX_PAYLOAD = 256  # 保守一点，避免超过UDP上限

tcp_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
tcp_listener.bind(LOCAL_TCP_BIND)
tcp_listener.listen(200)

conns = {}
pending   = {}
fragments = {}
msg_id_s={}
completed_msgs = OrderedDict()
conns_lock = threading.Lock()
msg_lock = threading.Lock()
completed_msgs_lock = threading.Lock()

_next_conn_id = 1


def send_fragmented(conn_id, data,uuid):
    """把大数据分片后通过UDP发送"""
    with msg_lock:
        msg_id=msg_id_s[(conn_id,uuid)]
        msg_id_s[(conn_id,uuid)] = msg_id+1
    total = (len(data)+MAX_PAYLOAD-1) // MAX_PAYLOAD
    for seq in range(0, total):
        chunk = data[seq*MAX_PAYLOAD:(seq+1)*MAX_PAYLOAD]
        header = struct.pack(HEADER_FMT, TYPE_MC, conn_id, msg_id, seq, total,uuid)
        pkt = header + chunk
        with msg_lock:
            pending[(conn_id, msg_id, seq ,uuid)] = (pkt, time.time())
        p2pExample.sock.sendto(pkt, RELAY_UDP_ADDR)


def resend_loop():
    """定时重发未确认分片"""
    while True:
        time.sleep(0.05)
        now = time.time()
        with msg_lock:
            if not pending:
                continue
            for key, (pkt, last) in list(pending.items()):
                if now - last > 0.5:
                    del pending[key]
                    del fragments[key[0],key[1],key[3]]
                if now - last > 0.1:  # 100ms 超时
                    p2pExample.sock.sendto(pkt, RELAY_UDP_ADDR)


def gen_conn_id():
    global _next_conn_id
    with conns_lock:
        cid = _next_conn_id
        _next_conn_id = (_next_conn_id + 1) & 0xFFFFFFFF
        if _next_conn_id == 0:
            _next_conn_id = 1
        return cid


def udp_recv_loop():
    """统一接收来自 Relay 的 UDP，按 conn_id 分发到对应 TCP socket"""
    while True:
        try:
            data, addr = p2pExample.sock.recvfrom(60000)
            if not data or len(data) < HEADER_SIZE or data==Detection:
                continue
            t, conn_id,msg_id,seq,total,uuid = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
            payload = data[HEADER_SIZE:]
            with conns_lock:
                sock = conns.get((conn_id,uuid))
            if t == TYPE_MC:
                # 发 ACK
                ack = struct.pack(HEADER_FMT, TYPE_ACK, conn_id, msg_id, seq, total,uuid)
                p2pExample.sock.sendto(ack, addr)
                with completed_msgs_lock:
                    if (conn_id,msg_id,uuid) in completed_msgs:
                        continue
                if sock:
                    buf = fragments.setdefault((conn_id,msg_id,uuid), {})
                    buf[seq] = payload
                    if len(buf) == total and all(i in buf for i in range(total)): #分片集齐,开始拼接
                        assembled = b''.join(buf[i] for i in range(total))
                        # print("接到服务端的包",assembled)
                        fragments.pop((conn_id,msg_id,uuid), None)
                        mark_completed((conn_id,msg_id,uuid))
                        try:
                            sock.sendall(assembled)
                        except Exception:
                            # 发送失败 -> 关闭该连接
                            try:
                                sock.close()
                            except: pass
                            with conns_lock:
                                conns.pop((conn_id,uuid), None)
                                msg_id_s.pop((conn_id,uuid), None)
                else:
                    fragments.pop((conn_id, msg_id, uuid), None)
                    # print(f"没有找到 {conn_id} 的mc连接")

            elif t == TYPE_CLOSE:
                # Relay 告知后端关闭
                if sock:
                    try:
                        sock.close()
                    except: pass
                    with conns_lock:
                        conns.pop((conn_id,uuid), None)
                        msg_id_s.pop((conn_id,uuid), None)
                    print(f"[local] 收到 CLOSE for conn {conn_id}, 已关闭本地 TCP")
            elif t == TYPE_ACK:
                with msg_lock:
                    if (conn_id, msg_id, seq ,uuid) in pending:
                        del pending[(conn_id, msg_id, seq, uuid)]
        except Exception:
            traceback.print_exc()


def mark_completed(msg_id):
    completed_msgs[msg_id] = time.time()
    completed_msgs.move_to_end(msg_id)


def handle_client(conn_sock, client_addr, conn_id, uuid):
    msg_id_s[(conn_id,uuid)] = 1
    print(f"[local] 新客户端 {client_addr} -> conn_id {conn_id}")
    try:
        while True:
            data = conn_sock.recv(65536)
            if not data:
                break
            send_fragmented(conn_id, data,uuid)
    except:pass
    finally:
        # 客户端关闭，通知 Relay 关闭后端连接
        time.sleep(0.3)
        p2pExample.sock.sendto(struct.pack(HEADER_FMT, TYPE_CLOSE, conn_id, 0, 0, 0,uuid), RELAY_UDP_ADDR)
        try:
            conn_sock.close()
        except: pass
        with conns_lock:
            conns.pop((conn_id,uuid), None)
            msg_id_s.pop((conn_id,uuid),None)
        print(f"conn_id: {conn_id} 关闭")


def accept_loop():
    uuid=p2pExample.uuid.bytes
    while True:
        sock, addr = tcp_listener.accept()
        conn_id = gen_conn_id()
        with conns_lock:
            conns[(conn_id,uuid)] = sock
        t = threading.Thread(target=handle_client, args=(sock, addr, conn_id, uuid), daemon=True)
        t.start()


def cleanup_loop():
    """定期清理过期 completed_msgs，但保留最后一个"""
    while True:
        now = time.time()
        keys = list(completed_msgs.keys())
        for k in keys[:-1]:  # 保留最后一个
            if now - completed_msgs[k] > 5:
                del completed_msgs[k]
        time.sleep(0.5)

if __name__ == "__main__":
    print("[local] 启动 local proxy")
    threading.Thread(target=resend_loop, daemon=True).start()
    threading.Thread(target=udp_recv_loop, daemon=True).start()
    threading.Thread(target=cleanup_loop, daemon=True).start()
    accept_loop()
    print("结束")
