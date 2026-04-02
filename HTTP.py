import socket
import threading
import re
import os

class HTTP():
    def __init__(self, pHost, pPort):
        self.host = pHost
        self.port = pPort

    def run(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"HTTP Proxy запущен на {self.host}:{self.port}")
        print("Поддерживается только HTTP (порт 80)")
        print("-" * 50)

        while True:
            client_socket, client_address = self.server_socket.accept()
            print(f"Подключение от {client_address}")
            thread = threading.Thread(target=self.client, args=(client_socket,))
            thread.daemon = True
            thread.start()

    def client(self, client_socket):
        try:
            result = self.clientData(client_socket)
            if not result:
                return
            method, url, version, lines = result
            
            if method not in ["GET", "POST", "HEAD"]:
                print(f"  Отклонён метод: {method}")
                self.error(client_socket, 501, "Method Not Supported")
                return
            
            parse_result = self.parse(client_socket, url, lines)
            if not parse_result or parse_result[0] is None:
                return
            host, port, path = parse_result
            
            if port != 80:
                print(f"  Отклонён порт: {port}")
                self.error(client_socket, 501, "Only HTTP (port 80) is supported")
                return
            
            server_socket = self.connect(client_socket, host, port)
            if not server_socket:
                return
            
            new_request = self.newRequest(method, path, version, lines)
            
            print(f"  -> {method} {host}:{port}{path}")
            
            server_socket.send(new_request.encode())
            
            while True:
                data = server_socket.recv(8192)
                if not data:
                    break
                client_socket.send(data)
            
            print(f"  <- {host}:{port} - завершено")
            
        except ConnectionResetError:
            print("  Клиент разорвал соединение")
        except Exception as e:
            print(f"  Ошибка: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass

    def newRequest(self, method, path, version, lines):
        new_request_line = f"{method} {path} {version}\r\n"
        new_headers = []
        
        for line in lines[1:]:
            if not line.strip():
                continue
            if line.lower().startswith('proxy-connection:'):
                continue
            new_headers.append(line)
        
        has_connection = any(h.lower().startswith('connection:') for h in new_headers)
        if not has_connection:
            new_headers.append("Connection: close")
        
        new_request = new_request_line + '\r\n'.join(new_headers) + '\r\n\r\n'
        return new_request

    def connect(self, client_socket, host, port):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(5)
            server_socket.connect((host, port))
            server_socket.settimeout(None)
            return server_socket
        except socket.timeout:
            print(f"  Таймаут подключения к {host}:{port}")
            self.error(client_socket, 504, "Gateway Timeout")
            return None
        except ConnectionRefusedError:
            print(f"  Соединение отклонено {host}:{port}")
            self.error(client_socket, 502, "Bad Gateway")
            return None
        except Exception as e:
            print(f"  Не удалось подключиться к {host}:{port} - {e}")
            self.error(client_socket, 502, "Bad Gateway")
            return None
        
    def clientData(self, client_socket):
        try:
            request_data = client_socket.recv(65536)
            if not request_data:
                return None

            request_str = request_data.decode('utf-8', errors='replace')
            lines = request_str.split('\r\n')
            request_line = lines[0]
            
            if not request_line:
                return None
                
        except Exception as e:
            print(f"Ошибка чтения от клиента: {e}")
            return None
            
        match = re.match(r'^(\w+) (.*?) (HTTP/\d\.\d)$', request_line)
        if not match:
            print(f"Некорректный request line: {request_line}")
            self.error(client_socket, 400, "Bad Request")
            return None
            
        method, url, version = match.groups()
        return method, url, version, lines
    
    def parse(self, client_socket, url, lines):
        if url.startswith('http://'):
            url = url[7:]
            
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
            
            return host, port, path
        
        else:
            path = url
            if not path.startswith('/'):
                path = '/' + path
            
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
                print("Отсутствует Host header")
                self.error(client_socket, 400, "Missing Host header")
                return None, None, None
            
            return host, port, path

    def error(self, client_socket, code, message):
        response = f"HTTP/1.1 {code} {message}\r\n"
        response += f"Content-Length: 0\r\n"
        response += f"Connection: close\r\n"
        response += f"\r\n"
        try:
            client_socket.send(response.encode())
        except:
            pass
        try:
            client_socket.close()
        except:
            pass

if __name__ == "__main__":
    try:
        server = HTTP("127.0.0.1", 8080)
        server.run()
    except KeyboardInterrupt:
        print("\nПрокси остановлен")
        os._exit(0)