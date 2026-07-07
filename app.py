import os
import json
import uuid
import datetime

import requests
import psycopg
from psycopg.rows import dict_row
from flask import Flask, request, session, redirect, Response, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change_me_in_railway_env")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HOST_SECRET = os.environ.get("HOST_SECRET", "hazera-host")
CLAUDE_MODEL = "claude-sonnet-4-6"

BRAND = {
    "green": "#20805E",
    "green_deep": "#04342C",
    "green_mid": "#0F6E56",
    "green_tint": "#E1F5EE",
    "green_line": "#9FE1CB",
    "orange": "#FA8B01",
    "orange_deep": "#4A1B0C",
    "orange_mid": "#993C1D",
    "orange_tint": "#FAECE7",
    "teal": "#12B5B0",
    "text": "#4F4F4F",
    "muted": "#888780",
    "line": "#D3D1C7",
    "hair": "#F1EFE8",
    "white": "#FFFFFF",
    "logo": "https://www.hazera.com/wp-content/uploads/sites/27/2023/07/Logo-2-1.png",
}

EXERCISES = ["reconnect", "disc", "dice"]

SCENARIO = "A tight deadline lands with incomplete information. What do you do first?"


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS exercise_state ("
                "exercise TEXT PRIMARY KEY, "
                "status TEXT NOT NULL DEFAULT 'locked', "
                "synthesis TEXT DEFAULT '')"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS responses ("
                "id SERIAL PRIMARY KEY, "
                "pid TEXT NOT NULL, "
                "exercise TEXT NOT NULL, "
                "payload JSONB NOT NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS responses_pid_exercise "
                "ON responses (pid, exercise)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS votes ("
                "id SERIAL PRIMARY KEY, "
                "pid TEXT NOT NULL, "
                "response_id INTEGER NOT NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS votes_pid ON votes (pid)"
            )
            for ex in EXERCISES:
                cur.execute(
                    "INSERT INTO exercise_state (exercise, status) "
                    "VALUES (%s, 'locked') ON CONFLICT (exercise) DO NOTHING",
                    (ex,),
                )
        conn.commit()


def pid():
    if "pid" not in session:
        session["pid"] = uuid.uuid4().hex
    return session["pid"]


def states():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT exercise, status, synthesis FROM exercise_state")
            rows = cur.fetchall()
    out = {}
    for r in rows:
        out[r["exercise"]] = {"status": r["status"], "synthesis": r["synthesis"] or ""}
    return out


def require_host():
    token = request.view_args.get("secret") if request.view_args else None
    return token == HOST_SECRET


def claude_text(prompt):
    if not ANTHROPIC_API_KEY:
        return "AI key is not set. Add ANTHROPIC_API_KEY in Railway to run the synthesis."
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 700,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        data = resp.json()
        parts = data.get("content", [])
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        return text.strip() or "The synthesis came back empty. Try again."
    except Exception:
        return "The synthesis could not run just now. Try again in a moment."


PAGE_HEAD = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<link rel='icon' href='" + BRAND["logo"] + "'>"
    "<link rel='preconnect' href='https://fonts.googleapis.com'>"
    "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
    "<link href='https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600&"
    "family=Open+Sans:wght@400;500;600&display=swap' rel='stylesheet'>"
)


def base_css():
    b = BRAND
    return (
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:'Open Sans',sans-serif;color:" + b["text"] + ";"
        "background:#F7FAF8;line-height:1.5}"
        "h1,h2,h3,.hd{font-family:'Poppins',sans-serif;font-weight:600}"
        ".wrap{max-width:960px;margin:0 auto;padding:24px 20px}"
        ".card{background:#fff;border:1px solid " + b["line"] + ";"
        "border-radius:14px;padding:22px;margin-bottom:16px}"
        ".btn{font-family:'Poppins',sans-serif;font-weight:600;border:none;"
        "border-radius:8px;padding:14px 18px;font-size:15px;cursor:pointer;"
        "width:100%;background:" + b["orange"] + ";color:" + b["orange_deep"] + "}"
        ".btn:active{transform:scale(.99)}"
        ".btn.green{background:" + b["green"] + ";color:#fff}"
        ".btn.ghost{background:#fff;border:1px solid " + b["line"] + ";color:" + b["text"] + ";"
        "font-weight:500}"
        "textarea,input[type=text]{width:100%;border:1px solid " + b["line"] + ";"
        "border-radius:8px;padding:11px 12px;font-family:'Open Sans',sans-serif;"
        "font-size:14px;color:" + b["text"] + ";resize:none;background:#fff}"
        "textarea:focus,input:focus{outline:none;border-color:" + b["green"] + "}"
        "label{font-size:13px;font-weight:600;display:block;margin-bottom:6px}"
        ".muted{color:" + b["muted"] + ";font-size:13px}"
        ".topbar{background:" + b["green"] + ";color:#fff;border-radius:14px;"
        "padding:16px 20px;display:flex;align-items:center;justify-content:space-between;"
        "margin-bottom:18px}"
        ".brandrow{display:flex;align-items:center;gap:12px}"
        ".brandrow img{height:30px;width:auto;background:#fff;border-radius:6px;padding:3px 6px}"
        ".tagline{font-size:11px;color:#C7E6DA}"
        ".chip{background:" + b["teal"] + ";color:" + b["green_deep"] + ";font-size:11px;"
        "font-weight:600;padding:5px 11px;border-radius:20px;font-family:'Poppins',sans-serif}"
        ".big{font-family:'Poppins',sans-serif;font-weight:600;font-size:28px;color:" + b["green_deep"] + "}"
    )


def participant_html():
    css = base_css()
    body = (
        "<div class='wrap'>"
        "<div class='topbar'>"
        "<div class='brandrow'><img src='" + BRAND["logo"] + "' alt='Hazera'>"
        "<div><div class='hd' style='font-size:16px'>Growing Together</div>"
        "<div class='tagline'>Full Immersion, session three</div></div></div>"
        "<span class='chip'>Dale Carnegie</span>"
        "</div>"
        "<div id='view'></div>"
        "<p class='muted' style='text-align:center;margin-top:10px'>"
        "Your answers are anonymous to the room.</p>"
        "</div>"
    )
    script = (
        "<script>"
        "var S={};"
        "function esc(s){var d=document.createElement('div');d.textContent=s||'';"
        "return d.innerHTML;}"
        "var lastKey='';"
        "function load(force){fetch('/state').then(r=>r.json())"
        ".then(function(st){render(st,force);});}"
        "function vkey(st){"
        "if(st.reconnect.status=='open')return 'reconnect:'+(sent('reconnect')?1:0);"
        "if(st.disc.status=='open')return 'disc:'+(sent('disc')?1:0);"
        "if(['open','voting','revealed'].includes(st.dice.status))"
        "return 'dice:'+st.dice.status+':'+(sent('dice')?1:0)+':'"
        "+(localStorage.getItem('voted')?1:0);"
        "return 'wait';}"
        "function render(st,force){S=st;var k=vkey(st);"
        "if(!force&&k===lastKey)return;lastKey=k;"
        "var v=document.getElementById('view');"
        "var open=null;"
        "if(st.reconnect.status=='open')open='reconnect';"
        "else if(st.disc.status=='open')open='disc';"
        "else if(['open','voting','revealed'].includes(st.dice.status))open='dice';"
        "if(!open){v.innerHTML=waiting();return;}"
        "if(open=='reconnect')v.innerHTML=reconnect();"
        "if(open=='disc')v.innerHTML=disc();"
        "if(open=='dice')diceView(v);"
        "}"
        "function waiting(){return \"<div class='card' style='text-align:center'>"
        "<div class='big'>Stand by</div>"
        "<p class='muted' style='margin-top:8px'>Ken will open the next step. "
        "Keep this tab open.</p></div>\";}"
        "function reconnect(){if(sent('reconnect'))return thanks('Reflection in. "
        "Watch the shared screen.');"
        "return \"<div class='card'>"
        "<div class='hd' style='font-size:18px;color:" + BRAND["green"] + "'>January reconnect</div>"
        "<p class='muted' style='margin:6px 0 16px'>Think back to January. Be honest.</p>"
        "<label style='color:" + BRAND["green"] + "'>One Carnegie principle you actually used</label>"
        "<textarea id='r_used' rows='3'></textarea>"
        "<div style='height:14px'></div>"
        "<label style='color:" + BRAND["orange"] + "'>One that slipped</label>"
        "<textarea id='r_slip' rows='3'></textarea>"
        "<div style='height:16px'></div>"
        "<button class='btn' onclick='sendReconnect()'>Submit reflection</button>"
        "</div>\";}"
        "function sendReconnect(){var u=val('r_used'),s=val('r_slip');"
        "if(!u&&!s){return;}post('/submit/reconnect',{used:u,slipped:s});}"
        "function disc(){if(sent('disc'))return thanks('Response in. "
        "Watch the four styles on the shared screen.');"
        "return \"<div class='card'>"
        "<div class='hd' style='font-size:18px;color:" + BRAND["green"] + "'>DISC in action</div>"
        "<div style='background:" + BRAND["hair"] + ";border-radius:8px;padding:12px;margin:12px 0'>"
        "<div class='muted' style='font-weight:600'>Scenario</div>"
        "<div style='margin-top:4px'>" + SCENARIO + "</div></div>"
        "<label style='color:" + BRAND["green"] + "'>Your response</label>"
        "<textarea id='d_text' rows='3'></textarea>"
        "<div style='height:14px'></div>"
        "<label style='color:" + BRAND["orange"] + "'>Your natural style</label>"
        "<div id='styles' style='display:flex;gap:8px'>"
        "<button class='btn ghost' onclick=\\\"pick('D')\\\" data-s='D'>D</button>"
        "<button class='btn ghost' onclick=\\\"pick('I')\\\" data-s='I'>I</button>"
        "<button class='btn ghost' onclick=\\\"pick('S')\\\" data-s='S'>S</button>"
        "<button class='btn ghost' onclick=\\\"pick('C')\\\" data-s='C'>C</button></div>"
        "<div style='height:16px'></div>"
        "<button class='btn' onclick='sendDisc()'>Submit response</button></div>\";}"
        "var chosen='';"
        "function pick(s){chosen=s;document.querySelectorAll('#styles button')"
        ".forEach(function(b){if(b.getAttribute('data-s')==s){"
        "b.style.background='" + BRAND["orange"] + "';b.style.color='" + BRAND["orange_deep"] + "';"
        "b.style.borderColor='" + BRAND["orange"] + "';}"
        "else{b.style.background='#fff';b.style.color='" + BRAND["text"] + "';"
        "b.style.borderColor='" + BRAND["line"] + "';}});}"
        "function sendDisc(){var t=val('d_text');if(!t||!chosen)return;"
        "post('/submit/disc',{text:t,style:chosen});}"
        "function diceView(v){var st=S.dice.status;"
        "if(st=='open'){if(sent('dice')){v.innerHTML=thanks("
        "'Commitment locked. Voting opens shortly.');return;}"
        "v.innerHTML=diceForm();return;}"
        "if(st=='voting'){diceVote(v);return;}"
        "if(st=='revealed'){v.innerHTML=thanks('Winner is on the shared screen.');}}"
        "function diceForm(){return \"<div class='card'>"
        "<div class='hd' style='font-size:18px;color:" + BRAND["green"] + "'>DICE and commit</div>"
        "<p class='muted' style='margin:6px 0 14px'>Run DICE on your own behavior since January.</p>"
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px'>"
        "<div><label style='color:" + BRAND["green"] + "'>Decrease</label>"
        "<textarea id='x_dec' rows='2'></textarea></div>"
        "<div><label style='color:" + BRAND["green"] + "'>Increase</label>"
        "<textarea id='x_inc' rows='2'></textarea></div>"
        "<div><label style='color:" + BRAND["green"] + "'>Continue</label>"
        "<textarea id='x_con' rows='2'></textarea></div>"
        "<div><label style='color:" + BRAND["green"] + "'>Eliminate</label>"
        "<textarea id='x_eli' rows='2'></textarea></div></div>"
        "<div style='height:14px'></div>"
        "<label style='color:" + BRAND["orange"] + "'>One start, one stop</label>"
        "<textarea id='x_start' rows='2' placeholder='Start: ...'></textarea>"
        "<div style='height:8px'></div>"
        "<textarea id='x_stop' rows='2' placeholder='Stop: ...'></textarea>"
        "<div style='height:16px'></div>"
        "<button class='btn' onclick='sendDice()'>Lock my commitment</button></div>\";}"
        "function sendDice(){var start=val('x_start'),stop=val('x_stop');"
        "if(!start&&!stop)return;post('/submit/dice',{"
        "decrease:val('x_dec'),increase:val('x_inc'),continue_:val('x_con'),"
        "eliminate:val('x_eli'),start:start,stop:stop});}"
        "function diceVote(v){if(localStorage.getItem('voted')){"
        "v.innerHTML=thanks('Vote recorded. Watch the shared screen.');return;}"
        "fetch('/commitments').then(r=>r.json()).then(function(list){"
        "var h=\"<div class='card'><div class='hd' style='font-size:18px;color:"
        + BRAND["green"] + "'>Vote the sharpest commitment</div>"
        "<p class='muted' style='margin:6px 0 14px'>Pick the most specific, testable one.</p>\";"
        "list.forEach(function(c){h+=\"<button class='btn ghost' style='text-align:left;"
        "margin-bottom:8px' onclick='castVote(\"+c.id+\")'>\"+esc(c.text)+\"</button>\";});"
        "h+=\"</div>\";v.innerHTML=h;});}"
        "function castVote(id){localStorage.setItem('voted','1');"
        "post('/vote',{response_id:id});}"
        "function thanks(m){return \"<div class='card' style='text-align:center'>"
        "<div class='big'>Done</div><p class='muted' style='margin-top:8px'>\"+m+\"</p></div>\";}"
        "function sent(ex){return localStorage.getItem('done_'+ex)=='1';}"
        "function markSent(ex){localStorage.setItem('done_'+ex,'1');}"
        "function val(id){var e=document.getElementById(id);return e?e.value.trim():'';}"
        "function post(url,data){fetch(url,{method:'POST',"
        "headers:{'content-type':'application/json'},body:JSON.stringify(data)})"
        ".then(r=>r.json()).then(function(res){if(res.ok){"
        "if(res.exercise)markSent(res.exercise);load(true);}});}"
        "load(true);setInterval(load,2500);"
        "</script>"
    )
    return (
        PAGE_HEAD + "<style>" + css + "</style><title>Hazera session</title></head><body>"
        + body + script + "</body></html>"
    )


def host_html(secret):
    css = base_css()
    extra = (
        ".hcard{background:#fff;border:1px solid " + BRAND["line"] + ";border-radius:14px;"
        "padding:18px 20px;margin-bottom:16px}"
        ".row{display:flex;align-items:center;justify-content:space-between;gap:12px}"
        ".stat{background:" + BRAND["green_tint"] + ";border-radius:10px;padding:14px 16px}"
        ".stat .k{font-size:13px;color:" + BRAND["green_mid"] + "}"
        ".stat .v{font-family:'Poppins',sans-serif;font-weight:600;font-size:30px;"
        "color:" + BRAND["green_deep"] + "}"
        ".ctrl{display:flex;gap:8px}"
        ".ctrl button{font-family:'Poppins',sans-serif;font-weight:600;font-size:13px;"
        "border-radius:8px;border:1px solid " + BRAND["line"] + ";padding:8px 12px;cursor:pointer;"
        "background:#fff;color:" + BRAND["text"] + "}"
        ".ctrl .on{background:" + BRAND["green"] + ";color:#fff;border-color:" + BRAND["green"] + "}"
        ".ctrl .go{background:" + BRAND["orange"] + ";color:" + BRAND["orange_deep"] + ";"
        "border-color:" + BRAND["orange"] + "}"
        ".mirror{background:" + BRAND["green_tint"] + ";border:1px solid " + BRAND["green_line"] + ";"
        "border-radius:12px;padding:16px 18px;font-size:15px;color:" + BRAND["green_mid"] + ";"
        "line-height:1.6;white-space:pre-wrap}"
        ".scan{height:3px;background:" + BRAND["teal"] + ";border-radius:3px;width:0;"
        "transition:width 1.1s ease}"
        ".grid4{display:grid;grid-template-columns:1fr 1fr;gap:10px}"
        ".scol{border-radius:10px;padding:12px}"
        ".scol h4{font-family:'Poppins',sans-serif;font-size:13px;margin-bottom:6px}"
        ".scol .it{font-size:13px;margin-bottom:6px;line-height:1.4}"
        ".vbar{position:relative;border-radius:8px;overflow:hidden;border:1px solid "
        + BRAND["line"] + ";margin-bottom:8px}"
        ".vbar .fill{position:absolute;inset:0;width:0;background:" + BRAND["green_tint"] + ";"
        "transition:width .8s ease}"
        ".vbar .lab{position:relative;padding:10px 12px;display:flex;justify-content:space-between;"
        "gap:12px;font-size:14px}"
        ".vbar.win .fill{background:#FCE9C9}"
        ".vbar.win{border-color:" + BRAND["orange"] + "}"
    )
    body = (
        "<div class='wrap'>"
        "<div class='topbar' style='background:" + BRAND["green_deep"] + "'>"
        "<div class='brandrow'><img src='" + BRAND["logo"] + "' alt='Hazera'>"
        "<div><div class='hd' style='font-size:16px'>Facilitator stage</div>"
        "<div class='tagline'>Shared this screen the whole time</div></div></div>"
        "<span class='chip'>Live</span></div>"
        "<div id='stage'></div>"
        "</div>"
    )
    script = (
        "<script>"
        "var SEC='__SECRET__';var lastSynth={};"
        "function esc(s){var d=document.createElement('div');d.textContent=s||'';"
        "return d.innerHTML;}"
        "function api(path,data){return fetch('/host/'+SEC+path,{method:'POST',"
        "headers:{'content-type':'application/json'},body:JSON.stringify(data||{})})"
        ".then(r=>r.json());}"
        "function open_(ex){api('/open',{exercise:ex}).then(pull);}"
        "function lock_(ex){api('/lock',{exercise:ex}).then(pull);}"
        "function clr(ex){if(confirm('Clear all responses for '+ex+'?'))"
        "api('/clear',{exercise:ex}).then(pull);}"
        "function phase(ex,p){api('/phase',{exercise:ex,status:p}).then(pull);}"
        "function synth(ex){var el=document.getElementById('scan_'+ex);"
        "if(el){el.style.width='100%';}"
        "api('/synthesize',{exercise:ex}).then(function(){pull();});}"
        "function ctrlRow(ex,st){var open=st==='open';"
        "var h=\"<div class='ctrl'>\";"
        "h+=\"<button class='\"+(open?'on':'')+\"' onclick=\\\"open_('\"+ex+\"')\\\">Open</button>\";"
        "h+=\"<button onclick=\\\"lock_('\"+ex+\"')\\\">Lock</button>\";"
        "h+=\"<button onclick=\\\"clr('\"+ex+\"')\\\">Clear</button>\";"
        "h+=\"</div>\";return h;}"
        "function num(el,to){var from=parseInt(el.getAttribute('data-n')||'0');"
        "if(from===to){el.textContent=to;return;}var step=(to>from)?1:-1;var cur=from;"
        "var t=setInterval(function(){cur+=step;el.textContent=cur;"
        "if(cur===to){clearInterval(t);}},40);el.setAttribute('data-n',to);}"
        "function pull(){fetch('/host/'+SEC+'/data').then(r=>r.json()).then(render);}"
        "function render(d){var s=document.getElementById('stage');"
        "var h='';"
        "h+=block('January reconnect','reconnect',d);"
        "h+=block('DISC in action','disc',d);"
        "h+=block('DICE and commit','dice',d);"
        "s.innerHTML=h;"
        "var rc=document.getElementById('cnt_reconnect');if(rc)num(rc,d.reconnect.count);"
        "var dc=document.getElementById('cnt_disc');if(dc)num(dc,d.disc.count);"
        "var xc=document.getElementById('cnt_dice');if(xc)num(xc,d.dice.count);"
        "if(d.dice.status==='voting'||d.dice.status==='revealed')paintVotes(d);"
        "if(d.disc.status!=='locked')paintDisc(d);}"
        "function block(title,ex,d){var st=d[ex].status;var b=d[ex];"
        "var h=\"<div class='hcard'><div class='row'>"
        "<div class='hd' style='font-size:18px;color:" + BRAND["green"] + "'>\"+title+\"</div>\";"
        "h+=ctrlRow(ex,st)+\"</div>\";"
        "h+=\"<div class='row' style='margin-top:14px'>"
        "<div class='stat'><div class='k'>Submitted</div>"
        "<div class='v'><span id='cnt_\"+ex+\"' data-n='0'>0</span> of \"+d.total+\"</div></div>\";"
        "if(ex==='reconnect'||ex==='disc'){"
        "h+=\"<button class='btn green' style='width:auto;padding:12px 18px' "
        "onclick=\\\"synth('\"+ex+\"')\\\">Run group synthesis</button>\";}"
        "if(ex==='dice'){"
        "h+=\"<div class='ctrl'>"
        "<button class='\"+(st==='voting'?'on':'go')+\"' onclick=\\\"phase('dice','voting')\\\">Open vote</button>"
        "<button class='go' onclick=\\\"phase('dice','revealed')\\\">Reveal winner</button></div>\";}"
        "h+=\"</div>\";"
        "if((ex==='reconnect'||ex==='disc')){"
        "h+=\"<div id='scan_\"+ex+\"' class='scan' style='margin:14px 0'></div>\";"
        "if(b.synthesis){h+=\"<div class='mirror'>\"+esc(b.synthesis)+\"</div>\";}}"
        "if(ex==='disc'){h+=\"<div id='disc_grid' style='margin-top:14px'></div>\";}"
        "if(ex==='dice'){h+=\"<div id='vote_box' style='margin-top:14px'></div>\";}"
        "h+=\"</div>\";return h;}"
        "var DC={D:['" + BRAND["orange_tint"] + "','" + BRAND["orange_mid"] + "','D, results'],"
        "I:['#FAEEDA','#854F0B','I, people'],"
        "S:['#E6F1FB','#185FA5','S, stability'],"
        "C:['#EEEDFE','#3C3489','C, accuracy']};"
        "function paintDisc(d){var g=document.getElementById('disc_grid');if(!g)return;"
        "var by={D:[],I:[],S:[],C:[]};(d.disc.items||[]).forEach(function(it){"
        "if(by[it.style])by[it.style].push(it.text);});"
        "var h=\"<div class='grid4'>\";['D','I','S','C'].forEach(function(k){"
        "var c=DC[k];h+=\"<div class='scol' style='background:\"+c[0]+\"'>"
        "<h4 style='color:\"+c[1]+\"'>\"+c[2]+\"</h4>\";"
        "by[k].forEach(function(t){h+=\"<div class='it' style='color:\"+c[1]+\"'>\"+esc(t)+\"</div>\";});"
        "if(by[k].length===0){h+=\"<div class='it' style='color:" + BRAND["muted"] + "'>waiting</div>\";}"
        "h+=\"</div>\";});h+=\"</div>\";g.innerHTML=h;}"
        "function paintVotes(d){var box=document.getElementById('vote_box');if(!box)return;"
        "var items=d.dice.votes||[];var total=0;items.forEach(function(i){total+=i.count;});"
        "var reveal=d.dice.status==='revealed';var top=-1;"
        "items.forEach(function(i){if(i.count>top)top=i.count;});"
        "var h='';items.forEach(function(i){"
        "var pct=total?Math.round(i.count/total*100):0;"
        "var win=reveal&&i.count===top&&total>0;"
        "h+=\"<div class='vbar\"+(win?' win':'')+\"'><div class='fill' style='width:\"+pct+\"%'></div>"
        "<div class='lab'><span>\"+(win?'<b>':'')+esc(i.text)+(win?' </b>':'')+\"</span>"
        "<span style='font-weight:600'>\"+pct+\"%</span></div></div>\";});"
        "if(reveal&&total>0){h+=\"<div style='text-align:center;margin-top:6px;"
        "font-family:Poppins;font-weight:600;color:" + BRAND["orange_mid"] + "'>"
        "Sharpest commitment in the room</div>\";}"
        "box.innerHTML=h;"
        "requestAnimationFrame(function(){document.querySelectorAll('#vote_box .fill')"
        ".forEach(function(f,idx){var pct=items[idx]?"
        "(total?Math.round(items[idx].count/total*100):0):0;f.style.width=pct+'%';});});}"
        "pull();setInterval(pull,2500);"
        "</script>"
    )
    html = (
        PAGE_HEAD + "<style>" + css + extra + "</style><title>Hazera host</title></head><body>"
        + body + script + "</body></html>"
    )
    return html.replace("__SECRET__", secret)


@app.route("/")
def index():
    pid()
    return Response(participant_html(), mimetype="text/html")


@app.route("/state")
def state():
    st = states()
    return jsonify({k: {"status": v["status"]} for k, v in st.items()})


@app.route("/submit/reconnect", methods=["POST"])
def submit_reconnect():
    return save_response("reconnect", request.get_json(force=True))


@app.route("/submit/disc", methods=["POST"])
def submit_disc():
    return save_response("disc", request.get_json(force=True))


@app.route("/submit/dice", methods=["POST"])
def submit_dice():
    return save_response("dice", request.get_json(force=True))


def save_response(exercise, data):
    st = states().get(exercise, {}).get("status", "locked")
    allowed = ["open"] if exercise != "dice" else ["open"]
    if st not in allowed:
        return jsonify({"ok": False, "error": "closed"})
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO responses (pid, exercise, payload) VALUES (%s,%s,%s) "
                "ON CONFLICT (pid, exercise) DO UPDATE SET payload=EXCLUDED.payload, "
                "created_at=now()",
                (pid(), exercise, json.dumps(data)),
            )
        conn.commit()
    return jsonify({"ok": True, "exercise": exercise})


@app.route("/commitments")
def commitments():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, payload FROM responses WHERE exercise='dice' ORDER BY id"
            )
            rows = cur.fetchall()
    out = []
    for r in rows:
        p = r["payload"]
        start = p.get("start", "")
        stop = p.get("stop", "")
        text = start
        if stop:
            text = (start + "  |  " + stop) if start else stop
        out.append({"id": r["id"], "text": text or "Commitment"})
    return jsonify(out)


@app.route("/vote", methods=["POST"])
def vote():
    if states().get("dice", {}).get("status") != "voting":
        return jsonify({"ok": False, "error": "closed"})
    data = request.get_json(force=True)
    rid = int(data.get("response_id", 0))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO votes (pid, response_id) VALUES (%s,%s) "
                "ON CONFLICT (pid) DO UPDATE SET response_id=EXCLUDED.response_id, "
                "created_at=now()",
                (pid(), rid),
            )
        conn.commit()
    return jsonify({"ok": True})


@app.route("/host/<secret>")
def host(secret):
    if secret != HOST_SECRET:
        return Response("Not found", status=404)
    return Response(host_html(secret), mimetype="text/html")


@app.route("/host/<secret>/open", methods=["POST"])
def host_open(secret):
    if not require_host():
        return jsonify({"ok": False}), 404
    ex = request.get_json(force=True).get("exercise")
    set_status(ex, "open")
    return jsonify({"ok": True})


@app.route("/host/<secret>/lock", methods=["POST"])
def host_lock(secret):
    if not require_host():
        return jsonify({"ok": False}), 404
    ex = request.get_json(force=True).get("exercise")
    set_status(ex, "locked")
    return jsonify({"ok": True})


@app.route("/host/<secret>/phase", methods=["POST"])
def host_phase(secret):
    if not require_host():
        return jsonify({"ok": False}), 404
    data = request.get_json(force=True)
    set_status(data.get("exercise"), data.get("status"))
    return jsonify({"ok": True})


@app.route("/host/<secret>/clear", methods=["POST"])
def host_clear(secret):
    if not require_host():
        return jsonify({"ok": False}), 404
    ex = request.get_json(force=True).get("exercise")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM responses WHERE exercise=%s", (ex,))
            if ex == "dice":
                cur.execute("DELETE FROM votes")
            cur.execute(
                "UPDATE exercise_state SET synthesis='' WHERE exercise=%s", (ex,)
            )
        conn.commit()
    return jsonify({"ok": True})


@app.route("/host/<secret>/synthesize", methods=["POST"])
def host_synth(secret):
    if not require_host():
        return jsonify({"ok": False}), 404
    ex = request.get_json(force=True).get("exercise")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM responses WHERE exercise=%s ORDER BY id", (ex,)
            )
            rows = cur.fetchall()
    if ex == "reconnect":
        lines = []
        for r in rows:
            p = r["payload"]
            lines.append("USED: " + p.get("used", "") + " | SLIPPED: " + p.get("slipped", ""))
        prompt = (
            "You are helping a Dale Carnegie facilitator read a room of about 20 leaders "
            "six months after training. Below are anonymous responses naming one Carnegie "
            "relationship principle each person used and one that slipped. Write three "
            "short paragraphs the facilitator can read aloud. Stay anonymous and behavioral. "
            "Never name individuals. Name the common themes in what stuck, the common theme "
            "in what slipped, and one sharp sentence about the pattern to train today. "
            "Plain sentences, no lists, no dashes.\n\n" + "\n".join(lines)
        )
    else:
        lines = []
        for r in rows:
            p = r["payload"]
            lines.append("STYLE " + p.get("style", "") + ": " + p.get("text", ""))
        prompt = (
            "You are helping a Dale Carnegie facilitator debrief a DISC exercise with about "
            "20 leaders. The scenario was a tight deadline with incomplete information. Below "
            "are anonymous responses tagged by the person's self selected DISC style. Write "
            "three short paragraphs to read aloud. Name where the styles clash, where they "
            "complement each other, and one behavior the team can flex to work better together. "
            "Stay anonymous and behavioral. No lists, no dashes.\n\n" + "\n".join(lines)
        )
    text = claude_text(prompt)
    set_synthesis(ex, text)
    return jsonify({"ok": True, "synthesis": text})


@app.route("/host/<secret>/data")
def host_data(secret):
    if not require_host():
        return jsonify({"ok": False}), 404
    st = states()
    out = {"total": 20}
    with get_conn() as conn:
        with conn.cursor() as cur:
            for ex in EXERCISES:
                cur.execute(
                    "SELECT count(*) AS c FROM responses WHERE exercise=%s", (ex,)
                )
                cnt = cur.fetchone()["c"]
                out[ex] = {"status": st[ex]["status"], "count": cnt}
                out[ex]["synthesis"] = st[ex]["synthesis"]
            cur.execute(
                "SELECT id, payload FROM responses WHERE exercise='disc' ORDER BY id"
            )
            disc_items = []
            for r in cur.fetchall():
                p = r["payload"]
                disc_items.append({"style": p.get("style", ""), "text": p.get("text", "")})
            out["disc"]["items"] = disc_items
            cur.execute(
                "SELECT r.id, r.payload, "
                "(SELECT count(*) FROM votes v WHERE v.response_id=r.id) AS votes "
                "FROM responses r WHERE r.exercise='dice' ORDER BY votes DESC, r.id"
            )
            votes_list = []
            for r in cur.fetchall():
                p = r["payload"]
                start = p.get("start", "")
                stop = p.get("stop", "")
                text = start if start else stop
                if start and stop:
                    text = start + "  |  " + stop
                votes_list.append({"id": r["id"], "text": text or "Commitment", "count": r["votes"]})
            out["dice"]["votes"] = votes_list
    return jsonify(out)


def set_status(ex, status):
    if ex not in EXERCISES:
        return
    valid = ["locked", "open", "voting", "revealed"]
    if status not in valid:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE exercise_state SET status=%s WHERE exercise=%s", (status, ex)
            )
        conn.commit()


def set_synthesis(ex, text):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE exercise_state SET synthesis=%s WHERE exercise=%s", (text, ex)
            )
        conn.commit()


try:
    if DATABASE_URL:
        init_db()
except Exception:
    pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
