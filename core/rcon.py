"""RCON 协议客户端。"""
import socket
import struct
import threading


class SimpleRCON:
    def __init__(self, host, port, password):
        self.host = host
        self.port = int(port)
        self.password = str(password)
        self.socket = None
        self.connected = False
        self._lock = threading.Lock()

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.host, self.port))

            self._send_packet(3, self.password)
            try:
                response = self._receive_packet()
            except socket.timeout:
                response = None
            if response:
                packet_id, packet_type, _ = response
                if packet_type == 2 and packet_id != -1:
                    self.connected = True
                    return True
            self.disconnect()
            return False
        except Exception:
            self.disconnect()
            raise

    def command(self, cmd):
        if not self.connected:
            raise ConnectionError("RCON not connected")
        with self._lock:
            if not self.connected:
                raise ConnectionError("RCON not connected")
            try:
                self._send_packet(2, cmd)
                return self._receive_full_response()
            except Exception:
                self.disconnect()
                raise

    def disconnect(self):
        with self._lock:
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
            self.socket = None
            self.connected = False

    # ---------- 内部 ----------
    def _send_packet(self, packet_type, body):
        if not self.socket:
            return
        body_bytes = body.encode("utf-8")
        length = len(body_bytes) + 10
        packet = struct.pack("<iii", length, 1, packet_type) + body_bytes + b"\x00\x00"
        self.socket.sendall(packet)

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.socket.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def _receive_packet(self):
        if not self.socket:
            return None
        try:
            size_data = self._recv_exact(4)
            if not size_data or len(size_data) < 4:
                return None
            size = struct.unpack("<i", size_data)[0]
            if size < 10 or size > 100000:
                return None
            data = self._recv_exact(size)
            if not data or len(data) < 10:
                return None
            packet_id, packet_type = struct.unpack("<ii", data[:8])
            body = data[8:-2].decode("utf-8", errors="replace")
            return packet_id, packet_type, body
        except socket.timeout:
            raise  # ★ 让 timeout 冒到上层
        except Exception:
            return None
    def _receive_full_response(self):
        """
        读取完整的 RCON 响应。
        Minecraft 服务端在响应较大时会分片发送（每个分片一个独立包），
        这里循环读取直到 socket 不再有新数据。
        """
        first = self._receive_packet()
        if not first:
            return ""

        body = first[2]

        # 用短超时试探后续分片
        old_timeout = self.socket.gettimeout()
        self.socket.settimeout(0.3)
        try:
            while True:
                try:
                    extra = self._receive_packet()
                except socket.timeout:
                    break
                except Exception:
                    break
                if not extra:
                    break
                body += extra[2]
        finally:
            try:
                self.socket.settimeout(old_timeout)
            except Exception:
                pass

        return body