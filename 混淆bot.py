import os
import subprocess
import sys
import time
import urllib.request
import random
import string
from pathlib import Path

# ==============================
# 配置说明
# ==============================
WORK_DIR = Path.cwd()
CONFIG_FILE = WORK_DIR / "config.yaml"
CERT_FILE = WORK_DIR / "cert.crt"
KEY_FILE = WORK_DIR / "cert.key"
ENV_FILE = WORK_DIR / ".env"
BINARY_RECORD = WORK_DIR / ".bin_name"  # 隐藏文件，记录当前二进制文件名
HY2_BINARY = None  # 将在 download_hysteria2 中动态设置

def load_dotenv():
    """加载 .env 文件（如果存在）"""
    if ENV_FILE.exists():
        print(".env 文件已检测到，正在加载...")
        try:
            for line in ENV_FILE.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
            print(".env 加载完成")
        except Exception as e:
            print(f".env 加载失败: {e}")

def get_public_ip():
    """自动获取服务器公网 IPv4 地址（多备用源，提高成功率）"""
    ip_sources = [
        "https://api.ipify.org",
        "https://ifconfig.me",
        "https://icanhazip.com",
        "https://ipinfo.io/ip",
        "http://checkip.amazonaws.com"
    ]
    
    for source in ip_sources:
        try:
            with urllib.request.urlopen(source, timeout=5) as response:
                ip = response.read().decode('utf-8').strip()
                if ip:
                    print(f"自动获取公网 IP 成功（来源: {source}）：{ip}")
                    return ip
        except Exception:
            continue
    
    print("\033[91m自动获取公网 IP 失败（所有来源均不可达），请手动查看服务器 IP 并替换链接中的地址\033[m")
    return "你的服务器IP"

def download_hysteria2():
    """下载最新版 Hysteria2 二进制，使用纯随机文件名"""
    global HY2_BINARY
    arch = os.getenv("ARCH", "amd64").lower()
    binary_name = f"hysteria-linux-{arch}"

    # 优先检查记录文件
    if BINARY_RECORD.exists():
        recorded_name = BINARY_RECORD.read_text().strip()
        candidate = WORK_DIR / recorded_name
        if candidate.exists() and os.access(candidate, os.X_OK):
            HY2_BINARY = candidate
            print(f"检测到已有二进制文件（记录名称）：{recorded_name}，跳过下载")
            return

    # 生成纯随机文件名（16位小写字母+数字）
    random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
    temp_binary = WORK_DIR / "temp-binary"

    print(f"正在下载最新版 Hysteria2 ({binary_name})...")
    url = f"https://github.com/apernet/hysteria/releases/latest/download/{binary_name}"
    try:
        urllib.request.urlretrieve(url, temp_binary)
        temp_binary.chmod(0o755)
        
        # 重命名为纯随机名称
        HY2_BINARY = WORK_DIR / random_name
        temp_binary.rename(HY2_BINARY)
        
        # 记录新文件名到隐藏文件
        BINARY_RECORD.write_text(random_name)
        
        print(f"下载完成，已使用纯随机文件名：{random_name}")
    except Exception as e:
        print(f"下载失败（可能架构错误？当前设置: {arch}）: {e}")
        if temp_binary.exists():
            temp_binary.unlink()
        sys.exit(1)

def generate_self_signed_cert():
    """生成自签证书（如果不存在）"""
    if CERT_FILE.exists() and KEY_FILE.exists():
        print("自签证书已存在，跳过生成")
        return
    print("正在生成自签证书...")
    try:
        fake_domain = os.getenv("FAKE_DOMAIN", "bing.com")
        subprocess.run([
            "openssl", "req", "-x509", "-nodes", "-days", "36500",
            "-newkey", "rsa:2048",
            "-keyout", str(KEY_FILE),
            "-out", str(CERT_FILE),
            "-subj", f"/CN={fake_domain}"
        ], check=True)
        KEY_FILE.chmod(0o600)
        CERT_FILE.chmod(0o644)
        print("自签证书生成完成")
    except Exception as e:
        print(f"证书生成失败（可能缺少 openssl）: {e}")
        sys.exit(1)

def generate_config():
    """生成 Hysteria2 配置文件"""
    port = os.getenv("HY2_PORT", "7102")
    password = os.getenv("HY2_PASSWORD")
    masquerade_url = os.getenv("MASQUERADE_URL", "https://www.bing.com")
    
    if not password:
        print("\033[91m错误：HY2_PASSWORD 未设置！请在面板环境变量或 .env 文件中设置强密码\033[m")
        sys.exit(1)
    
    try:
        port = int(port)
    except ValueError:
        print("\033[91m错误：HY2_PORT 必须是数字\033[m")
        sys.exit(1)
    
    config_content = f"""listen: :{port}
tls:
  cert: {CERT_FILE}
  key: {KEY_FILE}
auth:
  type: password
  password: {password}
masquerade:
  type: proxy
  proxy:
    url: {masquerade_url}
    rewriteHost: true
"""
    CONFIG_FILE.write_text(config_content)
    print("配置文件已生成")

def run_hysteria2():
    """运行 Hysteria2 服务"""
    public_ip = get_public_ip()
    port = os.getenv("HY2_PORT", "7102")
    password = os.getenv("HY2_PASSWORD", "[未设置]")
    fake_domain = os.getenv("FAKE_DOMAIN", "bing.com")
    hy2_node_name = os.getenv("HY2_NODE_NAME", "Hysteria2 Node").strip()
    
    base_url = f"hysteria2://{password}@{public_ip}:{port}/?sni={fake_domain}&insecure=1"
    client_url = f"{base_url}#{hy2_node_name}" if hy2_node_name else base_url
    
    print(f"\n=== Hysteria2 服务器启动成功 ===")
    print(f"监听端口: {port}")
    print(f"公网 IP: {public_ip}")
    print(f"节点名称: {hy2_node_name}")
    print(f"当前二进制文件: {HY2_BINARY.name}")
    print(f"工作目录: {WORK_DIR}\n")
    
    print("客户端连接链接（自签证书，需要允许不安全）：")
    print(f"\n\033[92m{client_url}\033[m\n")
    
    print("提示：")
    print("- 可直接复制上方链接导入 v2rayNG / NekoBox / Clash Meta 等客户端")
    print("- 节点将在客户端显示为：{}".format(hy2_node_name if hy2_node_name else "默认名称"))
    print("- 如果 IP 获取失败，请手动替换链接中的“你的服务器IP”")
    print("- 日志输出开始（面板重启会自动运行）\n")
    
    subprocess.run([str(HY2_BINARY), "server", "-c", str(CONFIG_FILE)])

def main():
    print("=== Hysteria2 容器专用启动脚本（工作目录为当前路径）===")
    print(f"当前工作目录: {WORK_DIR}")
    
    load_dotenv()
    
    download_hysteria2()
    generate_self_signed_cert()
    generate_config()
    
    time.sleep(2)
    
    run_hysteria2()

if __name__ == "__main__":
    main()
