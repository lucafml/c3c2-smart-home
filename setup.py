import secrets
import socket

class generate:
    def system_id():
        return secrets.token_hex(6)

    def token():
        return secrets.token_urlsafe(96)
    
class get:
    def ip():
        try:
            # The IP address used here doesn't matter; it's just for checking the LAN IP.
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]  # Get the local IP address from the socket
            s.close()
            return lan_ip
        except Exception as e:
            return f"Error: {e}"

if __name__ == "__main__":
    print(get.ip())
