import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ==============================
# 配置说明
# ==============================
# 本脚本支持从以下来源加载配置（优先级从高到低）：
# 1. 面板环境变量（Pterodactyl 等面板的 "Variables" 设置）
# 2. /home/container/.env 文件（你可以手动创建）
# 3. 脚本中的默认值
#
# HY2_NODE_NAME = 节点别名（显示在客户端节点列表中的名称，可自定义中文/英文）
#                 示例：HY2_NODE_NAME=美国节点1
#                 如果不设置，默认使用 "Hysteria2 Node"
#
# 其他变量同之前：
# HY2_PORT=7102
# HY2_PASSWORD=your_very_strong_password_here
# ARCH=amd64
# MASQUERADE_URL=https://www.bing.com
# FAKE_DOMAIN=bing.com

# 工作目录：现在使用当前工作目录（容器启动时通常为 /home/container）
# 这样更灵活，无需硬编码路径。如果面板在其他目录启动，也能正常工作
WORK_DIR = Path.cwd()
HY2_BINARY = WORK_DIR / "hysteria"
CONFIG_FILE = WORK_DIR / "config.yaml"
CERT_FILE = WORK_DIR / "cert.crt"
KEY_FILE = WORK_DIR / "cert.key"
ENV_FILE = WORK_DIR / ".env"  # .env 文件也会在当前目录查找

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
    """下载最新版 Hysteria2 二进制"""
    arch = os.getenv("ARCH", "amd64").lower()
    binary_name = f"hysteria-linux-{arch}"
    
    if HY2_BINARY.exists():
        print(f"Hysteria2 二进制已存在（{binary_name}），跳过下载")
        return

    print(f"正在下载最新版 Hysteria2 ({binary_name})...")
    url = f"https://github.com/apernet/hysteria/releases/latest/download/{binary_name}"
    try:
        urllib.request.urlretrieve(url, HY2_BINARY)
        HY2_BINARY.chmod(0o755)
        print("下载完成")
    except Exception as e:
        print(f"下载失败（可能架构错误？当前设置: {arch}）: {e}")
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
    
    # 构建链接（如果有节点名称，则添加 #节点名称）
    base_url = f"hysteria2://{password}@{public_ip}:{port}/?sni={fake_domain}&insecure=1"
    client_url = f"{base_url}#{hy2_node_name}" if hy2_node_name else base_url
    
    print(f"\n=== Hysteria2 服务器启动成功 ===")
    print(f"监听端口: {port}")
    print(f"公网 IP: {public_ip}")
    print(f"节点名称: {hy2_node_name}")
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
    # 无需 os.chdir，因为已经使用 Path.cwd() 作为工作目录
    
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
