print('Starting olis api')
from flask import Flask, request, jsonify, render_template_string, Response, redirect, url_for, send_from_directory, make_response, flash, abort
import subprocess, tempfile, os, shutil, psutil, time, json, uuid, re
from urllib.parse import urljoin
from werkzeug.utils import secure_filename
from flask_cors import CORS
from datetime import datetime, timedelta
import base64
import requests
from openai import OpenAI
import os
from random import random, randint
from urllib.parse import urljoin
from threading import Thread
from collections import deque
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
CORS(app)  # This allows all routes to accept cross-origin requests

# ========================
# CONFIG
# ========================
TIMEOUT = 10
MAX_OUTPUT_SIZE = 5000
NODE_PATH = os.path.expanduser("~/node/bin/node")
start_time = time.time()

SECRET_PASSCODE_B64 = "SEk="
SECRET_PASSCODE = base64.b64decode(SECRET_PASSCODE_B64).decode()

URLS_FILE = "urls.json"
LOCKDOWN = False  # Global lockdown flag
FIND = False
CLIENTS_JSON = "clients.json"

CURRENT_PROXY="math.waithuh.workers.dev";
# ========================
# UTILITIES
# ========================

def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file,"r") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_json(file, data):
    with open(file,"w") as f:
        json.dump(data,f,indent=2)

def is_valid_route_path(path):
    if not path or not path.startswith("/"):
        return False
    return bool(re.fullmatch(r"\/[A-Za-z0-9_\-\/\.]*", path))

# ========================
# LOAD DATA
# ========================
urls = load_json(URLS_FILE)
clients = load_json(CLIENTS_JSON)

# ========================
# HOME & STATS
# ========================

HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
<style>
body{font-family:Arial;max-width:1000px;margin:auto;padding:20px; background: lightblue;}
a{display:block;margin:10px 0;font-size:18px;}
.stats{margin-top:20px;padding:10px;background:#f0f0f0;}
canvas{margin-top:20px;}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
<ul>
<li><a href="/shortener">URL Shortener</a></li>
<li><a href="/user">User Activity</a></li>
<li><a href="/clients">Client Manager</a></li>
<li><a href="/client_script">Client Script</a></li>
</ul>
<h2>Server Stats</h2>
<div class="stats" id="stats">Loading...</div>
<canvas id="usageChart" width="800" height="400"></canvas>
<script>
let chart; const maxDataPoints=30; let lastSent=0,lastRecv=0;
function createChart(){
const ctx=document.getElementById("usageChart").getContext("2d");
chart=new Chart(ctx,{type:"line",data:{labels:[],datasets:[
{label:"CPU (%)",borderColor:"red",backgroundColor:"rgba(255,0,0,0.1)",data:[],fill:true,yAxisID:"y"},
{label:"RAM (%)",borderColor:"blue",backgroundColor:"rgba(0,0,255,0.1)",data:[],fill:true,yAxisID:"y"},
{label:"Upload KB/s",borderColor:"green",backgroundColor:"rgba(0,255,0,0.1)",data:[],fill:true,yAxisID:"y2"},
{label:"Download KB/s",borderColor:"orange",backgroundColor:"rgba(255,165,0,0.1)",data:[],fill:true,yAxisID:"y2"}
]},options:{responsive:true,animation:false,scales:{y:{beginAtZero:true,max:100,position:"left",title:{display:true,text:"CPU & RAM (%)"}},y2:{beginAtZero:true,position:"right",title:{display:true,text:"Network KB/s"}}}}});
}
async function updateStats(){
try{
const r=await fetch("/stats");
const d=await r.json();
const h=Math.floor(d.uptime_seconds/3600);
const m=Math.floor((d.uptime_seconds%3600)/60);
const s=d.uptime_seconds%60;
let up=0,down=0;
if(lastSent && lastRecv){up=(d.net_sent-lastSent)/1024;down=(d.net_recv-lastRecv)/1024;}
lastSent=d.net_sent; lastRecv=d.net_recv;
document.getElementById("stats").innerHTML=`CPU: ${d.cpu}%<br>RAM: ${d.ram}%<br>Upload: ${up.toFixed(2)} KB/s<br>Download: ${down.toFixed(2)} KB/s<br>Uptime: ${h}h ${m}m ${s}s`;
const now=new Date().toLocaleTimeString();
chart.data.labels.push(now);
chart.data.datasets[0].data.push(d.cpu);
chart.data.datasets[1].data.push(d.ram);
chart.data.datasets[2].data.push(up);
chart.data.datasets[3].data.push(down);
if(chart.data.labels.length>maxDataPoints){chart.data.labels.shift();chart.data.datasets.forEach(x=>x.data.shift());}
chart.update();
}catch(e){document.getElementById("stats").textContent="Error fetching stats";}
}
createChart();
setInterval(updateStats,1000);
updateStats();
</script>
</body>
</html>
<div style="position: relative; height: 400px; margin-top: 20px;">
    <canvas id="onlineChart"></canvas>
</div>

<script>
    let charte;

    async function fetchData() {
        try {
            const response = await fetch('/api/online-history');
            const result = await response.json();

            if (result.success && result.data.length > 0) {
                updateChart(result.data);
                updateStats(result.data);
                document.getElementById('lastUpdate').textContent = new Date().toLocaleString();
            } else {
                console.log('No data available yet');
            }
        } catch (error) {
            console.error('Error fetching data:', error);
        }
    }

    function updateStats(data) {
        const counts = data.map(d => d.count);
        const current = counts[counts.length - 1];
        const avg = (counts.reduce((a, b) => a + b, 0) / counts.length).toFixed(1);
        const peak = Math.max(...counts);

        document.getElementById('currentOnline').textContent = current;
        document.getElementById('avgOnline').textContent = avg;
        document.getElementById('peakOnline').textContent = peak;
    }

    function updateChart(data) {
        const labels = data.map(d => {
            const date = new Date(d.timestamp);
            return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        });
        const counts = data.map(d => d.count);

        if (charte) {
            charte.destroy();
        }

        const ctx = document.getElementById('onlineChart').getContext('2d');
        charte = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Online Clients',
                    data: counts,
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0, // REMOVE DOTS
                    pointHoverRadius: 0, // NO HOVER DOTS EITHER

                    // Dynamic segment coloring
                    segment: {
                        borderColor: ctx => {
                            const curr = ctx.p1.parsed.y;
                            const prev = ctx.p0.parsed.y;

                            if (curr > prev) return '#4CAF50';  // green up
                            if (curr < prev) return '#f44336';  // red down
                            return '#2196F3'; // blue flat
                        },
                        backgroundColor: ctx => {
                            const curr = ctx.p1.parsed.y;
                            const prev = ctx.p0.parsed.y;

                            if (curr > prev) return 'rgba(76, 175, 80, 0.1)';
                            if (curr < prev) return 'rgba(244, 67, 54, 0.1)';
                            return 'rgba(33, 150, 243, 0.1)';
                        }
                    }
                }]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: { size: 14 },
                        bodyFont: { size: 13 }
                    }
                },

                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1,
                            font: { size: 12 }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    x: {
                        ticks: {
                            font: { size: 11 },
                            maxRotation: 45,
                            minRotation: 45
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    fetchData();
    setInterval(fetchData, 30000);
</script>

"""

@app.route("/")
def home():
    return render_template_string(HOME_HTML)

@app.route("/prox")
def prox():
    return CURRENT_PROXY

@app.route("/stats")
def stats():
    cpu=psutil.cpu_percent(interval=0.5)
    tmp = randint(102, 105)
    ram=psutil.virtual_memory().percent
    uptime=int(time.time()-start_time)
    net_io=psutil.net_io_counters()
    return jsonify({"cpu":cpu,"ram":ram,"uptime_seconds":uptime,"net_sent":net_io.bytes_sent,"net_recv":net_io.bytes_recv,"tmp":tmp})

# ========================
# URL SHORTENER
# ========================
@app.route("/shortener",methods=["GET","POST"])
def shortener_dashboard():
    global urls
    if request.method=="POST":
        action=request.form.get("action")
        sid=request.form.get("short_id")
        target=request.form.get("target")
        if action=="delete" and sid in urls: urls.pop(sid,None); save_json(URLS_FILE,urls)
        if action=="add" and sid and target: urls[sid]=target; save_json(URLS_FILE,urls)
        return redirect(url_for("shortener_dashboard"))
    html="<style> body{background:lightblue;}</style><h1>URL Shortener</h1><form method='post'>Short ID: <input name='short_id'><br>Target URL: <input name='target'><br><button type='submit' name='action' value='add'>Add</button></form><hr><ul>"
    for sid,target in urls.items():
        html+=f"<li><a href='/{sid}' target='_blank'>/{sid}</a> → {target} <form style='display:inline' method='post'><input type='hidden' name='short_id' value='{sid}'><button type='submit' name='action' value='delete'>Delete</button></form></li>"
    html+="</ul><p><a href='/'>Back Home</a></p>"
    return html

@app.route("/<short_id>")
def proxy_site(short_id):
    if short_id not in urls:
        return redirect("/404")
    target_url = urls[short_id]
    try:
        r = requests.get(target_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "text/html")
        html = r.text
        # Only modify HTML content for relative URLs
        if "text/html" in content_type:
            html = html.replace('src="/', f'src="/asset/{short_id}/').replace('href="/', f'href="/asset/{short_id}/')
        return Response(html, content_type=content_type)
    except Exception as e:
        return f"Error fetching {target_url}: {e}", 500

@app.route("/asset/<short_id>/<path:asset>")
def proxy_asset(short_id, asset):
    if short_id not in urls:
        return redirect("/404")
    asset_url = urljoin(urls[short_id], asset)
    try:
        r = requests.get(asset_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return Response(r.content, content_type=r.headers.get("Content-Type", "application/octet-stream"))
    except Exception as e:
        return f"Error fetching asset {asset_url}: {e}", 500


# ========================
# CLIENT MANAGER
# ========================

CLIENTS_HTML = """
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<!DOCTYPE html>
<html>
<head>
  <title>Client Manager</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { box-sizing: border-box; }
    body {
      background: lightblue;
      padding: 15px;
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    .header-section {
      background: white;
      padding: 20px;
      border-radius: 10px;
      margin-bottom: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .stats-row {
      display: flex;
      gap: 20px;
      margin-bottom: 15px;
      flex-wrap: wrap;
    }
    .stat-box {
      background: #f0f8ff;
      padding: 15px 25px;
      border-radius: 8px;
      border: 2px solid #4a90e2;
      font-size: 18px;
      font-weight: bold;
      flex: 1;
      min-width: 150px;
      text-align: center;
    }
    .button-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .btn {
      padding: 12px 24px;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.2s;
    }
    .btn-danger { background: #e74c3c; color: white; }
    .btn-danger:hover { background: #c0392b; }
    .btn-primary { background: #3498db; color: white; }
    .btn-primary:hover { background: #2980b9; }
    .recent { background-color: #d4edda; }
    .inactive { background-color: #f8d7da; }
    .table-container {
      overflow-x: auto;
      background: white;
      border-radius: 10px;
      padding: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      margin-bottom: 20px;
    }
    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0 10px;
    }
    th {
      padding: 15px;
      text-align: left;
      background: #34495e;
      color: white;
      font-weight: 600;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    th:first-child { border-radius: 8px 0 0 8px; }
    th:last-child { border-radius: 0 8px 8px 0; }
    td {
      padding: 15px;
      vertical-align: top;
    }
    tr.recent, tr.inactive {
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    tr td:first-child { border-radius: 8px 0 0 8px; }
    tr td:last-child { border-radius: 0 8px 8px 0; }

    .action-cell {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .action-group {
      display: flex;
      gap: 5px;
      flex-wrap: wrap;
    }
    .action-group form {
      display: inline-flex;
      margin: 0;
    }
    .action-group input[type="text"],
    .action-group input[type="file"] {
      padding: 6px 10px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 13px;
      max-width: 180px;
    }
    .action-group button {
      padding: 6px 12px;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
      white-space: nowrap;
    }
    .btn-ban { background: #e74c3c; color: white; }
    .btn-ban:hover { background: #c0392b; }
    .btn-unban { background: #95a5a6; color: white; }
    .btn-unban:hover { background: #7f8c8d; }
    .btn-delete { background: #e74c3c; color: white; }
    .btn-delete:hover { background: #c0392b; }
    .btn-unlock { background: #27ae60; color: white; }
    .btn-unlock:hover { background: #229954; }
    .btn-redirect { background: #3498db; color: white; }
    .btn-redirect:hover { background: #2980b9; }
    .btn-lock { background: #f39c12; color: white; }
    .btn-lock:hover { background: #e67e22; }
    .btn-question { background: #8e44ad; color: white; }
    .btn-question:hover { background: #7d3c98; }
    .btn-inject { background: #e67e22; color: white; }
    .btn-inject:hover { background: #d35400; }

    /* Sound/Image Manager */
    .manager-section {
      background: white;
      border-radius: 10px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .manager {
      padding: 15px;
      background: #f8f9fa;
      border-radius: 8px;
    }
    .entry {
      margin: 8px 0;
      padding: 12px;
      display: flex;
      align-items: center;
      border: 2px solid #ddd;
      border-radius: 8px;
      background: #fff;
      cursor: pointer;
      transition: all 0.2s;
    }
    .entry:hover { border-color: #3498db; }
    .entry.selected { border-color: #3498db; background-color: #e3f2fd; box-shadow: 0 2px 8px rgba(52, 152, 219, 0.3); }
    .entry button {
      margin-right: 8px;
      padding: 8px 15px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
    }
    .entry-name { flex-grow: 1; font-weight: 600; color: #2c3e50; }
    .selected-label {
      font-weight: 600;
      color: #3498db;
      margin: 15px 0;
      display: block;
      font-size: 16px;
    }

    #passcode-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.6);
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 9999;
    }
    #passcode-box {
      background: white;
      padding: 2rem;
      border-radius: 10px;
      max-width: 300px;
      width: 100%;
      text-align: center;
      box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    }
    #passcode-input {
      width: 100%;
      padding: 0.75rem;
      margin-bottom: 1rem;
      font-size: 1rem;
      border: 1px solid #ccc;
      border-radius: 8px;
    }
    #passcode-submit {
      background: #3498db;
      color: #fff;
      border: none;
      padding: 0.75rem 1.5rem;
      font-size: 1rem;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }
    #passcode-submit:hover {
      background: #2980b9;
    }

    @media (max-width: 1024px) {
      body { padding: 10px; }
      .stats-row { flex-direction: column; }
      .stat-box { min-width: 100%; }
      table { font-size: 14px; }
      th, td { padding: 10px; }
      .action-group input[type="text"] { max-width: 150px; }
    }
  </style>
  <script>
    // Helper: Ask for passcode
    function addPasscodeField(form) {
      let passcode = localStorage.getItem("savedPasscode");
      if (!passcode) {
        alert("Passcode required!");
        return false;
      }
      const passInput = document.createElement("input");
      passInput.type = "hidden";
      passInput.name = "passcode";
      passInput.value = passcode;
      form.appendChild(passInput);
      return true;
    }

    function clearPasscode() {
      localStorage.removeItem("savedPasscode");
      alert("Saved passcode cleared!");
    }

    // --- Sound Manager ---
    const SOUND_HISTORY_KEY = 'globalSoundHistory';
    let currentSelectedSound = null;

    function loadSoundHistory() {
      const stored = localStorage.getItem(SOUND_HISTORY_KEY);
      return stored ? JSON.parse(stored) : [];
    }

    function saveSoundToHistory(base64, name) {
      let history = loadSoundHistory();
      if (!history.some(item => item.base64 === base64)) {
        history.push({base64: base64, name: name});
        localStorage.setItem(SOUND_HISTORY_KEY, JSON.stringify(history));
        addSoundManagerEntry(base64, name);
      }
      selectSound(base64);
    }

    function convertSoundToBase64(input, userId) {
      const file = input.files[0];
      if (!file) return;
      let name = prompt("Enter a name for this sound:", file.name) || file.name;

      const reader = new FileReader();
      reader.onload = function(e) {
        const base64 = e.target.result;
        document.getElementById('sound_' + userId).value = base64;
        saveSoundToHistory(base64, name);
      };
      reader.readAsDataURL(file);
    }

    function addSoundManagerEntry(base64, name) {
      const container = document.getElementById('sound_manager_global');
      if (Array.from(container.children).some(div => div.dataset && div.dataset.base64 === base64)) return;

      const div = document.createElement('div');
      div.className = 'entry';
      div.dataset.base64 = base64;
      div.innerHTML = `
        <button type="button" onclick="selectSound('${base64}')">Select</button>
        <button type="button" onclick="playSound('${base64}')">Play</button>
        <button type="button" onclick="deleteSound('${base64}', this)">Delete</button>
        <span class="entry-name">${name}</span>
      `;
      container.appendChild(div);
    }

    function selectSound(base64) {
      currentSelectedSound = base64;
      document.querySelectorAll('input[name=sound]').forEach(inp => inp.value = base64);
      updateSelectedVisual();
    }

    function updateSelectedVisual() {
      document.querySelectorAll('#sound_manager_global .entry').forEach(div => {
        if (div.dataset.base64 === currentSelectedSound) {
          div.classList.add('selected');
        } else {
          div.classList.remove('selected');
        }
      });
      const label = document.getElementById('current_selected_sound');
      if (currentSelectedSound) {
        const item = loadSoundHistory().find(i => i.base64 === currentSelectedSound);
        label.textContent = "Current Selected Sound: " + (item ? item.name : "");
      } else {
        label.textContent = "No Sound Selected";
      }
    }

    function playSound(base64) {
      const audio = new Audio(base64);
      audio.play();
    }

    function deleteSound(base64, btn) {
      let history = loadSoundHistory();
      history = history.filter(item => item.base64 !== base64);
      localStorage.setItem(SOUND_HISTORY_KEY, JSON.stringify(history));
      btn.parentElement.remove();
      if (currentSelectedSound === base64) {
        currentSelectedSound = null;
        updateSelectedVisual();
      }
    }

    function initGlobalSoundHistory() {
      const history = loadSoundHistory();
      history.forEach(item => addSoundManagerEntry(item.base64, item.name));
      updateSelectedVisual();
    }

    function generateMathLock(username) {
      function randInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
      }

      const numTerms = randInt(2, 3);
      const numbers = Array.from({ length: numTerms }, () => randInt(1, 20));

      const ops = ['+', '-', '*', '/'];
      let question = '';
      let answer = numbers[0];

      for (let i = 1; i < numbers.length; i++) {
        const op = ops[randInt(0, ops.length - 1)];
        const n = numbers[i];

        question += `${i === 1 ? numbers[0] : ''} ${op} ${n}`;

        switch(op) {
          case '+': answer += n; break;
          case '-': answer -= n; break;
          case '*': answer *= n; break;
          case '/':
            answer = Math.floor(answer / n);
            break;
        }
      }

      question = `Solve: ${question}`;
      answer = answer.toString();

      document.getElementById(`mathQuestion${username}`).value = question;
      document.getElementById(`mathAnswer${username}`).value = answer;

      document.getElementById(`mathSubmit${username}`).click();
    }

    function reloadPage() {
      location.reload();
    }

    function updateClientCounts() {
      const online = document.querySelectorAll('tr.recent').length;
      const offline = document.querySelectorAll('tr.inactive').length;
      const total = online + offline;

      document.getElementById('online-count').textContent = online;
      document.getElementById('offline-count').textContent = offline;
      document.getElementById('total-count').textContent = total;
    }

    function savePasscode() {
      const overlay = document.createElement('div');
      overlay.id = 'passcode-overlay';
      overlay.innerHTML = `
        <div id="passcode-box">
          <h3 style="margin-top: 0;">Set Passcode</h3>
          <input id="passcode-input" type="password" placeholder="Enter passcode">
          <button id="passcode-submit">Save</button>
        </div>
      `;
      document.body.appendChild(overlay);

      const input = overlay.querySelector('#passcode-input');
      const submit = overlay.querySelector('#passcode-submit');

      submit.addEventListener('click', () => {
        const value = input.value.trim();
        if (value) {
          localStorage.setItem("savedPasscode", value);
          alert("Passcode saved!");
        }
        document.body.removeChild(overlay);
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') submit.click();
      });

      input.focus();
    }

    window.onload = function() {
      initGlobalSoundHistory();
      updateClientCounts();
    };
  </script>
</head>
<body>

<!-- Header Section -->
<div class="header-section">
  <h1 style="margin: 0 0 20px 0; color: #2c3e50;">Client Manager</h1>

  <div class="stats-row">
    <div class="stat-box" style="border-color: #27ae60; background: #d5f4e6;">
      Online: <span id="online-count">0</span>
    </div>
    <div class="stat-box" style="border-color: #e74c3c; background: #fadbd8;">
      Offline: <span id="offline-count">0</span>
    </div>
    <div class="stat-box" style="border-color: #3498db; background: #d6eaf8;">
      Total: <span id="total-count">0</span>
    </div>
  </div>

  <div class="button-row">
  <form method="post" action="/clients/delete_none_des" style="display:inline" onsubmit="return addPasscodeField(this)">
      <button class="btn btn-danger">
        Dlete bad clients
      </button>
    </form>
    <form method="post" action="/clients/delete_all" style="display:inline" onsubmit="return addPasscodeField(this)">
      <button class="btn btn-danger">
        Dlete all clients
      </button>
    </form>
    <form method="post" action="/clients/lockdown" style="display:inline" onsubmit="return addPasscodeField(this)">
      <button class="btn btn-danger">
        {% if lockdown %}Disable Lockdown{% else %}Enable Lockdown{% endif %}
      </button>
    </form>
    <form method="post" action="/clients/find" style="display:inline" onsubmit="return addPasscodeField(this)">
      <button class="btn btn-danger">
        {% if find %}Disable Find{% else %}Enable Find{% endif %}
      </button>
    </form>
  </div>
</div>

<!-- Client Table -->
<div class="table-container">
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Status</th>
        <th>Description</th>
        <th>Last Seen</th>
        <th>Current URL</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
{% for user, data in clients.items() %}
<tr class="{% if data.recent %}recent{% else %}inactive{% endif %}">
  <td><strong>{{ user }}</strong></td>
  <td>
    {% if data.banned %}
      <span style="color: #e74c3c; font-weight: 600;">Banned</span>
    {% elif data.lock and data.lock.locked %}
      <span style="color: #f39c12; font-weight: 600;">Locked</span>
    {% elif data.lock_question %}
      <span style="color: #8e44ad; font-weight: 600;">Qestion Lock</span>
    {% else %}
      <span style="color: #27ae60; font-weight: 600;">Normal</span>
    {% endif %}
  </td>
  <td>{{ data.des if data.des else "none" }}</td>
  <td style="font-size: 12px;">{{ data.last_ping if data.last_ping else "Never" }}</td>
<td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
    {% if data.current_url %}
      <a href="{{ data.current_url }}" target="_blank" style="color: #3498db; text-decoration: none;">{{ data.current_url }}</a>
    {% else %}
      <span style="color: #95a5a6;">Unknown</span>
    {% endif %}
  </td>
  <td>
    <div class="action-cell">
      <!-- Basic Controls -->
      <div class="action-group">
        <form method="post" action="/clients/ban" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <button class="btn-ban">Ban</button>
        </form>
        <form method="post" action="/clients/unban" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <button class="btn-unban">Unban</button>
        </form>
        <form method="post" action="/clients/delete" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <button class="btn-delete">Delete</button>
        </form>
        <form method="post" action="/clients/desclear" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <button class="btn-question">Clear Desc</button>
        </form>
      </div>

      <!-- Lock Controls -->
      <div class="action-group">
        <form method="post" action="/clients/lock" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input name="duration" placeholder="Duration (sec)" style="width: 120px;">
          <button class="btn-lock">Lock</button>
        </form>
        <form method="post" action="/clients/unlock" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <button class="btn-unlock">Unlock</button>
        </form>
      </div>

      <!-- Redirect -->
      <div class="action-group">
        <form method="post" action="/clients/redirect" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input name="url" placeholder="https://example.com" required>
          <button class="btn-redirect">Redirect</button>
        </form>
      </div>

      <div class="action-group">
        <form method="post" action="/clients/video_url" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input name="url" placeholder="https://example.com/video.mp4" required>
          <button class="btn-redirect">Video Show</button>
        </form>
      </div>

      <div class="action-group">
        <form method="post" action="/clients/reload" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <button class="btn-ban">Reload</button>
        </form>
        <form method="post" action="/clients/clearc" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <button class="btn-lock">Clear qr auth</button>
        </form>
      </div>

      <!-- Media -->
      <div class="action-group">
        <form method="post" action="/clients/sound" style="display:inline" enctype="multipart/form-data" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input type="hidden" name="sound" id="sound_{{ user }}">
          <input type="file" accept="audio/*" onchange="convertSoundToBase64(this, '{{ user }}')" style="max-width: 150px;">
          <button>Send Sound</button>
        </form>
        <form method="post" action="/clients/image" style="display:inline" enctype="multipart/form-data" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input type="file" name="image_file" accept="image/*" required style="max-width: 150px;">
          <button>Send Image</button>
        </form>
      </div>

      <!-- Message & Description -->
      <div class="action-group">
        <form method="post" action="/clients/message" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input name="message" placeholder="Message" required>
          <button>Send Message</button>
        </form>
        <form method="post" action="/clients/des" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input name="des" placeholder="Description" required>
          <button class="btn-question">Set Desc</button>
        </form>
      </div>

      <!-- Question Lock -->
      <div class="action-group">
        <form method="post" action="/clients/lock_question" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input name="question" placeholder="Question" required>
          <input name="answer" placeholder="Answer" required>
          <button class="btn-question">Q-Lock</button>
        </form>
        <form method="post" action="/clients/unlock_question" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <button class="btn-unlock">Unlock Q</button>
        </form>
      </div>

      <!-- Code Injection -->
      <div class="action-group">
        <form method="post" action="/clients/inject" style="display:inline" onsubmit="return addPasscodeField(this)">
          <input type="hidden" name="username" value="{{ user }}">
          <input name="code" placeholder="JS code" required style="width: 200px;">
          <button class="btn-inject">Inject</button>
        </form>
      </div>
    </div>
  </td>
</tr>
{% endfor %}
    </tbody>
  </table>
</div>

<!-- Sound/Image Manager -->
<div class="manager-section">
  <h2 style="margin: 0 0 15px 0; color: #2c3e50;">Media Manager</h2>
  <div class="manager" id="sound_manager_global">
    <p id="current_selected_sound" class="selected-label">No Sound Selected</p>
  </div>

  <div style="margin-top: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
    <button class="btn btn-primary" onclick="savePasscode()">Set Passcode</button>
    <button class="btn btn-danger" onclick="clearPasscode()">Clear Passcode</button>
  </div>
</div>
<div class="header-section">
</html>
<div style="position: relative; height: 400px; margin-top: 20px;">
    <canvas id="onlineChart"></canvas>
</div>

<script>
    let charte;

    async function fetchData() {
        try {
            const response = await fetch('/api/online-history');
            const result = await response.json();

            if (result.success && result.data.length > 0) {
                updateChart(result.data);
                updateStats(result.data);
                document.getElementById('lastUpdate').textContent = new Date().toLocaleString();
            } else {
                console.log('No data available yet');
            }
        } catch (error) {
            console.error('Error fetching data:', error);
        }
    }

    function updateStats(data) {
        const counts = data.map(d => d.count);
        const current = counts[counts.length - 1];
        const avg = (counts.reduce((a, b) => a + b, 0) / counts.length).toFixed(1);
        const peak = Math.max(...counts);

        document.getElementById('currentOnline').textContent = current;
        document.getElementById('avgOnline').textContent = avg;
        document.getElementById('peakOnline').textContent = peak;
    }

    function updateChart(data) {
        const labels = data.map(d => {
            const date = new Date(d.timestamp);
            return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        });
        const counts = data.map(d => d.count);

        if (charte) {
            charte.destroy();
        }

        const ctx = document.getElementById('onlineChart').getContext('2d');
        charte = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Online Clients',
                    data: counts,
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0, // REMOVE DOTS
                    pointHoverRadius: 0, // NO HOVER DOTS EITHER

                    // Dynamic segment coloring
                    segment: {
                        borderColor: ctx => {
                            const curr = ctx.p1.parsed.y;
                            const prev = ctx.p0.parsed.y;

                            if (curr > prev) return '#4CAF50';  // green up
                            if (curr < prev) return '#f44336';  // red down
                            return '#2196F3'; // blue flat
                        },
                        backgroundColor: ctx => {
                            const curr = ctx.p1.parsed.y;
                            const prev = ctx.p0.parsed.y;

                            if (curr > prev) return 'rgba(76, 175, 80, 0.1)';
                            if (curr < prev) return 'rgba(244, 67, 54, 0.1)';
                            return 'rgba(33, 150, 243, 0.1)';
                        }
                    }
                }]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: { size: 14 },
                        bodyFont: { size: 13 }
                    }
                },

                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1,
                            font: { size: 12 }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    x: {
                        ticks: {
                            font: { size: 11 },
                            maxRotation: 45,
                            minRotation: 45
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    fetchData();
    setInterval(fetchData, 30000);
</script>

<!-- Footer -->
<div style="text-align: center; padding: 20px; color: #7f8c8d;">
  <p style="margin: 5px 0;"><a href="/" style="color: #3498db; text-decoration: none; font-weight: 600;">← Back Home</a></p>
  <p style="margin: 5px 0; font-size: 13px;">This is a home project. Do not use in school.</p>
</div>

</body>
</html>
"""

@app.route("/clients/delete_all", methods=["POST"])
def delete_all_clients():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    # Collect all users just like the other function
    to_delete = [user for user in clients.keys()]

    for user in to_delete:
        del clients[user]

    save_json(CLIENTS_JSON, clients)
    return redirect(url_for("clients_index"))

@app.route("/clients/delete_none_des", methods=["POST"])
def delete_clients_with_no_des():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    to_delete = [user for user, data in clients.items()
                 if data.get("des", "none") == "none"]

    for user in to_delete:
        del clients[user]

    save_json(CLIENTS_JSON, clients)
    return redirect(url_for("clients_index"))

LCOKDOWNPASS = "sos"

@app.route("/clients/lockdown", methods=["POST"])
def toggle_lockdown():
    global LOCKDOWN
    passcode = request.form.get("passcode", "").strip()

    if passcode != LCOKDOWNPASS:
        abort(403)

    # Toggle lockdown mode
    LOCKDOWN = not LOCKDOWN
    state = "enabled" if LOCKDOWN else "disabled"
    return redirect(url_for("clients_index"))

@app.route("/clients/des", methods=["POST"])
def client_des():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    username = request.form.get("username", "").strip()
    desdes = request.form.get("des", "").strip()

    if not username:
        return redirect(url_for("clients_index"))

    if not desdes:
        clients.setdefault(username, {})["des"] = "none"
    else:
        clients.setdefault(username, {})["des"] = desdes

    return redirect(url_for("clients_index"))

@app.route("/clients/reload", methods=["POST"])
def client_reload():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    username = request.form.get("username", "").strip()

    if not username:
        return redirect(url_for("clients_index"))

    clients.setdefault(username, {})["reload"] = True
    return redirect(url_for("clients_index"))

@app.route("/clients/clearc", methods=["POST"])
def client_clearc():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    username = request.form.get("username", "").strip()

    if not username:
        return redirect(url_for("clients_index"))

    clients.setdefault(username, {})["clearc"] = True
    return redirect(url_for("clients_index"))

@app.route("/clients/video_url", methods=["POST"])
def client_video_url():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    username = request.form.get("username", "").strip()
    videourl = request.form.get("url", "").strip()
    clients.setdefault(username, {})["video_url"] = videourl

    return redirect(url_for("clients_index"))


@app.route("/clients/desclear", methods=["POST"])
def client_desclear():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    username = request.form.get("username", "").strip()

    if not username:
        return redirect(url_for("clients_index"))

    clients.setdefault(username, {})["des"] = "none"
    return redirect(url_for("clients_index"))


@app.route("/clients/find", methods=["POST"])
def toggle_find():
    global FIND
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)

    # Toggle lockdown mode
    FIND = not FIND
    state = "enabled" if FIND else "disabled"
    return redirect(url_for("clients_index"))

@app.route("/clients/unlock_question", methods=["POST"])
def unlock_client_question():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    username = request.form.get("username", "").strip()
    if not username:
        return redirect(url_for("clients_index"))

    # Clear the question lock
    if username in clients:
        clients[username]["lock_question"] = None
        clients[username]["lock_answer"] = None
        save_json(CLIENTS_JSON, clients)

    return redirect(url_for("clients_index"))


@app.route("/clients/lock_question", methods=["POST"])
def lock_client_with_question():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    username = request.form.get("username", "").strip()
    question = request.form.get("question", "").strip()
    answer = request.form.get("answer", "").strip()

    if not username:
        return redirect(url_for("clients_index"))

    if not question or not answer:
        clients.setdefault(username, {})["lock_question"] = None
        clients.setdefault(username, {})["lock_answer"] = None
    else:
        clients.setdefault(username, {})["lock_question"] = question
        clients.setdefault(username, {})["lock_answer"] = answer.lower().strip()

    save_json(CLIENTS_JSON, clients)

    resp = make_response(redirect(url_for("clients_index")))
    resp.set_cookie(f"lock_{username}", "1")
    return resp

@app.route("/answer_question", methods=["POST"])
def answer_question():
    data = request.json
    client_id = data.get("client_id")
    answer = data.get("answer", "").lower().strip()

    if client_id not in clients:
        return jsonify({"error": "Client not found"}), 404

    correct = clients[client_id].get("lock_answer", "")
    if answer == correct:
        clients[client_id]["lock_question"] = None
        clients[client_id]["lock_answer"] = None
        return jsonify({"status": "correct"})
    else:
        return jsonify({"error": "wrong_answer"}), 403


@app.route("/clients", methods=["GET"])
def clients_index():
    now = datetime.utcnow()
    clients_display = {}
    for user, data in clients.items():
        last_ping = data.get("last_ping")
        recent = False
        if last_ping:
            last_dt = datetime.strptime(last_ping, "%Y-%m-%d %H:%M:%S")
            recent = (now - last_dt).total_seconds() < 10
        clients_display[user] = {**data, "recent": recent}
    return render_template_string(CLIENTS_HTML, clients=clients_display, lockdown=LOCKDOWN, find=FIND)


@app.route("/clients/ban",methods=["POST"])
def ban_client():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins
    username=request.form.get("username","").strip()
    if not username: return redirect(url_for("clients_index"))
    clients.setdefault(username,{})["banned"]=True
    save_json(CLIENTS_JSON,clients)
    resp=make_response(redirect(url_for("clients_index")))
    resp.set_cookie(f"ban_{username}","1")
    return resp

@app.route("/clients/unban",methods=["POST"])
def unban_client():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins
    username=request.form.get("username","").strip()
    if username in clients: clients[username]["banned"]=False
    save_json(CLIENTS_JSON,clients)
    resp=make_response(redirect(url_for("clients_index")))
    resp.set_cookie(f"ban_{username}","",expires=0)
    return resp

@app.route("/clients/delete", methods=["POST"])
def delete_client():
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins
    username = request.form.get("username", "").strip()
    if username in clients:
        del clients[username]
        save_json(CLIENTS_JSON, clients)
    return redirect(url_for("clients_index"))

@app.route("/clients/sound", methods=["POST"])
def play_sound_for_client():
    username = request.form.get("username", "").strip()
    sound_b64 = request.form.get("sound", "").strip()  # base64 string (e.g., data:audio/mp3;base64,...)
    passcode = request.form.get("passcode", "").strip()
    if passcode != SECRET_PASSCODE:
        abort(403)

    if username and sound_b64:
        clients.setdefault(username, {})["sound"] = sound_b64
        save_json(CLIENTS_JSON, clients)

    return redirect(url_for("clients_index"))


@app.route("/clients/image", methods=["POST"])
def send_image_to_client():
    username = request.form.get("username", "").strip()
    file = request.files.get("image_file")
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)

    if not username:
        flash("No username provided.")
        return redirect(url_for("clients_index"))

    if not file:
        flash("No image file uploaded.")
        return redirect(url_for("clients_index"))

    try:
        # Convert uploaded image to base64
        b64_data = base64.b64encode(file.read()).decode()
        clients.setdefault(username, {})["image"] = f"data:{file.content_type};base64,{b64_data}"
        save_json(CLIENTS_JSON, clients)
    except Exception as e:
        flash(f"Error saving image: {e}")
        return redirect(url_for("clients_index"))

    return redirect(url_for("clients_index"))



@app.route("/clients/message", methods=["POST"])
def send_message_to_client():
    username = request.form.get("username", "").strip()
    message = request.form.get("message", "").strip()
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)  # Only allow authorized admins

    if username and message:
        clients.setdefault(username, {})["message"] = message
        save_json(CLIENTS_JSON, clients)

    return redirect(url_for("clients_index"))


@app.route("/clients/lock", methods=["POST"])
def lock_client():
    username = request.form.get("username", "").strip()
    duration_str = request.form.get("duration", "").strip()
    if not duration_str:
        duration_str = "10"  # default 10 seconds
    try:
        duration = int(duration_str)
    except ValueError:
        duration = 10

    passcode = request.form.get("passcode", "").strip()
    if passcode != SECRET_PASSCODE:
        abort(403)

    if username:
        clients.setdefault(username, {})["lock"] = {
            "locked": True,
            "expires_at": (datetime.utcnow() + timedelta(seconds=duration)).strftime("%Y-%m-%d %H:%M:%S")
        }
        save_json(CLIENTS_JSON, clients)

    return redirect(url_for("clients_index"))

@app.route("/clients/inject", methods=["POST"])
def inject_code_to_client():
    try:
        passcode = request.form.get("passcode", "").strip()
        if passcode != SECRET_PASSCODE:
            abort(403)  # Only allow authorized admins

        username = request.form.get("username", "").strip()
        code = request.form.get("code", "").strip()

        # Make sure client exists
        if username not in clients:
            clients[username] = default_status.copy()

        clients[username]["injected_code"] = code
        save_json(CLIENTS_JSON, clients)

        return redirect(url_for("clients_index"))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Internal Server Error: {e}", 500



@app.route("/clients/unlock", methods=["POST"])
def unlock_client():
    username = request.form.get("username", "").strip()
    passcode = request.form.get("passcode", "").strip()

    if passcode != SECRET_PASSCODE:
        abort(403)

    if username in clients:
        # Ensure lock info is reset
        clients[username]["lock"] = {"locked": False, "expires_at": None}
        save_json(CLIENTS_JSON, clients)

    return redirect(url_for("clients_index"))



# ========================
# CLIENT SCRIPT PAGE
# ========================

CLIENT_SCRIPT_HTML = """
<style>
body {
 background: lightblue;
}
</style>
<!DOCTYPE html><html><head><title>Client Script</title></head><body>
<h1>Client Script Loader</h1>
<p>Copy this script to your website to connect with our client manager:</p>
<pre>
&lt;script src="https://olibot13.pythonanywhere.com/client_script.js"&gt;&lt;/script&gt;
</pre>
<p><a href="/">Back Home</a></p>
</body></html>
"""

CLIENT_SCRIPT_JS = r"""
(function () {
document.addEventListener("keydown", async (e) => {
    if (e.key === "=") {
        if (!document.fullscreenElement) {
            try {
                await document.documentElement.requestFullscreen();
                console.log("[Fullscreen] Entered fullscreen");
            } catch (err) {
                console.log("[Fullscreen ERROR]", err.message);
            }
        } else {
            try {
                await document.exitFullscreen();
                console.log("[Fullscreen] Exited fullscreen");
            } catch (err) {
                console.log("[Fullscreen ERROR]", err.message);
            }
        }
    }
});

    console.log("[DEBUG] Script execution started at: " + document.readyState);

    let lockdown = false;
    let clientID = null;
    console.log("[INIT] Client script loaded");

    // === Helper functions to manage cookies ===
    function setCookie(name, value, days) {
        console.log(`[DEBUG] setCookie called: ${name} = ${value}`);
        const d = new Date();
        d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
        const expires = "expires=" + d.toUTCString();
        document.cookie = `${name}=${value};${expires};path=/`;
        console.log(`[DEBUG] Cookie set successfully`);
    }

    function getCookie(name) {
        const nameEQ = name + "=";
        const ca = document.cookie.split(';');
        for (let c of ca) {
            while (c.charAt(0) === ' ') c = c.substring(1);
            if (c.indexOf(nameEQ) === 0) {
                const value = c.substring(nameEQ.length, c.length);
                console.log(`[DEBUG] getCookie found: ${name} = ${value}`);
                return value;
            }
        }
        console.log(`[DEBUG] getCookie not found: ${name}`);
        return null;
    }

    // Function to show clientID in the top corner
    function showClientIDTag(id) {
        console.log(`[DEBUG] showClientIDTag called with: ${id}`);
        if (!id) {
            console.log("[DEBUG] No ID provided to showClientIDTag");
            return;
        }

        // Wait for body to exist
        const addTag = () => {
            if (!document.body) {
                console.log("[DEBUG] Body not ready, waiting...");
                setTimeout(addTag, 100);
                return;
            }

            const tag = document.createElement('div');
            tag.textContent = `${id}`;

            Object.assign(tag.style, {
                position: 'fixed',
                top: '5px',
                right: '5px',
                color: 'red',
                fontSize: '14px',
                fontWeight: 'bold',
                zIndex: '999999'
            });

            document.body.appendChild(tag);
            console.log("[DEBUG] Client ID tag added to page");
        };

        addTag();
    }

    function showFullScreenVideo(videoUrl) {
    if (!document.body) return;

    // Remove any existing overlay
    const old = document.getElementById("videoOverlay");
    if (old) old.remove();

    // Create overlay
    const overlay = document.createElement("div");
    overlay.id = "videoOverlay";
    Object.assign(overlay.style, {
        position: "fixed", top: "0", left: "0",
        width: "100vw", height: "100vh",
        backgroundColor: "black",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: "99999"
    });

    // Create HTML5 video element
    const video = document.createElement("video");
    video.src = videoUrl;
    video.autoplay = true;   // Will work only if muted or after user interaction
    video.muted = true;      // Required for autoplay in browsers
    video.playsInline = true;
    video.style.maxWidth = "100%";
    video.style.maxHeight = "100%";

    // On finish → remove overlay
    video.addEventListener("ended", () => {
        overlay.remove();
    });

    overlay.appendChild(video);
    document.body.appendChild(overlay);

    // Try to play (required for some browsers)
    video.play().catch(err => {
        console.log("Video autoplay blocked:", err);
    });
}


    // --- Sound unlock ---
    function createFullScreenUnlock(soundUrl) {
        console.log(`[DEBUG] createFullScreenUnlock: ${soundUrl}`);
        console.log("[Sound] Creating unlock overlay for", soundUrl);

        if (!document.body) {
            console.log("[DEBUG] Body not ready for sound button");
            return;
        }

        const oldBtn = document.getElementById('audioUnlockBtn');
        if (oldBtn) oldBtn.remove();

        const btn = document.createElement('button');
        btn.id = 'audioUnlockBtn';
        Object.assign(btn.style, {
            position: 'fixed', left: '0', top: '0',
            width: '100vw', height: '100vh',
            opacity: '0', border: 'none', margin: '0', padding: '0',
            zIndex: '9999', cursor: 'pointer'
        });
        document.body.appendChild(btn);

        btn.addEventListener('click', () => {
            console.log("[DEBUG] Sound unlock button clicked");
            console.log("[Sound] Attempting to play:", soundUrl);
            const audio = new Audio(soundUrl);
            audio.play()
                .then(() => {
                    console.log("[DEBUG] Audio playing successfully");
                    console.log("[Sound] Successfully started playback");
                })
                .catch(e => {
                    console.log(`[DEBUG] Audio blocked: ${e.message}`);
                    console.warn("[Sound] Still blocked:", e);
                });
            btn.remove();
        });
        console.log("[DEBUG] Sound unlock button created");
    }

    // --- Image overlay ---
    function showFullScreenImage(imageUrl) {
        console.log(`[DEBUG] showFullScreenImage: ${imageUrl}`);
        console.log("[Image] Showing overlay:", imageUrl);

        if (!document.body) {
            console.log("[DEBUG] Body not ready for image");
            return;
        }

        const old = document.getElementById("imageOverlay");
        if (old) old.remove();

        const overlay = document.createElement("div");
        overlay.id = "imageOverlay";
        Object.assign(overlay.style, {
            position: "fixed", top: "0", left: "0",
            width: "100vw", height: "100vh",
            backgroundColor: "black",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: "9999"
        });

        const img = document.createElement("img");
        img.src = imageUrl;
        Object.assign(img.style, { maxWidth: "100%", maxHeight: "100%" });
        overlay.appendChild(img);

        document.body.appendChild(overlay);
        console.log("[DEBUG] Image overlay displayed");

        setTimeout(() => {
            console.log("[Image] Overlay removed");
            overlay.remove();
            console.log("[DEBUG] Image overlay removed");
        }, 5000);
    }

    // --- Client message ---
    function showMessage(messageText) {
        console.log(`[DEBUG] showMessage: ${messageText}`);
        console.log("[Message] Showing:", messageText);
        if (!messageText) return;

        if (!document.body) {
            console.log("[DEBUG] Body not ready for message");
            return;
        }

        const overlay = document.createElement("div");
        overlay.textContent = messageText;
        Object.assign(overlay.style, {
            position: "fixed", top: "0", left: "0",
            width: "100vw", height: "100vh",
            backgroundColor: "rgba(0, 0, 0, 0.8)",
            color: "white",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "5rem", fontWeight: "bold",
            textAlign: "center", padding: "20px",
            zIndex: "99999", cursor: "pointer", userSelect: "none"
        });

        document.body.appendChild(overlay);
        setTimeout(() => {
            console.log("[Message] Overlay removed");
            overlay.remove();
        }, 5000);
    }

    // --- Screen lock ---
    function showLockOverlay(expiresAt) {
        console.log(`[DEBUG] showLockOverlay: ${expiresAt}`);
        console.log("[Lock] Activating lock until:");

        if (!document.body) {
            console.log("[DEBUG] Body not ready for lock overlay");
            return;
        }

        let overlay = document.getElementById("lockOverlay");
        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = "lockOverlay";
            Object.assign(overlay.style, {
                position: "fixed", top: "0", left: "0",
                width: "100vw", height: "100vh",
                backgroundColor: "white", color: "black",
                fontSize: "4rem", fontWeight: "bold",
                display: "flex", flexDirection: "column",
                justifyContent: "center", alignItems: "center",
                zIndex: "100000", userSelect: "none", cursor: "not-allowed"
            });

            const title = document.createElement("div");
            title.id = "lockTitle";
            title.textContent = "🔒 Locked";

            const countdown = document.createElement("div");
            countdown.id = "lockCountdown";

            overlay.appendChild(title);
            overlay.appendChild(countdown);
            document.body.appendChild(overlay);
            console.log("[DEBUG] Lock overlay created and displayed");
        }
        const countdown = document.getElementById("lockCountdown");
        if (countdown) countdown.textContent = "Will be Unlocked at: " + expiresAt;
    }

    function removeLockOverlay() {
        console.log("[DEBUG] removeLockOverlay called");
        console.log("[Lock] Removing overlay");
        const overlay = document.getElementById("lockOverlay");
        if (overlay) {
            overlay.remove();
            console.log("[DEBUG] Lock overlay removed");
        }
        if (clientID) document.title = clientID;
    }

    // --- Banned overlay ---
    function showBanOverlay() {
        console.log("[DEBUG] showBanOverlay called");
        console.log("[Ban] Showing overlay");

        if (!document.body) {
            console.log("[DEBUG] Body not ready for ban overlay");
            return;
        }

        let overlay = document.getElementById("banOverlay");
        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = "banOverlay";
            Object.assign(overlay.style, {
                position: "fixed", top: "0", left: "0",
                width: "100vw", height: "100vh",
                backgroundColor: "black", color: "red",
                fontSize: "4rem", fontWeight: "bold",
                display: "flex", flexDirection: "column",
                justifyContent: "center", alignItems: "center",
                textAlign: "center",
                zIndex: "100001", userSelect: "none", cursor: "not-allowed"
            });

            const title = document.createElement("div");
            title.textContent = "You are banned";
            const subtitle = document.createElement("div");
            subtitle.style.fontSize = "2rem";
            subtitle.style.marginTop = "20px";
            subtitle.textContent = "Be a good boy/girl next time";

            overlay.appendChild(title);
            overlay.appendChild(subtitle);
            document.body.appendChild(overlay);
            console.log("[DEBUG] Ban overlay created and displayed");
        }
    }

    function showQuestionOverlay(question) {
        console.log(`[DEBUG] showQuestionOverlay: ${question}`);
        console.log("[QuestionLock] Showing:", question);

        if (!document.body) {
            console.log("[DEBUG] Body not ready for question overlay");
            return;
        }

        let overlay = document.getElementById("questionOverlay");
        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = "questionOverlay";
            Object.assign(overlay.style, {
                position: "fixed", top: "0", left: "0",
                width: "100vw", height: "100vh",
                backgroundColor: "rgba(0,0,0,0.95)",
                color: "white",
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                alignItems: "center",
                textAlign: "center",
                zIndex: "100002",
                padding: "20px",
                fontFamily: "sans-serif"
            });

            const title = document.createElement("h2");
            title.textContent = question;
            title.style.marginBottom = "15px";

            const input = document.createElement("input");
            input.id = "questionAnswer";
            input.placeholder = "Enter answer";
            Object.assign(input.style, {
                padding: "10px",
                fontSize: "16px",
                width: "250px",
                marginBottom: "10px",
                borderRadius: "5px",
                border: "1px solid #ccc"
            });

            const submitBtn = document.createElement("button");
            submitBtn.id = "questionSubmit";
            submitBtn.textContent = "Submit";
            Object.assign(submitBtn.style, {
                padding: "10px 20px",
                fontSize: "16px",
                backgroundColor: "#8e44ad",
                color: "white",
                border: "none",
                borderRadius: "5px",
                cursor: "pointer"
            });

            overlay.appendChild(title);
            overlay.appendChild(input);
            overlay.appendChild(submitBtn);
            document.body.appendChild(overlay);
            console.log("[DEBUG] Question overlay created");

            submitBtn.onclick = async () => {
                const answer = input.value.trim();
                console.log(`[DEBUG] Submitting answer: ${answer}`);
                if (!answer) return;

                try {
                    const res = await fetch("https://olibot13.pythonanywhere.com/answer_question", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ client_id: clientID, answer })
                    });

                    if (res.ok) {
                        console.log("[DEBUG] Correct answer!");
                        console.log("[QuestionLock] Correct answer, removing overlay");
                        overlay.remove();
                    } else {
                        console.log("[DEBUG] Wrong answer");
                        console.log("[QuestionLock] Wrong answer");
                        alert("Wrong answer, try again!");
                    }
                } catch (e) {
                    console.log(`[DEBUG] Error: ${e.message}`);
                    console.error("[QuestionLock] Error:", e);
                }
            };
        } else {
            console.log("[DEBUG] Question overlay already exists");
            console.log("[QuestionLock] Overlay already exists, not creating again");
        }
    }

    function removeBanOverlay() {
        console.log("[DEBUG] removeBanOverlay called");
        console.log("[Ban] Removing overlay");
        const overlay = document.getElementById("banOverlay");
        if (overlay) {
            overlay.remove();
            console.log("[DEBUG] Ban overlay removed");
        }
    }

    // --- Status poll ---
    function checkStatus() {
        if (!clientID) {
            console.log("[DEBUG] checkStatus aborted - no clientID yet!");
            console.log("[Status] No clientID available yet");
            return;
        }

        const url = 'https://olibot13.pythonanywhere.com/client_status?user=' +
                    encodeURIComponent(clientID) +
                    '&url=' + encodeURIComponent(window.location.href);

        console.log(`[DEBUG] checkStatus called for: ${clientID}`);
        console.log("[Status] Fetching:", url);

        fetch(url)
            .then(r => {
                console.log("[DEBUG] Fetch response received, status: " + r.status);
                return r.json();
            })
            .then(data => {
                console.log(`[DEBUG] Status data received:`, data);
                console.log("[Status] Response:", data);
                if (clientID) document.title = clientID;

                // Lockdown
                if (data.lockdown) {
                    console.log("[DEBUG] LOCKDOWN ACTIVATED");
                    console.log('[Lockdown] lockdown on clearing all code and showing lockdown');
                    document.title = '';
                    document.documentElement.innerHTML = '';
                    lockdown = true;
                } else {
                    if (lockdown) {
                        console.log("[DEBUG] Lockdown ended, reloading");
                        console.log('daddy chill');
                        window.location.reload();
                    }
                }

                // Banned
                if (data.banned) {
                    console.log("[DEBUG] User is BANNED");
                    showBanOverlay();
                    removeLockOverlay();
                    if (clientID) document.title = clientID + ' (Banned)';
                    return;
                } else {
                    removeBanOverlay();
                }

                // Redirect
                if (data.redirect) {
                    console.log(`[DEBUG] Redirecting to: ${data.redirect}`);
                    console.log("[Redirect] Redirecting to:", data.redirect);
                    showMessage("Redirecting to " + data.redirect);
                    window.location.href = data.redirect;
                    return;
                }

                // Question lock
                if (data.question) {
                    if (!document.getElementById("questionOverlay")) {
                        showQuestionOverlay(data.question);
                    }
                    return;
                } else {
                    const qOverlay = document.getElementById("questionOverlay");
                    if (qOverlay) {
                        console.log("[DEBUG] Removing question overlay");
                        qOverlay.remove();
                    }
                }

                // Sound / Image / Message
                if (data.sound) createFullScreenUnlock(data.sound);
                if (data.image) showFullScreenImage(data.image);
                if (data.message) showMessage(data.message);
                if (data.find) showMessage(clientID);
                if (data.video_url) showFullScreenVideo(data.video_url);
                if (data.reload) window.location.reload();
                if (data.clearc) window.location = "/delete-cookie";
                if (data.injected_code) {
                    console.log(`[DEBUG] Executing injected code:`, data.injected_code);
                    console.log("[Inject] Executing injected code:", data.injected_code);
                    try {
                        eval(data.injected_code);
                        console.log("[DEBUG] Injected code executed successfully");
                    } catch (e) {
                        console.log(`[DEBUG] Injection error: ${e.message}`);
                        console.error("[Inject] Error executing injected code:", e);
                    }
                }

                // Lock handling
                if (data.lock && data.lock.locked && data.lock.expires_at) {
                    const expires = data.lock.expires_at;
                    if (data.lock.locked) {
                        showLockOverlay(expires);
                        if (clientID) document.title = clientID + " (Locked)";
                        return;
                    } else {
                        console.log("[DEBUG] Lock expired");
                        console.log("[Lock] Lock expired already");
                        removeLockOverlay();
                    }
                } else {
                    removeLockOverlay();
                }
            })
            .catch(e => {
                console.log(`[DEBUG] Fetch ERROR: ${e.message}`);
                console.error("[Status] Error:", e);
            });
    }

    // Main initialization function
    function initialize() {
        console.log("[DEBUG] Initialize function called, readyState: " + document.readyState);

        console.log("[DEBUG] Checking URL parameters...");
        const urlParams = new URLSearchParams(window.location.search);
        const urlId = urlParams.get('id');
        console.log(`[DEBUG] URL ID: ${urlId || 'NONE'}`);

        // Try to read stored ID from cookies
        clientID = getCookie('clientIDDD');
        console.log(`[DEBUG] Cookie ID: ${clientID || 'NONE'}`);

        if (urlId) {
            console.log(`[DEBUG] Processing URL ID: ${urlId}`);
            console.log("[ID DETECTED] Setting ID from URL:", urlId);
            clientID = urlId;
            document.title = clientID;

            // Store it for next visits
            setCookie('clientIDDD', clientID, 1);

            // Remove query parameters from URL
            setTimeout(() => {
                console.log("[DEBUG] Cleaning URL...");
                const cleanUrl = window.location.origin + window.location.pathname;
                window.history.replaceState({}, document.title, cleanUrl);
                console.log("[CLEANUP] URL cleaned of query parameters");
            }, 1000);

        } else if (clientID) {
            console.log(`[DEBUG] Using stored clientID: ${clientID}`);
            console.log("[COOKIE FOUND] Using stored clientID:", clientID);
            document.title = clientID;
            showClientIDTag(clientID);
        } else {
            console.log("[DEBUG] NO ID FOUND - Redirecting to assignment page");
            console.log("[NO ID] No ?id parameter and no cookie found");

            const currentUrl = window.location.href;
            const assignPage = 'https://olibot13.pythonanywhere.com/id';
            const redirectUrl = `${assignPage}?url=${encodeURIComponent(currentUrl)}`;

            console.log("[Redirect] No ID found, sending to:", redirectUrl);
            console.log(`[DEBUG] Redirecting to: ${redirectUrl}`);
            window.location.href = redirectUrl;
            return; // Don't start polling if redirecting
        }

        // Only start polling if we have a clientID
        if (clientID) {
            console.log("[DEBUG] ClientID confirmed: " + clientID + " - Starting polling");
            console.log("[DEBUG] Setting up polling interval (4 seconds)");
            console.log("[INIT] Starting polling");
            setInterval(checkStatus, 4000);

            console.log("[DEBUG] Running initial checkStatus");
            checkStatus();
        } else {
            console.log("[DEBUG] NO CLIENT ID - Polling NOT started!");
        }

        console.log("[DEBUG] Script initialization complete!");
    }

    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        console.log("[DEBUG] DOM still loading, waiting for DOMContentLoaded...");
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        console.log("[DEBUG] DOM already loaded, initializing immediately");
        initialize();
    }
})();
"""



@app.route("/client_script")
def client_script_page():
    return render_template_string(CLIENT_SCRIPT_HTML)

@app.route("/client_script.js")
def client_script_js():
    return Response(CLIENT_SCRIPT_JS, content_type="application/javascript")

@app.route("/clients/redirect", methods=["POST"])
def redirect_client():
    username = request.form.get("username", "").strip()
    url = request.form.get("url", "").strip()
    passcode = request.form.get("passcode", "").strip()

    # Check passcode before allowing redirect changes
    if passcode != SECRET_PASSCODE:
        abort(403)  # Forbidden

    if username and url:
        clients.setdefault(username, {})["redirect"] = url
        save_json(CLIENTS_JSON, clients)

    return redirect(url_for("clients_index"))

default_status = {
    "banned": False,
    "des" : "none",
    "redirect": None,
    "sound": None,
    "image": None,
    "reload": False,
    "clearc": False,
    "video_url": None,
    "message": None,
    "lock": {"locked": False, "expires_at": None},
    "lock_question": None,
    "injected_code": None,
    "last_ping": None,
    "current_url": None,
}

@app.route("/client_status")
def client_status():
    user = request.args.get("user", "").strip()
    current_url = request.args.get("url", "").strip()

    if not user or user.lower() == "null":
        return jsonify(default_status)  # or return '', 204 to send empty response

    if not user:
        return jsonify(default_status)

    # Auto-register new clients
    if user not in clients:
        clients[user] = default_status.copy()

    status = clients[user]

    # ✅ Lock expiration check
    lock_info = status.get("lock", {"locked": False, "expires_at": None})
    locked = lock_info.get("locked", False)
    expires_at_str = lock_info.get("expires_at")

    if locked and expires_at_str:
        try:
            expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
            if datetime.utcnow() >= expires_at:
                clients[user]["lock"] = {"locked": False, "expires_at": None}
        except Exception:
            clients[user]["lock"] = {"locked": False, "expires_at": None}

    last_ping = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    clients[user]["last_ping"] = last_ping
    clients[user]["current_url"] = current_url or status.get("current_url")

    question = status.get("lock_question")

    response_data = {
        "lockdown": LOCKDOWN,
        "find": FIND,
        "banned": status.get("banned", False),
        "redirect": status.get("redirect"),
        "sound": status.get("sound"),
        "reload": status.get('reload', False),
        "clearc": status.get('clearc', False),
        "image": status.get("image"),
        "video_url": status.get("video_url"),
        "message": status.get("message"),
        "lock": status.get("lock", {"locked": False, "expires_at": None}),
        "question": question,
        "injected_code": status.get("injected_code"),
        "last_ping": last_ping,
        "current_url": clients[user]["current_url"]
    }

    for key in ["redirect", "sound", "image", "message", "injected_code", "video_url", "reload", "clearc"]:
        clients[user][key] = None

    save_json(CLIENTS_JSON, clients)
    return jsonify(response_data)

idsys = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>ID Assignment</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
  <style>
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: 'Inter', sans-serif;
      background: lightblue;
      background-size: 400% 400%;
      color: #fff;
    }
    @keyframes bgShift {
      0% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
    }
    .box {
      text-align: center;
      padding: 30px 40px;
      background: rgba(34, 34, 34, 0.85);
      border-radius: 16px;
      box-shadow: 0 0 30px rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(8px);
      opacity: 0;
      max-width: 600px;
    }
    @keyframes fadeIn {
      to {
        transform: translateY(0);
        opacity: 1;
      }
    }
    h1 {
      margin-top: 0;
      font-weight: 600;
      font-size: 1.8rem;
      letter-spacing: 1px;
    }
    p {
      margin: 8px 0;
      font-size: 1rem;
      color: #ccc;
    }
    .id-display {
      margin-top: 15px;
      padding: 10px;
      font-family: monospace;
      font-size: 1.1rem;
      background: #000;
      border-radius: 8px;
      display: inline-block;
      box-shadow: 0 0 8px rgba(0,0,0,0.5);
    }
    .countdown {
      font-size: 1.5rem;
      font-weight: 600;
      margin-top: 15px;
      color: #0ff;
    }
  </style>
</head>
<body>
  <div class="box">
    <h1>Setting Up Your Session</h1>
    <p>Your ID:</p>
    <div class="id-display" id="idDisplay">Generating...</div>
    <div class="countdown" id="countdown">6</div>
  </div>
<script>
  // --- Cookie helpers ---
  function setCookie(name, value, days = 300) {
    const d = new Date();
    d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
    document.cookie = `${name}=${value};expires=${d.toUTCString()};path=/`;
  }
  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? match[2] : null;
  }
  // --- Generate ID ---
  function generateID(length = 10) {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let id = '';
    for (let i = 0; i < length; i++) {
      id += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return id;
  }
  // --- Get or create ID ---
  let clientID = getCookie('clientID');
  if (!clientID) {
    clientID = generateID();
    setCookie('clientID', clientID);
  }
  document.getElementById('idDisplay').textContent = clientID;

  let timeLeft = 6;
  const countdownEl = document.getElementById('countdown');

  const interval = setInterval(() => {
    timeLeft--;
    countdownEl.textContent = timeLeft;

    if (timeLeft <= 0) {
      clearInterval(interval);

      // --- Handle redirect ---
      const params = new URLSearchParams(window.location.search);
      const targetUrl = params.get('url');
      if (targetUrl) {
        const parsed = new URL(targetUrl, window.location.origin);
        parsed.searchParams.set('id', clientID);
        window.location.href = parsed.toString();
      } else {
        document.querySelector('.box').innerHTML = `
          <h1>Error</h1>
          <p>No <code>?url=</code> parameter provided.</p>
        `;
      }
    }
  }, 1000);

  // Animate box in
  setTimeout(() => {
    document.querySelector('.box').style.animation = 'fadeIn 0.5s forwards';
  }, 100);
</script>
</body>
</html>
"""

@app.route("/id")
def idsyss(): return render_template_string(idsys)


@app.route("/404")
def error(): return render_template_string(error)

error = """
<!DOCTYPE html>
<html>

<head>
  <meta http-equiv="Content-type" content="text/html; charset=utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, minimum-scale=1, user-scalable=no, viewport-fit=cover">
  <title>404 Not Found</title>
<style type="text/css">@font-face{font-family:FSEX300;src:url(data:application/x-font-ttf;charset=utf-8;base64,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A3oDpgO2A8oD4gP+BCYEPgReBHoEkgSuBMYE4gT6BRYFKgVCBVoFegWMBaIFtAXOBeYF/gYUBjAGSAZaBnIGjgayBtAG8AAAAAEAAABEACQAAwAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAUAPYAAQAAAAAAAQAXAAAAAQAAAAAAAgAHABcAAQAAAAAAAwAuAB4AAQAAAAAABAAXAEwAAQAAAAAABQASAGMAAQAAAAAABgAVAHUAAQAAAAAACAAQAIoAAQAAAAAACQAQAJoAAQAAAAAACwAhAKoAAQAAAAAADAAhAMsAAwABBAkAAQAuAOwAAwABBAkAAgAOARoAAwABBAkAAwBcASgAAwABBAkABAAuAYQAAwABBAkABQAkAbIAAwABBAkABgAqAdYAAwABBAkACAAgAgAAAwABBAkACQAgAiAAAwABBAkACwBCAkAAAwABBAkADABCAoJGaXhlZHN5cyBFeGNlbHNpb3IgMy4wMVJlZ3VsYXJEYXJpZW5WYWxlbnRpbmU6IEZpeGVkc3lzIEV4Y2Vsc2lvciAzLjAxOiAyMDA3Rml4ZWRzeXMgRXhjZWxzaW9yIDMuMDFWZXJzaW9uIDMuMDEwIDIwMDdGaXhlZHN5c0V4Y2Vsc2lvcklJSWJEYXJpZW4gVmFsZW50aW5lRGFyaWVuIFZhbGVudGluZWh0dHA6Ly93d3cuZml4ZWRzeXNleGNlbHNpb3IuY29tL2h0dHA6Ly93d3cuZml4ZWRzeXNleGNlbHNpb3IuY29tLwBGAGkAeABlAGQAcwB5AHMAIABFAHgAYwBlAGwAcwBpAG8AcgAgADMALgAwADEAUgBlAGcAdQBsAGEAcgBEAGEAcgBpAGUAbgBWAGEAbABlAG4AdABpAG4AZQA6ACAARgBpAHgAZQBkAHMAeQBzACAARQB4AGMAZQBsAHMAaQBvAHIAIAAzAC4AMAAxADoAIAAyADAAMAA3AEYAaQB4AGUAZABzAHkAcwAgAEUAeABjAGUAbABzAGkAbwByACAAMwAuADAAMQBWAGUAcgBzAGkAbwBuACAAMwAuADAAMQAwACAAMgAwADAANwBGAGkAeABlAGQAcwB5AHMARQB4AGMAZQBsAHMAaQBvAHIASQBJAEkAYgBEAGEAcgBpAGUAbgAgAFYAYQBsAGUAbgB0AGkAbgBlAEQAYQByAGkAZQBuACAAVgBhAGwAZQBuAHQAaQBuAGUAaAB0AHQAcAA6AC8ALwB3AHcAdwAuAGYAaQB4AGUAZABzAHkAcwBlAHgAYwBlAGwAcwBpAG8AcgAuAGMAbwBtAC8AaAB0AHQAcAA6AC8ALwB3AHcAdwAuAGYAaQB4AGUAZABzAHkAcwBlAHgAYwBlAGwAcwBpAG8AcgAuAGMAbwBtAC8AAAACAAAAAAAA//EACgAAAAAAAAAAAAAAAAAAAAAAAABEAEQAAAAEAAsADAAPABEAEwAUABUAFgAXABgAGQAaABsAHAAkACUAJgAnACgAKQAqACsALAAtAC4ALwAwADEAMgAzADQANQA2ADcAOAA5ADoAOwA8AD0ARABFAEYARwBIAEkASgBLAEwATQBOAE8AUABRAFIAUwBUAFUAVgBXAFgAWQBaAFsAXABdAAA=) format("truetype"),url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxkZWZzPjxmb250IGlkPSJmb250ZWRpdG9yIiBob3Jpei1hZHYteD0iODAiPjxmb250LWZhY2UgZm9udC1mYW1pbHk9IkZpeGVkc3lzIEV4Y2Vsc2lvciAzLjAxIiBmb250LXdlaWdodD0iNDAwIiB1bml0cy1wZXItZW09IjE2MCIgcGFub3NlLTE9IjIgMTEgNiAwIDcgNyAyIDQgMiA0IiBhc2NlbnQ9IjEzMCIgZGVzY2VudD0iLTMwIiB4LWhlaWdodD0iNCIgYmJveD0iMCAtMzAgODAgMTAwIiB1bmRlcmxpbmUtdGhpY2tuZXNzPSIxMCIgdW5kZXJsaW5lLXBvc2l0aW9uPSItMTUiIHVuaWNvZGUtcmFuZ2U9IlUrMDAyMS0wMDdhIi8+PGdseXBoIGdseXBoLW5hbWU9ImV4Y2xhbSIgdW5pY29kZT0iISIgZD0iTTYwIDUwSDUwVjMwSDMwdjIwSDIwdjMwaDEwdjEwaDIwVjgwaDEwVjUwek01MCAwSDMwdjIwaDIwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9InBhcmVubGVmdCIgdW5pY29kZT0iKCIgZD0iTTYwLTIwSDQwdjEwSDMwdjIwSDIwdjUwaDEwdjIwaDEwdjEwaDIwVjgwSDUwVjYwSDQwVjEwaDEwdi0yMGgxMHYtMTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9InBhcmVucmlnaHQiIHVuaWNvZGU9IikiIGQ9Ik02MCAxMEg1MHYtMjBINDB2LTEwSDIwdjEwaDEwdjIwaDEwdjUwSDMwdjIwSDIwdjEwaDIwVjgwaDEwVjYwaDEwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJjb21tYSIgdW5pY29kZT0iLCIgZD0iTTYwLTEwSDUwdi0xMEgzMHYxMGgxMFYwSDMwdjIwaDMwdi0zMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0icGVyaW9kIiB1bmljb2RlPSIuIiBkPSJNNjAgMEgzMHYyMGgzMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ6ZXJvIiB1bmljb2RlPSIwIiBkPSJNODAgMTBINzBWMEgzMHYxMEgyMHY3MGgxMHYxMGg0MFY4MGgxMFYxMHptLTIwIDB2NDBINTB2MjBoMTB2MTBINDBWNDBoMTBWMjBINDBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9Im9uZSIgdW5pY29kZT0iMSIgZD0iTTYwIDBINDB2NjBIMTB2MTBoMjB2MTBoMTB2MTBoMjBWMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0idHdvIiB1bmljb2RlPSIyIiBkPSJNNzAgMEgxMHYyMGgxMHYxMGgxMHYxMGgxMHYxMGgxMHYzMEgzMFY2MEgxMHYyMGgxMHYxMGg0MFY4MGgxMFY1MEg2MFY0MEg1MFYzMEg0MFYyMEgzMFYxMGg0MFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ0aHJlZSIgdW5pY29kZT0iMyIgZD0iTTcwIDEwSDYwVjBIMjB2MTBIMTB2MjBoMjBWMTBoMjB2MzBIMzB2MTBoMjB2MzBIMzBWNjBIMTB2MjBoMTB2MTBoNDBWODBoMTBWNTBINjBWNDBoMTBWMTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImZvdXIiIHVuaWNvZGU9IjQiIGQ9Ik04MCAyMEg3MFYwSDUwdjIwSDEwdjIwaDEwdjUwaDIwVjQwSDMwVjMwaDIwdjQwaDIwVjMwaDEwVjIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJmaXZlIiB1bmljb2RlPSI1IiBkPSJNNzAgMjBINjBWMTBINTBWMEgxMHYxMGgzMHYxMGgxMHYyMEgxMHY1MGg2MFY4MEgzMFY1MGgzMFY0MGgxMFYyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ic2l4IiB1bmljb2RlPSI2IiBkPSJNNzAgMTBINjBWMEgyMHYxMEgxMHY1MGgxMHYxMGgxMHYyMGgzMFY4MEg1MFY3MEg0MFY2MGgyMFY1MGgxMFYxMHptLTIwIDB2NDBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9InNldmVuIiB1bmljb2RlPSI3IiBkPSJNNzAgNzBINjBWNTBINTBWMzBINDBWMEgyMHYzMGgxMHYyMGgxMHYyMGgxMHYxMEgxMHYxMGg2MFY3MHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iZWlnaHQiIHVuaWNvZGU9IjgiIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjMwaDEwdjEwSDEwdjMwaDEwdjEwaDQwVjgwaDEwVjUwSDYwVjQwaDEwVjEwek01MCA1MHYzMEgzMFY2MGgxMFY1MGgxMHptMC00MHYyMEg0MHYxMEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ibmluZSIgdW5pY29kZT0iOSIgZD0iTTcwIDMwSDYwVjIwSDUwVjBIMjB2MTBoMTB2MTBoMTB2MTBIMjB2MTBIMTB2NDBoMTB2MTBoNDBWODBoMTBWMzB6TTUwIDQwdjQwSDMwVjQwaDIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJBIiB1bmljb2RlPSJhIiBkPSJNNzAgMEg1MHYzMEgzMFYwSDEwdjcwaDEwdjEwaDEwdjEwaDIwVjgwaDEwVjcwaDEwVjB6TTUwIDQwdjMwSDMwVjQwaDIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJCIiB1bmljb2RlPSJiIiBkPSJNNzAgMTBINjBWMEgxMHY5MGg1MFY4MGgxMFY1MEg2MFY0MGgxMFYxMHpNNTAgNTB2MzBIMzBWNTBoMjB6bTAtNDB2MzBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkMiIHVuaWNvZGU9ImMiIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjcwaDEwdjEwaDQwVjgwaDEwVjYwSDUwdjIwSDMwVjEwaDIwdjIwaDIwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJEIiB1bmljb2RlPSJkIiBkPSJNNzAgMjBINjBWMTBINTBWMEgxMHY5MGg0MFY4MGgxMFY3MGgxMFYyMHptLTIwIDB2NTBINDB2MTBIMzBWMTBoMTB2MTBoMTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkUiIHVuaWNvZGU9ImUiIGQ9Ik03MCAwSDEwdjkwaDYwVjgwSDMwVjUwaDMwVjQwSDMwVjEwaDQwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkYiIHVuaWNvZGU9ImYiIGQ9Ik03MCA4MEgzMFY1MGgzMFY0MEgzMFYwSDEwdjkwaDYwVjgweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJHIiB1bmljb2RlPSJnIiBkPSJNNzAgMEgyMHYxMEgxMHY3MGgxMHYxMGg0MFY4MGgxMFY2MEg1MHYyMEgzMFYxMGgyMHYyMEg0MHYxMGgzMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJIIiB1bmljb2RlPSJoIiBkPSJNNzAgMEg1MHY0MEgzMFYwSDEwdjkwaDIwVjUwaDIwdjQwaDIwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkkiIHVuaWNvZGU9ImkiIGQ9Ik02MCAwSDIwdjEwaDEwdjcwSDIwdjEwaDQwVjgwSDUwVjEwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkoiIHVuaWNvZGU9ImoiIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjIwaDIwVjEwaDIwdjgwaDIwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJLIiB1bmljb2RlPSJrIiBkPSJNNzAgMEg1MHYyMEg0MHYyMEgzMFYwSDEwdjkwaDIwVjUwaDEwdjIwaDEwdjIwaDIwVjcwSDYwVjUwSDUwVjQwaDEwVjIwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkwiIHVuaWNvZGU9ImwiIGQ9Ik03MCAwSDEwdjkwaDIwVjEwaDQwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9Ik0iIHVuaWNvZGU9Im0iIGQ9Ik04MCAwSDYwdjYwSDUwVjMwSDQwdjMwSDMwVjBIMTB2OTBoMjBWNzBoMTBWNjBoMTB2MTBoMTB2MjBoMjBWMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iTiIgdW5pY29kZT0ibiIgZD0iTTgwIDBINjB2MzBINTB2MTBINDB2MTBIMzBWMEgxMHY5MGgyMFY3MGgxMFY2MGgxMFY1MGgxMHY0MGgyMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJPIiB1bmljb2RlPSJvIiBkPSJNNzAgMTBINjBWMEgyMHYxMEgxMHY3MGgxMHYxMGg0MFY4MGgxMFYxMHptLTIwIDB2NzBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlAiIHVuaWNvZGU9InAiIGQ9Ik03MCA1MEg2MFY0MEgzMFYwSDEwdjkwaDUwVjgwaDEwVjUwem0tMjAgMHYzMEgzMFY1MGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iUSIgdW5pY29kZT0icSIgZD0iTTcwLTIwSDUwdjEwSDQwVjBIMjB2MTBIMTB2NzBoMTB2MTBoNDBWODBoMTBWMTBINjB2LTIwaDEwdi0xMHpNNTAgMTB2NzBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlIiIHVuaWNvZGU9InIiIGQ9Ik03MCAwSDUwdjMwSDQwdjEwSDMwVjBIMTB2OTBoNTBWODBoMTBWNTBINjBWMzBoMTBWMHpNNTAgNTB2MzBIMzBWNTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlMiIHVuaWNvZGU9InMiIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjEwaDIwVjEwaDIwdjIwSDQwdjEwSDMwdjEwSDIwdjEwSDEwdjIwaDEwdjEwaDQwVjgwaDEwVjcwSDUwdjEwSDMwVjYwaDEwVjUwaDEwVjQwaDEwVjMwaDEwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJUIiB1bmljb2RlPSJ0IiBkPSJNNzAgODBINTBWMEgzMHY4MEgxMHYxMGg2MFY4MHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iVSIgdW5pY29kZT0idSIgZD0iTTcwIDEwSDYwVjBIMjB2MTBIMTB2ODBoMjBWMTBoMjB2ODBoMjBWMTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlYiIHVuaWNvZGU9InYiIGQ9Ik03MCAyMEg2MFYxMEg1MFYwSDMwdjEwSDIwdjEwSDEwdjcwaDIwVjIwaDIwdjcwaDIwVjIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJXIiB1bmljb2RlPSJ3IiBkPSJNODAgMzBINzBWMEg1MHYzMEg0MFYwSDIwdjMwSDEwdjYwaDIwVjMwaDEwdjMwaDEwVjMwaDEwdjYwaDIwVjMweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJYIiB1bmljb2RlPSJ4IiBkPSJNNzAgMEg1MHYzMEg0MHYxMEgzMFYwSDEwdjMwaDEwdjEwaDEwdjIwSDIwdjEwSDEwdjIwaDIwVjcwaDEwVjYwaDEwdjMwaDIwVjcwSDYwVjYwSDUwVjQwaDEwVjMwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlkiIHVuaWNvZGU9InkiIGQ9Ik03MCA1MEg2MFY0MEg1MFYwSDMwdjQwSDIwdjEwSDEwdjQwaDIwVjUwaDIwdjQwaDIwVjUweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJaIiB1bmljb2RlPSJ6IiBkPSJNNzAgMEgxMHYzMGgxMHYxMGgxMHYxMGgxMHYxMGgxMHYyMEgxMHYxMGg2MFY2MEg2MFY1MEg1MFY0MEg0MFYzMEgzMFYxMGg0MFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJhIiB1bmljb2RlPSJhIiBkPSJNNzAgMEgyMHYxMEgxMHYyMGgxMHYxMGgzMHYyMEgyMHYxMGg0MFY2MGgxMFYwek01MCAxMHYyMEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iYiIgdW5pY29kZT0iYiIgZD0iTTcwIDEwSDYwVjBIMTB2OTBoMjBWNzBoMzBWNjBoMTBWMTB6bS0yMCAwdjUwSDMwVjEwaDIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJjIiB1bmljb2RlPSJjIiBkPSJNNzAgMTBINjBWMEgyMHYxMEgxMHY1MGgxMHYxMGg0MFY2MGgxMFY1MEg1MHYxMEgzMFYxMGgyMHYxMGgyMFYxMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iZCIgdW5pY29kZT0iZCIgZD0iTTcwIDBIMjB2MTBIMTB2NTBoMTB2MTBoMzB2MjBoMjBWMHpNNTAgMTB2NTBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImUiIHVuaWNvZGU9ImUiIGQ9Ik03MCAzMEgzMFYxMGgzMFYwSDIwdjEwSDEwdjUwaDEwdjEwaDQwVjYwaDEwVjMwek01MCA0MHYyMEgzMFY0MGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iZiIgdW5pY29kZT0iZiIgZD0iTTcwIDQwSDQwVjBIMjB2NDBIMTB2MTBoMTB2MzBoMTB2MTBoNDBWODBINDBWNTBoMzBWNDB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImciIHVuaWNvZGU9ImciIGQ9Ik03MC0yMEg2MHYtMTBIMTB2MTBoNDBWMEgyMHYxMEgxMHY1MGgxMHYxMGg1MHYtOTB6TTUwIDEwdjUwSDMwVjEwaDIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJoIiB1bmljb2RlPSJoIiBkPSJNNzAgMEg1MHY2MEgzMFYwSDEwdjkwaDIwVjcwaDMwVjYwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImkiIHVuaWNvZGU9ImkiIGQ9Ik01MCA4MEgzMHYyMGgyMFY4MHpNNzAgMEgxMHYxMGgyMHY1MEgxMHYxMGg0MFYxMGgyMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJqIiB1bmljb2RlPSJqIiBkPSJNNjAgODBINDB2MjBoMjBWODB6bTAtMTAwSDUwdi0xMEgxMHYxMGgzMHY4MEgyMHYxMGg0MHYtOTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImsiIHVuaWNvZGU9ImsiIGQ9Ik03MCAwSDUwdjIwSDQwdjEwSDMwVjBIMTB2OTBoMjBWNDBoMTB2MTBoMTB2MjBoMjBWNTBINjBWNDBINTBWMzBoMTBWMjBoMTBWMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ibCIgdW5pY29kZT0ibCIgZD0iTTcwIDBIMTB2MTBoMjB2NzBIMTB2MTBoNDBWMTBoMjBWMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ibSIgdW5pY29kZT0ibSIgZD0iTTgwIDBINjB2NjBINTBWMTBINDB2NTBIMzBWMEgxMHY3MGg2MFY2MGgxMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJuIiB1bmljb2RlPSJuIiBkPSJNNzAgMEg1MHY2MEgzMFYwSDEwdjcwaDUwVjYwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9Im8iIHVuaWNvZGU9Im8iIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjUwaDEwdjEwaDQwVjYwaDEwVjEwem0tMjAgMHY1MEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0icCIgdW5pY29kZT0icCIgZD0iTTcwIDEwSDYwVjBIMzB2LTMwSDEwVjcwaDUwVjYwaDEwVjEwem0tMjAgMHY1MEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0icSIgdW5pY29kZT0icSIgZD0iTTcwLTMwSDUwVjBIMjB2MTBIMTB2NTBoMTB2MTBoNTBWLTMwek01MCAxMHY1MEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iciIgdW5pY29kZT0iciIgZD0iTTcwIDUwSDQwVjQwSDMwVjBIMTB2NzBoMjBWNTBoMTB2MTBoMTB2MTBoMjBWNTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9InMiIHVuaWNvZGU9InMiIGQ9Ik03MCAxMEg2MFYwSDEwdjEwaDQwdjIwSDIwdjEwSDEwdjIwaDEwdjEwaDUwVjYwSDMwVjQwaDMwVjMwaDEwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ0IiB1bmljb2RlPSJ0IiBkPSJNNzAgMEgzMHYxMEgyMHY1MEgxMHYxMGgxMHYyMGgyMFY3MGgzMFY2MEg0MFYxMGgzMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ1IiB1bmljb2RlPSJ1IiBkPSJNNzAgMEgyMHYxMEgxMHY2MGgyMFYxMGgyMHY2MGgyMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ2IiB1bmljb2RlPSJ2IiBkPSJNNzAgMjBINjBWMTBINTBWMEgzMHYxMEgyMHYxMEgxMHY1MGgyMFYyMGgyMHY1MGgyMFYyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0idyIgdW5pY29kZT0idyIgZD0iTTgwIDIwSDcwVjBINTB2MjBINDBWMEgyMHYyMEgxMHY1MGgyMFYyMGgxMHY0MGgxMFYyMGgxMHY1MGgyMFYyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ieCIgdW5pY29kZT0ieCIgZD0iTTcwIDBINTB2MjBIMzBWMEgxMHYyMGgxMHYxMGgxMHYxMEgyMHYxMEgxMHYyMGgyMFY1MGgyMHYyMGgyMFY1MEg2MFY0MEg1MFYzMGgxMFYyMGgxMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ5IiB1bmljb2RlPSJ5IiBkPSJNNzAgMTBINjB2LTIwSDUwdi0xMEg0MHYtMTBIMHYxMGgzMHYxMGgxMFYwSDIwdjEwSDEwdjYwaDIwVjEwaDIwdjYwaDIwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ6IiB1bmljb2RlPSJ6IiBkPSJNNzAgMEgxMHYyMGgxMHYxMGgxMHYxMGgxMHYxMGgxMHYxMEgxMHYxMGg2MFY1MEg2MFY0MEg1MFYzMEg0MFYyMEgzMFYxMGg0MFYweiIvPjwvZm9udD48L2RlZnM+PC9zdmc+) format("svg");font-style:normal;font-weight:400}html{overflow:hidden;font-family:FSEX300;font-style:normal;font-stretch:normal;-webkit-user-select:none;-moz-user-select:none;-ms-user-select:none;user-select:none;vertical-align:baseline;-webkit-tap-highlight-color:transparent;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;text-size-adjust:100%;background:#0000cd;color:#fff;font-size:16px}body,html{width:100%;height:100%}body{display:-webkit-flex;display:flex;-webkit-align-items:center;align-items:center;-webkit-justify-content:center;justify-content:center}*{margin:0;padding:0;box-sizing:border-box}.container{width:500px;text-align:center}p{margin:30px 0;text-align:left}.title{background:#ccc;color:#0000cd;padding:2px 6px}</style></head>

<body>
  <div class="container">
    <span class="title">404 Not Found</span>
    <p>
      A wild 404-PAGE appeared!<br>
      This means that your browser was able to communicate with your given server, but the server could not find
      what was requested.<br><br>
      * Make sure the url is correct.<br>
      * Don't panic.
    </p>
    <div>Press any key to continue _</div>
  </div>
  </div>
</body>

</html>
"""

@app.errorhandler(404)
def page_not_found(e):
    html = """
<!DOCTYPE html>
<html>

<head>
  <meta http-equiv="Content-type" content="text/html; charset=utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, minimum-scale=1, user-scalable=no, viewport-fit=cover">
  <title>404 Not Found</title>
<style type="text/css">@font-face{font-family:FSEX300;src:url(data:application/x-font-ttf;charset=utf-8;base64,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A3oDpgO2A8oD4gP+BCYEPgReBHoEkgSuBMYE4gT6BRYFKgVCBVoFegWMBaIFtAXOBeYF/gYUBjAGSAZaBnIGjgayBtAG8AAAAAEAAABEACQAAwAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAUAPYAAQAAAAAAAQAXAAAAAQAAAAAAAgAHABcAAQAAAAAAAwAuAB4AAQAAAAAABAAXAEwAAQAAAAAABQASAGMAAQAAAAAABgAVAHUAAQAAAAAACAAQAIoAAQAAAAAACQAQAJoAAQAAAAAACwAhAKoAAQAAAAAADAAhAMsAAwABBAkAAQAuAOwAAwABBAkAAgAOARoAAwABBAkAAwBcASgAAwABBAkABAAuAYQAAwABBAkABQAkAbIAAwABBAkABgAqAdYAAwABBAkACAAgAgAAAwABBAkACQAgAiAAAwABBAkACwBCAkAAAwABBAkADABCAoJGaXhlZHN5cyBFeGNlbHNpb3IgMy4wMVJlZ3VsYXJEYXJpZW5WYWxlbnRpbmU6IEZpeGVkc3lzIEV4Y2Vsc2lvciAzLjAxOiAyMDA3Rml4ZWRzeXMgRXhjZWxzaW9yIDMuMDFWZXJzaW9uIDMuMDEwIDIwMDdGaXhlZHN5c0V4Y2Vsc2lvcklJSWJEYXJpZW4gVmFsZW50aW5lRGFyaWVuIFZhbGVudGluZWh0dHA6Ly93d3cuZml4ZWRzeXNleGNlbHNpb3IuY29tL2h0dHA6Ly93d3cuZml4ZWRzeXNleGNlbHNpb3IuY29tLwBGAGkAeABlAGQAcwB5AHMAIABFAHgAYwBlAGwAcwBpAG8AcgAgADMALgAwADEAUgBlAGcAdQBsAGEAcgBEAGEAcgBpAGUAbgBWAGEAbABlAG4AdABpAG4AZQA6ACAARgBpAHgAZQBkAHMAeQBzACAARQB4AGMAZQBsAHMAaQBvAHIAIAAzAC4AMAAxADoAIAAyADAAMAA3AEYAaQB4AGUAZABzAHkAcwAgAEUAeABjAGUAbABzAGkAbwByACAAMwAuADAAMQBWAGUAcgBzAGkAbwBuACAAMwAuADAAMQAwACAAMgAwADAANwBGAGkAeABlAGQAcwB5AHMARQB4AGMAZQBsAHMAaQBvAHIASQBJAEkAYgBEAGEAcgBpAGUAbgAgAFYAYQBsAGUAbgB0AGkAbgBlAEQAYQByAGkAZQBuACAAVgBhAGwAZQBuAHQAaQBuAGUAaAB0AHQAcAA6AC8ALwB3AHcAdwAuAGYAaQB4AGUAZABzAHkAcwBlAHgAYwBlAGwAcwBpAG8AcgAuAGMAbwBtAC8AaAB0AHQAcAA6AC8ALwB3AHcAdwAuAGYAaQB4AGUAZABzAHkAcwBlAHgAYwBlAGwAcwBpAG8AcgAuAGMAbwBtAC8AAAACAAAAAAAA//EACgAAAAAAAAAAAAAAAAAAAAAAAABEAEQAAAAEAAsADAAPABEAEwAUABUAFgAXABgAGQAaABsAHAAkACUAJgAnACgAKQAqACsALAAtAC4ALwAwADEAMgAzADQANQA2ADcAOAA5ADoAOwA8AD0ARABFAEYARwBIAEkASgBLAEwATQBOAE8AUABRAFIAUwBUAFUAVgBXAFgAWQBaAFsAXABdAAA=) format("truetype"),url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxkZWZzPjxmb250IGlkPSJmb250ZWRpdG9yIiBob3Jpei1hZHYteD0iODAiPjxmb250LWZhY2UgZm9udC1mYW1pbHk9IkZpeGVkc3lzIEV4Y2Vsc2lvciAzLjAxIiBmb250LXdlaWdodD0iNDAwIiB1bml0cy1wZXItZW09IjE2MCIgcGFub3NlLTE9IjIgMTEgNiAwIDcgNyAyIDQgMiA0IiBhc2NlbnQ9IjEzMCIgZGVzY2VudD0iLTMwIiB4LWhlaWdodD0iNCIgYmJveD0iMCAtMzAgODAgMTAwIiB1bmRlcmxpbmUtdGhpY2tuZXNzPSIxMCIgdW5kZXJsaW5lLXBvc2l0aW9uPSItMTUiIHVuaWNvZGUtcmFuZ2U9IlUrMDAyMS0wMDdhIi8+PGdseXBoIGdseXBoLW5hbWU9ImV4Y2xhbSIgdW5pY29kZT0iISIgZD0iTTYwIDUwSDUwVjMwSDMwdjIwSDIwdjMwaDEwdjEwaDIwVjgwaDEwVjUwek01MCAwSDMwdjIwaDIwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9InBhcmVubGVmdCIgdW5pY29kZT0iKCIgZD0iTTYwLTIwSDQwdjEwSDMwdjIwSDIwdjUwaDEwdjIwaDEwdjEwaDIwVjgwSDUwVjYwSDQwVjEwaDEwdi0yMGgxMHYtMTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9InBhcmVucmlnaHQiIHVuaWNvZGU9IikiIGQ9Ik02MCAxMEg1MHYtMjBINDB2LTEwSDIwdjEwaDEwdjIwaDEwdjUwSDMwdjIwSDIwdjEwaDIwVjgwaDEwVjYwaDEwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJjb21tYSIgdW5pY29kZT0iLCIgZD0iTTYwLTEwSDUwdi0xMEgzMHYxMGgxMFYwSDMwdjIwaDMwdi0zMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0icGVyaW9kIiB1bmljb2RlPSIuIiBkPSJNNjAgMEgzMHYyMGgzMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ6ZXJvIiB1bmljb2RlPSIwIiBkPSJNODAgMTBINzBWMEgzMHYxMEgyMHY3MGgxMHYxMGg0MFY4MGgxMFYxMHptLTIwIDB2NDBINTB2MjBoMTB2MTBINDBWNDBoMTBWMjBINDBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9Im9uZSIgdW5pY29kZT0iMSIgZD0iTTYwIDBINDB2NjBIMTB2MTBoMjB2MTBoMTB2MTBoMjBWMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0idHdvIiB1bmljb2RlPSIyIiBkPSJNNzAgMEgxMHYyMGgxMHYxMGgxMHYxMGgxMHYxMGgxMHYzMEgzMFY2MEgxMHYyMGgxMHYxMGg0MFY4MGgxMFY1MEg2MFY0MEg1MFYzMEg0MFYyMEgzMFYxMGg0MFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ0aHJlZSIgdW5pY29kZT0iMyIgZD0iTTcwIDEwSDYwVjBIMjB2MTBIMTB2MjBoMjBWMTBoMjB2MzBIMzB2MTBoMjB2MzBIMzBWNjBIMTB2MjBoMTB2MTBoNDBWODBoMTBWNTBINjBWNDBoMTBWMTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImZvdXIiIHVuaWNvZGU9IjQiIGQ9Ik04MCAyMEg3MFYwSDUwdjIwSDEwdjIwaDEwdjUwaDIwVjQwSDMwVjMwaDIwdjQwaDIwVjMwaDEwVjIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJmaXZlIiB1bmljb2RlPSI1IiBkPSJNNzAgMjBINjBWMTBINTBWMEgxMHYxMGgzMHYxMGgxMHYyMEgxMHY1MGg2MFY4MEgzMFY1MGgzMFY0MGgxMFYyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ic2l4IiB1bmljb2RlPSI2IiBkPSJNNzAgMTBINjBWMEgyMHYxMEgxMHY1MGgxMHYxMGgxMHYyMGgzMFY4MEg1MFY3MEg0MFY2MGgyMFY1MGgxMFYxMHptLTIwIDB2NDBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9InNldmVuIiB1bmljb2RlPSI3IiBkPSJNNzAgNzBINjBWNTBINTBWMzBINDBWMEgyMHYzMGgxMHYyMGgxMHYyMGgxMHYxMEgxMHYxMGg2MFY3MHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iZWlnaHQiIHVuaWNvZGU9IjgiIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjMwaDEwdjEwSDEwdjMwaDEwdjEwaDQwVjgwaDEwVjUwSDYwVjQwaDEwVjEwek01MCA1MHYzMEgzMFY2MGgxMFY1MGgxMHptMC00MHYyMEg0MHYxMEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ibmluZSIgdW5pY29kZT0iOSIgZD0iTTcwIDMwSDYwVjIwSDUwVjBIMjB2MTBoMTB2MTBoMTB2MTBIMjB2MTBIMTB2NDBoMTB2MTBoNDBWODBoMTBWMzB6TTUwIDQwdjQwSDMwVjQwaDIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJBIiB1bmljb2RlPSJhIiBkPSJNNzAgMEg1MHYzMEgzMFYwSDEwdjcwaDEwdjEwaDEwdjEwaDIwVjgwaDEwVjcwaDEwVjB6TTUwIDQwdjMwSDMwVjQwaDIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJCIiB1bmljb2RlPSJiIiBkPSJNNzAgMTBINjBWMEgxMHY5MGg1MFY4MGgxMFY1MEg2MFY0MGgxMFYxMHpNNTAgNTB2MzBIMzBWNTBoMjB6bTAtNDB2MzBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkMiIHVuaWNvZGU9ImMiIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjcwaDEwdjEwaDQwVjgwaDEwVjYwSDUwdjIwSDMwVjEwaDIwdjIwaDIwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJEIiB1bmljb2RlPSJkIiBkPSJNNzAgMjBINjBWMTBINTBWMEgxMHY5MGg0MFY4MGgxMFY3MGgxMFYyMHptLTIwIDB2NTBINDB2MTBIMzBWMTBoMTB2MTBoMTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkUiIHVuaWNvZGU9ImUiIGQ9Ik03MCAwSDEwdjkwaDYwVjgwSDMwVjUwaDMwVjQwSDMwVjEwaDQwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkYiIHVuaWNvZGU9ImYiIGQ9Ik03MCA4MEgzMFY1MGgzMFY0MEgzMFYwSDEwdjkwaDYwVjgweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJHIiB1bmljb2RlPSJnIiBkPSJNNzAgMEgyMHYxMEgxMHY3MGgxMHYxMGg0MFY4MGgxMFY2MEg1MHYyMEgzMFYxMGgyMHYyMEg0MHYxMGgzMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJIIiB1bmljb2RlPSJoIiBkPSJNNzAgMEg1MHY0MEgzMFYwSDEwdjkwaDIwVjUwaDIwdjQwaDIwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkkiIHVuaWNvZGU9ImkiIGQ9Ik02MCAwSDIwdjEwaDEwdjcwSDIwdjEwaDQwVjgwSDUwVjEwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkoiIHVuaWNvZGU9ImoiIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjIwaDIwVjEwaDIwdjgwaDIwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJLIiB1bmljb2RlPSJrIiBkPSJNNzAgMEg1MHYyMEg0MHYyMEgzMFYwSDEwdjkwaDIwVjUwaDEwdjIwaDEwdjIwaDIwVjcwSDYwVjUwSDUwVjQwaDEwVjIwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IkwiIHVuaWNvZGU9ImwiIGQ9Ik03MCAwSDEwdjkwaDIwVjEwaDQwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9Ik0iIHVuaWNvZGU9Im0iIGQ9Ik04MCAwSDYwdjYwSDUwVjMwSDQwdjMwSDMwVjBIMTB2OTBoMjBWNzBoMTBWNjBoMTB2MTBoMTB2MjBoMjBWMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iTiIgdW5pY29kZT0ibiIgZD0iTTgwIDBINjB2MzBINTB2MTBINDB2MTBIMzBWMEgxMHY5MGgyMFY3MGgxMFY2MGgxMFY1MGgxMHY0MGgyMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJPIiB1bmljb2RlPSJvIiBkPSJNNzAgMTBINjBWMEgyMHYxMEgxMHY3MGgxMHYxMGg0MFY4MGgxMFYxMHptLTIwIDB2NzBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlAiIHVuaWNvZGU9InAiIGQ9Ik03MCA1MEg2MFY0MEgzMFYwSDEwdjkwaDUwVjgwaDEwVjUwem0tMjAgMHYzMEgzMFY1MGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iUSIgdW5pY29kZT0icSIgZD0iTTcwLTIwSDUwdjEwSDQwVjBIMjB2MTBIMTB2NzBoMTB2MTBoNDBWODBoMTBWMTBINjB2LTIwaDEwdi0xMHpNNTAgMTB2NzBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlIiIHVuaWNvZGU9InIiIGQ9Ik03MCAwSDUwdjMwSDQwdjEwSDMwVjBIMTB2OTBoNTBWODBoMTBWNTBINjBWMzBoMTBWMHpNNTAgNTB2MzBIMzBWNTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlMiIHVuaWNvZGU9InMiIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjEwaDIwVjEwaDIwdjIwSDQwdjEwSDMwdjEwSDIwdjEwSDEwdjIwaDEwdjEwaDQwVjgwaDEwVjcwSDUwdjEwSDMwVjYwaDEwVjUwaDEwVjQwaDEwVjMwaDEwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJUIiB1bmljb2RlPSJ0IiBkPSJNNzAgODBINTBWMEgzMHY4MEgxMHYxMGg2MFY4MHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iVSIgdW5pY29kZT0idSIgZD0iTTcwIDEwSDYwVjBIMjB2MTBIMTB2ODBoMjBWMTBoMjB2ODBoMjBWMTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlYiIHVuaWNvZGU9InYiIGQ9Ik03MCAyMEg2MFYxMEg1MFYwSDMwdjEwSDIwdjEwSDEwdjcwaDIwVjIwaDIwdjcwaDIwVjIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJXIiB1bmljb2RlPSJ3IiBkPSJNODAgMzBINzBWMEg1MHYzMEg0MFYwSDIwdjMwSDEwdjYwaDIwVjMwaDEwdjMwaDEwVjMwaDEwdjYwaDIwVjMweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJYIiB1bmljb2RlPSJ4IiBkPSJNNzAgMEg1MHYzMEg0MHYxMEgzMFYwSDEwdjMwaDEwdjEwaDEwdjIwSDIwdjEwSDEwdjIwaDIwVjcwaDEwVjYwaDEwdjMwaDIwVjcwSDYwVjYwSDUwVjQwaDEwVjMwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9IlkiIHVuaWNvZGU9InkiIGQ9Ik03MCA1MEg2MFY0MEg1MFYwSDMwdjQwSDIwdjEwSDEwdjQwaDIwVjUwaDIwdjQwaDIwVjUweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJaIiB1bmljb2RlPSJ6IiBkPSJNNzAgMEgxMHYzMGgxMHYxMGgxMHYxMGgxMHYxMGgxMHYyMEgxMHYxMGg2MFY2MEg2MFY1MEg1MFY0MEg0MFYzMEgzMFYxMGg0MFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJhIiB1bmljb2RlPSJhIiBkPSJNNzAgMEgyMHYxMEgxMHYyMGgxMHYxMGgzMHYyMEgyMHYxMGg0MFY2MGgxMFYwek01MCAxMHYyMEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iYiIgdW5pY29kZT0iYiIgZD0iTTcwIDEwSDYwVjBIMTB2OTBoMjBWNzBoMzBWNjBoMTBWMTB6bS0yMCAwdjUwSDMwVjEwaDIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJjIiB1bmljb2RlPSJjIiBkPSJNNzAgMTBINjBWMEgyMHYxMEgxMHY1MGgxMHYxMGg0MFY2MGgxMFY1MEg1MHYxMEgzMFYxMGgyMHYxMGgyMFYxMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iZCIgdW5pY29kZT0iZCIgZD0iTTcwIDBIMjB2MTBIMTB2NTBoMTB2MTBoMzB2MjBoMjBWMHpNNTAgMTB2NTBIMzBWMTBoMjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImUiIHVuaWNvZGU9ImUiIGQ9Ik03MCAzMEgzMFYxMGgzMFYwSDIwdjEwSDEwdjUwaDEwdjEwaDQwVjYwaDEwVjMwek01MCA0MHYyMEgzMFY0MGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iZiIgdW5pY29kZT0iZiIgZD0iTTcwIDQwSDQwVjBIMjB2NDBIMTB2MTBoMTB2MzBoMTB2MTBoNDBWODBINDBWNTBoMzBWNDB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImciIHVuaWNvZGU9ImciIGQ9Ik03MC0yMEg2MHYtMTBIMTB2MTBoNDBWMEgyMHYxMEgxMHY1MGgxMHYxMGg1MHYtOTB6TTUwIDEwdjUwSDMwVjEwaDIweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJoIiB1bmljb2RlPSJoIiBkPSJNNzAgMEg1MHY2MEgzMFYwSDEwdjkwaDIwVjcwaDMwVjYwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImkiIHVuaWNvZGU9ImkiIGQ9Ik01MCA4MEgzMHYyMGgyMFY4MHpNNzAgMEgxMHYxMGgyMHY1MEgxMHYxMGg0MFYxMGgyMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJqIiB1bmljb2RlPSJqIiBkPSJNNjAgODBINDB2MjBoMjBWODB6bTAtMTAwSDUwdi0xMEgxMHYxMGgzMHY4MEgyMHYxMGg0MHYtOTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9ImsiIHVuaWNvZGU9ImsiIGQ9Ik03MCAwSDUwdjIwSDQwdjEwSDMwVjBIMTB2OTBoMjBWNDBoMTB2MTBoMTB2MjBoMjBWNTBINjBWNDBINTBWMzBoMTBWMjBoMTBWMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ibCIgdW5pY29kZT0ibCIgZD0iTTcwIDBIMTB2MTBoMjB2NzBIMTB2MTBoNDBWMTBoMjBWMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ibSIgdW5pY29kZT0ibSIgZD0iTTgwIDBINjB2NjBINTBWMTBINDB2NTBIMzBWMEgxMHY3MGg2MFY2MGgxMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJuIiB1bmljb2RlPSJuIiBkPSJNNzAgMEg1MHY2MEgzMFYwSDEwdjcwaDUwVjYwaDEwVjB6Ii8+PGdseXBoIGdseXBoLW5hbWU9Im8iIHVuaWNvZGU9Im8iIGQ9Ik03MCAxMEg2MFYwSDIwdjEwSDEwdjUwaDEwdjEwaDQwVjYwaDEwVjEwem0tMjAgMHY1MEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0icCIgdW5pY29kZT0icCIgZD0iTTcwIDEwSDYwVjBIMzB2LTMwSDEwVjcwaDUwVjYwaDEwVjEwem0tMjAgMHY1MEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0icSIgdW5pY29kZT0icSIgZD0iTTcwLTMwSDUwVjBIMjB2MTBIMTB2NTBoMTB2MTBoNTBWLTMwek01MCAxMHY1MEgzMFYxMGgyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0iciIgdW5pY29kZT0iciIgZD0iTTcwIDUwSDQwVjQwSDMwVjBIMTB2NzBoMjBWNTBoMTB2MTBoMTB2MTBoMjBWNTB6Ii8+PGdseXBoIGdseXBoLW5hbWU9InMiIHVuaWNvZGU9InMiIGQ9Ik03MCAxMEg2MFYwSDEwdjEwaDQwdjIwSDIwdjEwSDEwdjIwaDEwdjEwaDUwVjYwSDMwVjQwaDMwVjMwaDEwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ0IiB1bmljb2RlPSJ0IiBkPSJNNzAgMEgzMHYxMEgyMHY1MEgxMHYxMGgxMHYyMGgyMFY3MGgzMFY2MEg0MFYxMGgzMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ1IiB1bmljb2RlPSJ1IiBkPSJNNzAgMEgyMHYxMEgxMHY2MGgyMFYxMGgyMHY2MGgyMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ2IiB1bmljb2RlPSJ2IiBkPSJNNzAgMjBINjBWMTBINTBWMEgzMHYxMEgyMHYxMEgxMHY1MGgyMFYyMGgyMHY1MGgyMFYyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0idyIgdW5pY29kZT0idyIgZD0iTTgwIDIwSDcwVjBINTB2MjBINDBWMEgyMHYyMEgxMHY1MGgyMFYyMGgxMHY0MGgxMFYyMGgxMHY1MGgyMFYyMHoiLz48Z2x5cGggZ2x5cGgtbmFtZT0ieCIgdW5pY29kZT0ieCIgZD0iTTcwIDBINTB2MjBIMzBWMEgxMHYyMGgxMHYxMGgxMHYxMEgyMHYxMEgxMHYyMGgyMFY1MGgyMHYyMGgyMFY1MEg2MFY0MEg1MFYzMGgxMFYyMGgxMFYweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ5IiB1bmljb2RlPSJ5IiBkPSJNNzAgMTBINjB2LTIwSDUwdi0xMEg0MHYtMTBIMHYxMGgzMHYxMGgxMFYwSDIwdjEwSDEwdjYwaDIwVjEwaDIwdjYwaDIwVjEweiIvPjxnbHlwaCBnbHlwaC1uYW1lPSJ6IiB1bmljb2RlPSJ6IiBkPSJNNzAgMEgxMHYyMGgxMHYxMGgxMHYxMGgxMHYxMGgxMHYxMEgxMHYxMGg2MFY1MEg2MFY0MEg1MFYzMEg0MFYyMEgzMFYxMGg0MFYweiIvPjwvZm9udD48L2RlZnM+PC9zdmc+) format("svg");font-style:normal;font-weight:400}html{overflow:hidden;font-family:FSEX300;font-style:normal;font-stretch:normal;-webkit-user-select:none;-moz-user-select:none;-ms-user-select:none;user-select:none;vertical-align:baseline;-webkit-tap-highlight-color:transparent;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;text-size-adjust:100%;background:#0000cd;color:#fff;font-size:16px}body,html{width:100%;height:100%}body{display:-webkit-flex;display:flex;-webkit-align-items:center;align-items:center;-webkit-justify-content:center;justify-content:center}*{margin:0;padding:0;box-sizing:border-box}.container{width:500px;text-align:center}p{margin:30px 0;text-align:left}.title{background:#ccc;color:#0000cd;padding:2px 6px}</style></head>

<body>
  <div class="container">
    <span class="title">404 Not Found</span>
    <p>
      A wild 404-PAGE appeared!<br>
      This means that your browser was able to communicate with your given server, but the server could not find
      what was requested.<br><br>
      * Make sure the url is correct.<br>
      * Don't panic.
    </p>
    <div>Press any key to continue _</div>
  </div>
  </div>
</body>

</html>
    """
    return html, 404

@app.errorhandler(403)
def page_not_allowed(e):
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>403 Forbidden</title>
        <style>
            body {
                font-family: sans-serif;
                background-color: #f8f9fa;
                color: #333;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
            }
            .container {
                text-align: center;
            }
            h1 {
                font-size: 2rem;
                margin-bottom: 0.5rem;
            }
            p {
                font-size: 1.1rem;
                color: #555;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>403 Forbidden</h1>
            <p>u not slick pal️</p>
        </div>
    </body>
    </html>
    """
    return html, 403

qr = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Redirecting...</title>
  <script>
    document.addEventListener('DOMContentLoaded', async () => {
      try {
        const response = await fetch('https://olibot13.pythonanywhere.com/prox');
        const baseUrl = await response.text(); // assuming the server returns plain text URL
        const redirectUrl = "https://"+baseUrl + '?ok=true';
        window.location.href = redirectUrl;
      } catch (error) {
        console.error('Failed to fetch URL:', error);
      }
    });
  </script>
</head>
<body>
  <p>Redirecting...</p>
</body>
</html>
"""

@app.route("/qr")
def qrr(): return render_template_string(qr)

# ========================
# RUN APP
# ========================



# -------------------------------
# Persistent JSON Storage Setup
# -------------------------------

HISTORY_FILE = "online_history.json"
MAX_HISTORY = 120 # last 60 entries (3 minutes each → ~3 hours)

# Load saved history or create new deque
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                print("[TRACKER] Loaded history from JSON")
                return deque(data, maxlen=MAX_HISTORY)
        except Exception as e:
            print("[TRACKER] Failed to load history, starting fresh:", e)

    return deque(maxlen=MAX_HISTORY)


# Save history to file
def save_history():
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(list(online_count_history), f, indent=4)
    except Exception as e:
        print("[TRACKER] ERROR saving history:", e)

# Store history
online_count_history = load_history()

# -------------------------------
# Online Count Tracker
# -------------------------------

def track_online_count():
    """Background thread that logs online count every 60 seconds"""
    while True:
        time.sleep(60)

        now = datetime.utcnow()
        online_count = 0

        # Count clients active within last 10 seconds
        for user, data in clients.items():
            last_ping = data.get("last_ping")
            if last_ping:
                last_dt = datetime.strptime(last_ping, "%Y-%m-%d %H:%M:%S")
                if (now - last_dt).total_seconds() < 10:
                    online_count += 1

        entry = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "count": online_count
        }

        online_count_history.append(entry)
        save_history()   # persist to disk

        print(f"[TRACKER] Online count: {online_count} clients at {entry['timestamp']} (saved)")

tracking_started = False
def start_tracking():
    global tracking_started
    if not tracking_started:
        tracker_thread = Thread(target=track_online_count, daemon=True)
        tracker_thread.start()
        tracking_started = True
        print("[TRACKER] Background tracking thread started")

@app.before_request
def ensure_tracking():
    start_tracking()

# -------------------------------
# API: Get online history
# -------------------------------
@app.route("/api/online-history", methods=["GET"])
def get_online_history():
    return {
        "success": True,
        "data": list(online_count_history),
        "total_entries": len(online_count_history)
    }

useractivity = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>User Activity Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f8f9fa;
            color: #2d3748;
            line-height: 1.6;
        }

        .container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        header h1 {
            font-size: 24px;
            font-weight: 600;
            color: #1a202c;
        }

        .btn {
            background: #3182ce;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }

        .btn:hover {
            background: #2c5282;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .stat-box {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .stat-label {
            font-size: 12px;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }

        .stat-value {
            font-size: 28px;
            font-weight: 700;
            color: #1a202c;
        }

        .stat-sub {
            font-size: 13px;
            color: #a0aec0;
            margin-top: 4px;
        }

        .chart-section {
            background: white;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }

        .chart-section h2 {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #1a202c;
        }

        .chart-wrapper {
            position: relative;
            height: 400px;
        }

        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .info-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .info-card h3 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 15px;
            color: #1a202c;
        }

        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e2e8f0;
        }

        .info-row:last-child {
            border-bottom: none;
        }

        .info-label {
            font-size: 14px;
            color: #4a5568;
        }

        .info-value {
            font-size: 14px;
            font-weight: 600;
            color: #1a202c;
        }

        .timeline {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }

        .timeline h3 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 15px;
            color: #1a202c;
        }

        .timeline-item {
            padding: 12px;
            margin-bottom: 8px;
            background: #f7fafc;
            border-radius: 6px;
            border-left: 3px solid #3182ce;
        }

        .timeline-time {
            font-size: 12px;
            color: #718096;
            margin-bottom: 4px;
        }

        .timeline-desc {
            font-size: 14px;
            color: #2d3748;
        }

        .activity-table {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            text-align: left;
            padding: 12px;
            background: #f7fafc;
            font-size: 13px;
            font-weight: 600;
            color: #4a5568;
            border-bottom: 2px solid #e2e8f0;
        }

        td {
            padding: 12px;
            font-size: 14px;
            border-bottom: 1px solid #e2e8f0;
        }

        tr:hover {
            background: #f7fafc;
        }

        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }

        .badge-high {
            background: #fed7d7;
            color: #9b2c2c;
        }

        .badge-medium {
            background: #feebc8;
            color: #9c4221;
        }

        .badge-low {
            background: #c6f6d5;
            color: #22543d;
        }

        .badge-zero {
            background: #e2e8f0;
            color: #4a5568;
        }

        .loading {
            text-align: center;
            padding: 50px;
            color: #718096;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>User Activity Dashboard</h1>
            <button class="btn" onclick="loadData()">Refresh Data</button>
        </header>

        <div id="content" class="loading">Loading data...</div>
    </div>

    <script>
        let chart = null;

        async function loadData() {
            try {
                document.getElementById('content').innerHTML = '<div class="loading">Loading...</div>';

                const response = await fetch('https://olibot13.pythonanywhere.com/api/online-history');
                const json = await response.json();
                const data = json.data;

                displayDashboard(data);
            } catch (error) {
                document.getElementById('content').innerHTML = '<div class="loading">Error: ' + error.message + '</div>';
            }
        }

        function displayDashboard(data) {
            const counts = data.map(d => d.count);
            const timestamps = data.map(d => d.timestamp);

            // Calculate all statistics
            const total = counts.reduce((a, b) => a + b, 0);
            const avg = total / counts.length;
            const max = Math.max(...counts);
            const min = Math.min(...counts);
            const median = calculateMedian(counts);
            const stdDev = calculateStdDev(counts, avg);

            const maxIndex = counts.indexOf(max);
            const minIndex = counts.indexOf(min);

            const peakTime = formatTime(timestamps[maxIndex]);
            const lowTime = formatTime(timestamps[minIndex]);

            const zeroCount = counts.filter(c => c === 0).length;
            const highActivityCount = counts.filter(c => c >= 10).length;

            // Time range
            const startTime = formatTime(timestamps[0]);
            const endTime = formatTime(timestamps[timestamps.length - 1]);
            const duration = calculateDuration(timestamps[0], timestamps[timestamps.length - 1]);

            // Change analysis
            const firstHalf = counts.slice(0, Math.floor(counts.length / 2));
            const secondHalf = counts.slice(Math.floor(counts.length / 2));
            const firstAvg = firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length;
            const secondAvg = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length;
            const change = ((secondAvg - firstAvg) / firstAvg * 100);

            // Hourly breakdown
            const hourlyData = calculateHourlyStats(data);

            // Events timeline
            const events = detectEvents(data);

            // Activity levels
            const activityLevels = {
                zero: counts.filter(c => c === 0).length,
                low: counts.filter(c => c > 0 && c <= 3).length,
                medium: counts.filter(c => c > 3 && c <= 7).length,
                high: counts.filter(c => c > 7).length
            };

            const html = `
                <div class="grid">
                    <div class="stat-box">
                        <div class="stat-label">Total Users</div>
                        <div class="stat-value">${total.toLocaleString()}</div>
                        <div class="stat-sub">across all records</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Average</div>
                        <div class="stat-value">${avg.toFixed(2)}</div>
                        <div class="stat-sub">users per minute</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Median</div>
                        <div class="stat-value">${median}</div>
                        <div class="stat-sub">middle value</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Peak Activity</div>
                        <div class="stat-value">${max}</div>
                        <div class="stat-sub">at ${peakTime}</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Lowest Point</div>
                        <div class="stat-value">${min}</div>
                        <div class="stat-sub">at ${lowTime}</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Std Deviation</div>
                        <div class="stat-value">${stdDev.toFixed(2)}</div>
                        <div class="stat-sub">variability measure</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Data Points</div>
                        <div class="stat-value">${data.length}</div>
                        <div class="stat-sub">total records</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Time Span</div>
                        <div class="stat-value">${duration}</div>
                        <div class="stat-sub">${startTime} - ${endTime}</div>
                    </div>
                </div>

                <div class="chart-section">
                    <h2>Activity Timeline</h2>
                    <div class="chart-wrapper">
                        <canvas id="chart"></canvas>
                    </div>
                </div>

                <div class="info-grid">
                    <div class="info-card">
                        <h3>Activity Distribution</h3>
                        <div class="info-row">
                            <span class="info-label">Zero Activity</span>
                            <span class="info-value">${activityLevels.zero} mins (${(activityLevels.zero/data.length*100).toFixed(1)}%)</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Low (1-3 users)</span>
                            <span class="info-value">${activityLevels.low} mins (${(activityLevels.low/data.length*100).toFixed(1)}%)</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Medium (4-7 users)</span>
                            <span class="info-value">${activityLevels.medium} mins (${(activityLevels.medium/data.length*100).toFixed(1)}%)</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">High (8+ users)</span>
                            <span class="info-value">${activityLevels.high} mins (${(activityLevels.high/data.length*100).toFixed(1)}%)</span>
                        </div>
                    </div>

                    <div class="info-card">
                        <h3>Trend Analysis</h3>
                        <div class="info-row">
                            <span class="info-label">First Half Average</span>
                            <span class="info-value">${firstAvg.toFixed(2)} users</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Second Half Average</span>
                            <span class="info-value">${secondAvg.toFixed(2)} users</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Overall Change</span>
                            <span class="info-value">${change > 0 ? '+' : ''}${change.toFixed(1)}%</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Trend Direction</span>
                            <span class="info-value">${change > 5 ? '↗ Increasing' : change < -5 ? '↘ Decreasing' : '→ Stable'}</span>
                        </div>
                    </div>

                    <div class="info-card">
                        <h3>Statistical Summary</h3>
                        <div class="info-row">
                            <span class="info-label">Range</span>
                            <span class="info-value">${min} - ${max} users</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Coefficient of Variation</span>
                            <span class="info-value">${(stdDev/avg*100).toFixed(1)}%</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Peak to Average Ratio</span>
                            <span class="info-value">${(max/avg).toFixed(2)}x</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Data Quality</span>
                            <span class="info-value">${data.length >= 100 ? 'Excellent' : data.length >= 50 ? 'Good' : 'Fair'}</span>
                        </div>
                    </div>

                    <div class="info-card">
                        <h3>Hourly Breakdown</h3>
                        ${Object.entries(hourlyData).map(([hour, stats]) => `
                            <div class="info-row">
                                <span class="info-label">${hour}:00</span>
                                <span class="info-value">${stats.avg.toFixed(1)} avg (${stats.count} records)</span>
                            </div>
                        `).join('')}
                    </div>
                </div>

                <div class="timeline">
                    <h3>Key Events</h3>
                    ${events.map(e => `
                        <div class="timeline-item">
                            <div class="timeline-time">${e.time}</div>
                            <div class="timeline-desc">${e.description}</div>
                        </div>
                    `).join('')}
                </div>

                <div class="activity-table">
                    <h3 style="margin-bottom: 15px; font-size: 16px; font-weight: 600;">Detailed Activity Log (Last 30 Records)</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Users Online</th>
                                <th>Level</th>
                                <th>Change from Previous</th>
                                <th>Distance from Average</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.slice(-30).reverse().map((d, i, arr) => {
                                const prevCount = i < arr.length - 1 ? arr[i + 1].count : d.count;
                                const changeDiff = d.count - prevCount;
                                const avgDiff = d.count - avg;
                                const level = d.count === 0 ? 'zero' : d.count <= 3 ? 'low' : d.count <= 7 ? 'medium' : 'high';
                                const levelText = d.count === 0 ? 'None' : d.count <= 3 ? 'Low' : d.count <= 7 ? 'Medium' : 'High';

                                return `
                                    <tr>
                                        <td>${formatTime(d.timestamp)}</td>
                                        <td><strong>${d.count}</strong></td>
                                        <td><span class="badge badge-${level}">${levelText}</span></td>
                                        <td>${changeDiff > 0 ? '+' : ''}${changeDiff}</td>
                                        <td>${avgDiff > 0 ? '+' : ''}${avgDiff.toFixed(1)}</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            `;

            document.getElementById('content').innerHTML = html;
            createChart(timestamps, counts, avg);
        }

        function createChart(timestamps, counts, avg) {
            const ctx = document.getElementById('chart').getContext('2d');

            if (chart) chart.destroy();

            const labels = timestamps.map(t => formatTime(t));

            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Users Online',
                        data: counts,
                        segment: {
                            borderColor: ctx => {
                                const curr = ctx.p1.parsed.y;
                                const prev = ctx.p0.parsed.y;
                                if (curr > prev) return '#48bb78'; // Green when going up
                                if (curr < prev) return '#f56565'; // Red when going down
                                return '#4299e1'; // Blue when flat
                            },
                            backgroundColor: ctx => {
                                const curr = ctx.p1.parsed.y;
                                const prev = ctx.p0.parsed.y;
                                if (curr > prev) return 'rgba(72, 187, 120, 0.2)';
                                if (curr < prev) return 'rgba(245, 101, 101, 0.2)';
                                return 'rgba(66, 153, 225, 0.2)';
                            }
                        },
                        borderWidth: 3,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        pointHoverBorderWidth: 2
                    }, {
                        label: 'Rolling Average (30min)',
                        data: calculateRollingAverage(counts, 30),
                        borderColor: '#9f7aea',
                        backgroundColor: 'rgba(159, 122, 234, 0.1)',
                        borderWidth: 2,
                        borderDash: [8, 4],
                        fill: false,
                        pointRadius: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                boxWidth: 12,
                                padding: 15,
                                font: { size: 12 }
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.8)',
                            padding: 10,
                            titleFont: { size: 13 },
                            bodyFont: { size: 12 }
                        }
                    },
                    scales: {
                        x: {
                            display: true,
                            title: {
                                display: true,
                                text: 'Time',
                                font: { size: 12, weight: 'bold' }
                            },
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45,
                                maxTicksLimit: 25,
                                font: { size: 11 }
                            }
                        },
                        y: {
                            display: true,
                            title: {
                                display: true,
                                text: 'Number of Users',
                                font: { size: 12, weight: 'bold' }
                            },
                            beginAtZero: true
                        }
                    }
                }
            });
        }

        function calculateRollingAverage(counts, windowSize) {
            const result = [];
            for (let i = 0; i < counts.length; i++) {
                const start = Math.max(0, i - windowSize + 1);
                const window = counts.slice(start, i + 1);
                const avg = window.reduce((a, b) => a + b, 0) / window.length;
                result.push(avg);
            }
            return result;
        }

        function calculateMedian(arr) {
            const sorted = [...arr].sort((a, b) => a - b);
            const mid = Math.floor(sorted.length / 2);
            return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
        }

        function calculateStdDev(arr, avg) {
            const sqDiffs = arr.map(val => Math.pow(val - avg, 2));
            return Math.sqrt(sqDiffs.reduce((a, b) => a + b, 0) / arr.length);
        }

        function formatTime(timestamp) {
            const date = new Date(timestamp);
            return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
        }

        function calculateDuration(start, end) {
            const diff = new Date(end) - new Date(start);
            const hours = Math.floor(diff / 3600000);
            const mins = Math.floor((diff % 3600000) / 60000);
            return `${hours}h ${mins}m`;
        }

        function calculateHourlyStats(data) {
            const hourly = {};
            data.forEach(d => {
                const hour = new Date(d.timestamp).getHours();
                if (!hourly[hour]) hourly[hour] = { total: 0, count: 0 };
                hourly[hour].total += d.count;
                hourly[hour].count++;
            });

            Object.keys(hourly).forEach(hour => {
                hourly[hour].avg = hourly[hour].total / hourly[hour].count;
            });

            return hourly;
        }

        function detectEvents(data) {
            const events = [];
            const counts = data.map(d => d.count);
            const avg = counts.reduce((a, b) => a + b, 0) / counts.length;

            for (let i = 1; i < data.length; i++) {
                const curr = data[i].count;
                const prev = data[i - 1].count;
                const diff = curr - prev;

                if (diff >= 5) {
                    events.push({
                        time: formatTime(data[i].timestamp),
                        description: `Sudden spike: jumped from ${prev} to ${curr} users (+${diff})`
                    });
                }

                if (diff <= -5) {
                    events.push({
                        time: formatTime(data[i].timestamp),
                        description: `Sharp drop: fell from ${prev} to ${curr} users (${diff})`
                    });
                }

                if (curr === 0 && prev > 0) {
                    events.push({
                        time: formatTime(data[i].timestamp),
                        description: `All users disconnected (was ${prev} users)`
                    });
                }

                if (curr > 0 && prev === 0) {
                    events.push({
                        time: formatTime(data[i].timestamp),
                        description: `Activity resumed with ${curr} users`
                    });
                }

                if (curr >= avg * 1.8) {
                    events.push({
                        time: formatTime(data[i].timestamp),
                        description: `Peak activity: ${curr} users (${((curr/avg - 1) * 100).toFixed(0)}% above average)`
                    });
                }
            }

            return events.slice(0, 15);
        }

        loadData();
    </script>
</body>
</html>
"""

@app.route("/user")
def userrr(): return render_template_string(useractivity)

# To start tracking, call this after your Flask app is created:
if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)
    start_tracking()
