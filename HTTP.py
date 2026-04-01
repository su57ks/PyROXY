import socket
import threading
import re

class HTTP():
    def __init__(self, pHost, pPort):
        self.host = pHost
        self.port = pPort

    def run(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Прокси запущен на {self.host}:{self.port}")

        while True:
            client_socket, client_address = self.server_socket.accept()
            print(f"Подключение от {client_address}")
            thread = threading.Thread(target=self.client, args=(client_socket,))
            thread.start()

    def client(self, client_socket):
        method, url, version, lines = self.clientData(client_socket)
        host, port, path = self.parse(client_socket, url, lines)
        server_socket = self.connect(client_socket, host, port)
        new_request = self.newRequest(method, path, version, lines)
        server_socket.send(new_request.encode())
        try:
            while True:
                data = server_socket.recv(4096)
                if not data:
                    break
                client_socket.send(data)
        except Exception as e:
            print(f"Ошибка при передаче данных: {e}")
        finally:
            server_socket.close()
            client_socket.close()

    def newRequest(self, method, path, version, lines):
        new_request_line = f"{method} {path} {version}\r\n"
        new_headers = []
        for line in lines[1:]:
            if line.lower().startswith('proxy-connection:'):
                continue
            new_headers.append(line)
        new_request = new_request_line + '\r\n'.join(new_headers) + '\r\n\r\n'
        return new_request

    def connect(self, client_socket, host, port):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.connect((host, port))
        except Exception as e:
            print(f"Не удалось подключиться к {host}:{port} - {e}")
            self.error(client_socket, 502, "Bad Gateway")
            return
        return server_socket
        
    def clientData(self, client_socket):
        try:
            request_data = client_socket.recv(4096)
            if not request_data:
                return

            request_str = request_data.decode('utf-8', errors='replace')
            lines = request_str.split('\r\n')
            request_line = lines[0]
        except Exception as e:
            print(f"Ошибка чтения от клиента: {e}")
            client_socket.close()
            return
        match = re.match(r'^(\w+) (.*?) (HTTP/\d\.\d)$', request_line)
        if not match:
            self.error(client_socket, 400, "Bad Request")
            return
        method, url, version = match.groups()
        return method, url, version, lines
    
    def parse(self, client_socket, url, lines):
        if url.startswith('http://'):
            url = url.replace('http://', "")
            if '/' in url:
                host_part, path = url.split('/', 1)
                path = '/' + path
            else:
                host_part = url
                path = '/'
            if ':' in host_part:
                host, port = host_part.split(':')
                port = int(port)
            else:
                host = host_part
                port = 80
        else:
            path = url
            host = None
            port = 80
            for line in lines[1:]:
                if line.lower().startswith('host:'):
                    host_port = line.split(':', 1)[1].strip()
                    if ':' in host_port:
                        host, port_str = host_port.split(':')
                        port = int(port_str)
                    else:
                        host = host_port
                        port = 80
                    break
            if not host:
                self.error(client_socket, 400, "Missing Host header")
                return
        return host, port, path

    def error(self, client_socket, code, message):
            response = f"HTTP/1.1 {code} {message}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            client_socket.send(response.encode())
            client_socket.close()

server = HTTP("127.0.0.1", 8080)
server.run()