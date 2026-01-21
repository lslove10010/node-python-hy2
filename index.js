#!/usr/bin/env node
// Hysteria2 极简部署脚本（Node.js 版）
// 支持 .env 文件（无外部依赖）、环境变量、命令行端口参数
// 支持自定义节点名称（HY2_NODE_NAME）
// 默认跳过证书验证，适用于超低内存环境（32-64MB）

const fs = require('fs');
const https = require('https');
const os = require('os');
const path = require('path');
const { execFile, spawn } = require('child_process');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);

// ---------- 手动加载 .env 文件（使用自带模块） ----------
function loadEnv() {
  const envPath = path.join(__dirname, '.env');
  if (fs.existsSync(envPath)) {
    const content = fs.readFileSync(envPath, 'utf8');
    content.split(/\r?\n/).forEach(line => {
      line = line.trim();
      if (!line || line.startsWith('#')) return;

      const eqIndex = line.indexOf('=');
      if (eqIndex === -1) return;

      const key = line.substring(0, eqIndex).trim();
      let value = line.substring(eqIndex + 1).trim();

      // 去除可选的包围引号
      if ((value.startsWith('"') && value.endsWith('"')) ||
          (value.startsWith("'") && value.endsWith("'"))) {
        value = value.substring(1, value.length - 1);
      }

      process.env[key] = value;
    });
    console.log("✅ 从 .env 文件加载配置变量");
  }
}
loadEnv(); // 立即执行加载

// ---------- 默认配置 ----------
const HYSTERIA_VERSION = "v2.7.0";
const DEFAULT_PORT = 22222;
const DEFAULT_PASSWORD = "ieshare2025"; // 强烈建议修改！
const DEFAULT_NODE_NAME = "Hy2-Bing";   // 新增：默认节点名称

// 密码
const AUTH_PASSWORD = process.env.HY2_PASSWORD || DEFAULT_PASSWORD;
if (process.env.HY2_PASSWORD) {
  console.log("✅ 从 .env 或环境变量读取密码（HY2_PASSWORD）");
} else {
  console.log("⚠️ 未设置 HY2_PASSWORD，使用默认密码（极不安全！请立即修改）");
}

// 节点名称（新增）
const NODE_NAME = process.env.HY2_NODE_NAME || DEFAULT_NODE_NAME;
if (process.env.HY2_NODE_NAME) {
  console.log(`✅ 从 .env 或环境变量读取节点名称: ${NODE_NAME}`);
} else {
  console.log(`⚙️ 未设置 HY2_NODE_NAME，使用默认节点名称: ${NODE_NAME}`);
}

const CERT_FILE = "cert.pem";
const KEY_FILE = "key.pem";
const SNI = "www.bing.com";
const ALPN = "h3";

// ------------------------------
console.log("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~");
console.log("Hysteria2 极简部署脚本（Node.js 版）");
console.log("支持 .env 文件（无外部依赖）、环境变量、命令行端口参数");
console.log("支持自定义节点名称（HY2_NODE_NAME）");
console.log("示例 .env 文件内容：");
console.log("HY2_PORT=443");
console.log("HY2_PASSWORD=YourVeryStrongPassword123!");
console.log("HY2_NODE_NAME=MyCustomNode");  // 新增示例
console.log("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~");

// ---------- 获取端口 ----------
let SERVER_PORT = DEFAULT_PORT;

// 优先级：命令行参数 > 环境变量/.env > 默认
if (process.argv.length >= 3 && process.argv[2]) {
  SERVER_PORT = parseInt(process.argv[2], 10);
  console.log(`✅ 使用命令行指定端口: ${SERVER_PORT}（优先级最高）`);
} else if (process.env.HY2_PORT) {
  SERVER_PORT = parseInt(process.env.HY2_PORT, 10);
  console.log(`✅ 从 .env 或环境变量读取端口: ${SERVER_PORT}`);
} else {
  console.log(`⚙️ 未指定端口，使用默认端口: ${SERVER_PORT}`);
}

// ---------- 检测架构 ----------
function getArch() {
  const machine = os.arch();
  const platform = os.platform();
  if (platform !== 'linux') {
    console.log("❌ 只支持 Linux 系统");
    process.exit(1);
  }
  if (machine === 'x64' || machine === 'amd64') {
    return "amd64";
  } else if (machine === 'arm64') {
    return "arm64";
  } else {
    return "";
  }
}

const ARCH = getArch();
if (!ARCH) {
  console.log(`❌ 无法识别 CPU 架构: ${os.arch()}`);
  process.exit(1);
}

const ORIGINAL_BIN_NAME = `hysteria-linux-${ARCH}`;
const FINAL_BIN_NAME = "hy2";
const ORIGINAL_BIN_PATH = path.join(__dirname, ORIGINAL_BIN_NAME);
const FINAL_BIN_PATH = path.join(__dirname, FINAL_BIN_NAME);

// ---------- 下载二进制 ----------
async function downloadBinary() {
  if (fs.existsSync(FINAL_BIN_PATH)) {
    console.log("✅ hy2 二进制已存在，跳过下载和重命名。");
    return;
  }

  const url = `https://cdn.gh-proxy.org/https://github.com/apernet/hysteria/releases/download/app/${HYSTERIA_VERSION}/${ORIGINAL_BIN_NAME}`;
  console.log(`⏳ 下载 Hysteria2 二进制: ${url}`);

  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(ORIGINAL_BIN_PATH);
    https.get(url, { timeout: 30000 }, (response) => {
      if (response.statusCode !== 200) {
        reject(new Error(`下载失败，状态码: ${response.statusCode}`));
        return;
      }
      response.pipe(file);
      file.on('finish', () => {
        file.close();
        fs.renameSync(ORIGINAL_BIN_PATH, FINAL_BIN_PATH);
        fs.chmodSync(FINAL_BIN_PATH, 0o755);
        console.log(`✅ 下载完成，重命名为 ${FINAL_BIN_NAME} 并设置可执行权限。`);
        resolve();
      });
    }).on('error', (err) => {
      if (fs.existsSync(ORIGINAL_BIN_PATH)) {
        fs.unlinkSync(ORIGINAL_BIN_PATH);
      }
      reject(err);
    });
  });
}

// ---------- 生成证书 ----------
async function ensureCert() {
  if (fs.existsSync(CERT_FILE) && fs.existsSync(KEY_FILE)) {
    console.log("✅ 发现证书，使用现有 cert/key。");
    return;
  }

  console.log("🔑 未发现证书，使用 openssl 生成自签证书（prime256v1）...");
  try {
    await execFileAsync('openssl', [
      'req', '-x509', '-nodes', '-newkey', 'ec',
      '-pkeyopt', 'ec_paramgen_curve:prime256v1',
      '-days', '3650',
      '-keyout', KEY_FILE,
      '-out', CERT_FILE,
      '-subj', `/CN=${SNI}`
    ]);
    console.log("✅ 证书生成成功。");
  } catch (err) {
    console.log("❌ openssl 生成证书失败，请确保系统已安装 openssl");
    process.exit(1);
  }
}

// ---------- 写配置文件 ----------
function writeConfig() {
  const config = `
listen: ":${SERVER_PORT}"

tls:
  cert: "${path.resolve(CERT_FILE)}"
  key: "${path.resolve(KEY_FILE)}"
  alpn:
    - "${ALPN}"

auth:
  type: "password"
  password: "${AUTH_PASSWORD}"

bandwidth:
  up: "200 mbps"
  down: "200 mbps"

quic:
  max_idle_timeout: "10s"
  max_concurrent_streams: 4
  initial_stream_receive_window: 65536
  max_stream_receive_window: 131072
  initial_conn_receive_window: 131072
  max_conn_receive_window: 262144
`;

  fs.writeFileSync('server.yaml', config.trim() + '\n');
  console.log(`✅ 写入配置 server.yaml（端口=${SERVER_PORT}）。`);
}

// ---------- 获取服务器 IP ----------
async function getServerIp() {
  return new Promise((resolve) => {
    https.get('https://api.ipify.org', { timeout: 10000 }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data.trim() || 'YOUR_SERVER_IP'));
    }).on('error', () => resolve('YOUR_SERVER_IP'));
  });
}

// ---------- 打印连接信息 ----------
function printConnectionInfo(ip) {
  const maskedPass = AUTH_PASSWORD.length >= 6
    ? AUTH_PASSWORD.substring(0, 3) + '****' + AUTH_PASSWORD.slice(-3)
    : '****';

  console.log("🎉 Hysteria2 部署成功！（极简优化版）");
  console.log("==========================================================================");
  console.log("📋 服务器信息:");
  console.log(`   🌐 IP地址: ${ip}`);
  console.log(`   🔌 端口: ${SERVER_PORT}`);
  console.log(`   🔑 密码: ${maskedPass}`);
  console.log(`   📛 节点名称: ${NODE_NAME}`);
  console.log("");
  console.log("📱 节点链接（跳过证书验证）:");
  console.log(`hysteria2://${AUTH_PASSWORD}@${ip}:${SERVER_PORT}?sni=${SNI}&alpn=${ALPN}&insecure=1#${NODE_NAME}`);
  console.log("");
  console.log("==========================================================================");
}

// ---------- 主逻辑 ----------
async function main() {
  await downloadBinary();
  await ensureCert();
  writeConfig();
  const serverIp = await getServerIp();
  printConnectionInfo(serverIp);
  console.log("🚀 启动 Hysteria2 服务器...");

  const child = spawn(FINAL_BIN_PATH, ['server', '-c', 'server.yaml'], {
    stdio: 'inherit'
  });

  child.on('error', (err) => {
    console.error('启动失败:', err);
    process.exit(1);
  });

  process.on('SIGINT', () => {
    child.kill();
    process.exit();
  });
}

main().catch(err => {
  console.error('脚本执行出错:', err);
  process.exit(1);
});
