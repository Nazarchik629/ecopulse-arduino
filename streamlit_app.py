from __future__ import annotations

from datetime import date, timedelta
import html
import os
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="EcoPulse — живой пульс среды", page_icon="🌱", layout="wide")
st_autorefresh(interval=15_000, key="ecopulse-page-refresh")

COLORS = {"temperature": "#FF4D6D", "humidity": "#27E1FF"}
FILL = {"temperature": "rgba(255,77,109,0.10)", "humidity": "rgba(39,225,255,0.10)"}
LABELS = {"temperature": ("🌡️ Температура", "°C"), "humidity": ("💧 Влажность", "%")}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@400;500;600&display=swap');
:root{--bg:#06080F;--text:#E8ECF4;--muted:#7C86A0;--grid:#1F293D;--surface:#0D121F}
.stApp{background:radial-gradient(ellipse at 90% 4%,#12203955,transparent 27%),#06080F;color:var(--text)}
[data-testid="stHeader"]{background:transparent} .block-container{max-width:1180px;padding-top:2.5rem;padding-bottom:5rem}
h1,h2,h3{font-family:'Playfair Display',Georgia,serif!important;color:var(--text)!important;font-weight:400!important}
p,span,label,div{font-family:'DM Sans',Arial,sans-serif}
.eyebrow{color:#7C86A0;font-size:10px;letter-spacing:.16em;text-transform:uppercase;margin-bottom:10px}
.hero-title{font:400 clamp(64px,9vw,112px)/.95 'Playfair Display',Georgia,serif;letter-spacing:-.05em;margin:8px 0 18px;color:#E8ECF4}
.hero-title span{font-style:italic;color:#7C86A0}.hero-lead{font:400 22px/1.45 'Playfair Display',Georgia,serif;color:#E8ECF4}
.metric{padding:14px 0;border-bottom:1px solid #1F293D}.metric strong{display:block;font:400 38px/1.1 'Playfair Display',Georgia,serif}.metric small{color:#7C86A0;font-size:11px}
.metric.temp strong{color:#FF4D6D;text-shadow:0 0 16px #ff4d6d55}.metric.hum strong{color:#27E1FF;text-shadow:0 0 16px #27e1ff55}
.quote{border-left:1px solid #FF4D6D;padding-left:18px;font:italic 22px/1.5 'Playfair Display',Georgia,serif;color:#E8ECF4;margin-top:28px}
.step{border-top:1px solid #27E1FF55;padding-top:14px}.step b{font:500 18px 'Playfair Display',Georgia,serif}.step p{color:#7C86A0;font-size:13px}
.note{border-left:1px solid #27E1FF;padding-left:14px;color:#CBD2DF;font:15px/1.7 'Playfair Display',Georgia,serif}.tech{color:#CBD2DF;font:17px 'Playfair Display',Georgia,serif}.footer{border-top:1px solid #1F293D;padding-top:18px;color:#7C86A0;font-size:12px}
div[data-testid="stRadio"] label{background:#0D121F;border:1px solid #1F293D;border-radius:2px;padding:6px 12px;margin-right:5px}
@media(max-width:700px){.block-container{padding:1.2rem 1.1rem 4rem}.hero-lead{font-size:19px}.metric strong{font-size:32px}}
</style>
""", unsafe_allow_html=True)


def secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return os.getenv(name, default)


def demo_data() -> pd.DataFrame:
    days = []
    for i in range(10):
        day = date.today() - timedelta(days=9 - i)
        temp = 22.4 + __import__("math").sin(i * .65) * 2.1 + i * .12
        hum = 48 + __import__("math").cos(i * .55) * 10 - i * .35
        days.append({"day": day, "temperature": temp, "humidity": hum,
                     "temperature_min": temp - 2, "temperature_max": temp + 2,
                     "humidity_min": hum - 12, "humidity_max": hum + 12, "sample_count": 1})
    return pd.DataFrame(days)


@st.cache_data(ttl=15)
def load_data(url: str, anon_key: str) -> tuple[pd.DataFrame, bool]:
    if not url or not anon_key:
        return demo_data(), False
    endpoint = f"{url.rstrip('/')}/rest/v1/daily_readings?select=day,temperature,temperature_min,temperature_max,humidity,humidity_min,humidity_max,sample_count&order=day.asc&limit=10"
    try:
        response = requests.get(endpoint, headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}"}, timeout=12)
        response.raise_for_status()
        raw = pd.DataFrame(response.json())
        if raw.empty:
            return pd.DataFrame(), True
        raw["day"] = pd.to_datetime(raw["day"]).dt.date
        return raw.tail(10), True
    except Exception as error:
        st.warning(f"Не удалось получить данные из базы: {error}")
        return demo_data(), False


@st.cache_data(ttl=900, show_spinner=False)
def ai_comment(
    metric: str,
    values: tuple[float, ...],
    days: tuple[str, ...],
    provider: str,
    api_url: str,
    api_key: str,
    model: str,
) -> str:
    if not api_key or not model:
        return ""
    title, unit = LABELS[metric]
    prompt = f"Кратко, по-русски (до 35 слов), опиши тренд показателя {title} за 10 дней. Не придумывай причины. Данные: {list(zip(days, values))}; единица: {unit}."
    try:
        if provider in {"gemini", "google"}:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='-._')}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3},
            }
            response = requests.post(endpoint, json=body, headers=headers, timeout=20)
            response.raise_for_status()
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()

        if provider not in {"openai_compatible", "openai-compatible"} or not api_url:
            return ""
        body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "model": model}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        response = requests.post(api_url, json=body, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as error:
        print(f"ИИ API недоступен: {error}")
        return ""


def chart(frame: pd.DataFrame, metric: str) -> go.Figure:
    title, unit = LABELS[metric]
    color = COLORS[metric]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame["day"], y=frame[metric], mode="lines+markers", name=title,
        line={"color": color, "width": 3, "shape": "spline"}, marker={"size": 7, "color": "#06080F", "line": {"color": color, "width": 2}},
        fill="tozeroy", fillcolor=FILL[metric], hovertemplate="%{x|%d.%m} · %{y:.1f} " + unit + "<extra></extra>"))
    if f"{metric}_min" in frame and f"{metric}_max" in frame:
        fig.add_trace(go.Scatter(x=frame["day"], y=frame[f"{metric}_max"], mode="lines", line={"width": 0}, showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=frame["day"], y=frame[f"{metric}_min"], mode="lines", line={"width": 0}, fill="tonexty", fillcolor=FILL[metric], showlegend=False, hoverinfo="skip"))
    fig.update_layout(height=330, margin={"l": 4, "r": 8, "t": 12, "b": 8}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#7C86A0", "family": "DM Sans"}, showlegend=False, hovermode="x unified")
    fig.update_xaxes(showgrid=False, tickformat="%d.%m", linecolor="#1F293D", tickfont={"size": 11})
    fig.update_yaxes(title=unit, gridcolor="#1F293D", zeroline=False, tickfont={"size": 10})
    return fig


st.markdown('<p class="eyebrow">🌱 ЛИЧНАЯ МЕТЕОСТАНЦИЯ · № 01</p><div class="hero-title">Eco<span>Pulse</span></div><p class="hero-lead">Живой пульс среды.<br>Данные с датчиков Arduino за последние 10 дней.</p>', unsafe_allow_html=True)

supabase_url = secret("SUPABASE_URL")
supabase_key = secret("SUPABASE_PUBLISHABLE_KEY") or secret("SUPABASE_ANON_KEY")
ai_api_url = secret("AI_API_URL").rstrip("/")
ai_api_key = secret("AI_API_KEY")
ai_model = secret("AI_MODEL")
ai_provider = secret("AI_PROVIDER", "gemini").lower()
frame, connected = load_data(supabase_url, supabase_key)
if frame.empty:
    frame = demo_data()
    st.info("История пока пуста. Подключите Arduino и запустите скрипт отправки данных; пока показан демонстрационный пример.")
elif not connected:
    st.caption("Показаны демонстрационные данные. Настройте облачную базу, чтобы подключить Arduino.")

latest = frame.iloc[-1]
if connected and supabase_url and supabase_key:
    try:
        response = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/readings?select=created_at,temperature,humidity&order=created_at.desc&limit=1", headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}, timeout=8)
        if response.ok and response.json():
            latest = response.json()[0]
    except Exception:
        pass

st.markdown('<p class="eyebrow">⚡ ТЕКУЩИЕ ПОКАЗАНИЯ</p>', unsafe_allow_html=True)
c1,c2=st.columns(2)
for col,key,css,emoji,label in [(c1,"temperature","temp","🌡️","температура · °C"),(c2,"humidity","hum","💧","влажность · %")]:
    value=float(latest.get(key,0))
    col.markdown(f'<div class="metric {css}"><strong>{emoji} {value:.1f}</strong><small>{label}</small></div>',unsafe_allow_html=True)
st.caption("🟢 Облако подключено" if connected and supabase_url else "⚡ Демо-режим · облачная база не настроена")

st.divider()
st.markdown('<p class="eyebrow">01 / ЗАМЫСЕЛ</p>',unsafe_allow_html=True)
a,b=st.columns([1,1.2],gap="large")
with a: st.header("У среды есть\nсвой ритм.")
with b:
    st.write("EcoPulse измеряет окружающий мир простой платой Arduino и превращает сырые числа в понятную историю о температуре и влажности. Маленький датчик помогает увидеть, как меняются комната или теплица. Такие наблюдения помогают обсуждать экологию на основе данных.")
    st.markdown('<div class="quote">«Сначала замечаем перемены.<br>Потом понимаем, что можем изменить».</div>',unsafe_allow_html=True)

st.divider(); st.markdown('<p class="eyebrow">02 / ПУТЬ ДАННЫХ</p>',unsafe_allow_html=True); st.header("Как это работает")
steps=st.columns(4)
for col,emoji,title,desc in zip(steps,["🌡️","🔌","📡","🌐"],["Датчики измеряют","Arduino собирает","Данные идут на ПК","Сайт показывает"],["Температуру и влажность.","Плата превращает их в числа.","Скрипт отправляет измерения в облако.","Streamlit строит историю и графики."]):
    col.markdown(f'<div class="step"><span>{emoji}</span><br><b>{title}</b><p>{desc}</p></div>',unsafe_allow_html=True)

st.divider(); st.markdown('<p class="eyebrow">03 / НАБЛЮДЕНИЯ</p>',unsafe_allow_html=True); st.header("Последние 10 дней")
metrics=list(LABELS); selected=st.radio("Показатель графика",metrics,format_func=lambda key:LABELS[key][0],horizontal=True,label_visibility="collapsed")
left,right=st.columns([3,1],gap="large")
with left:
    st.plotly_chart(chart(frame,selected),use_container_width=True,config={"displayModeBar":False})
with right:
    values=frame[selected].astype(float); unit=LABELS[selected][1]
    weights=frame["sample_count"].astype(float) if "sample_count" in frame else pd.Series(1.0,index=frame.index)
    average=float((values*weights).sum()/weights.sum())
    period_max=float(frame[f"{selected}_max"].max()) if f"{selected}_max" in frame else float(values.max())
    period_min=float(frame[f"{selected}_min"].min()) if f"{selected}_min" in frame else float(values.min())
    st.markdown('<p class="eyebrow">СВОДКА · 10 ДНЕЙ</p>',unsafe_allow_html=True)
    st.metric("Среднее",f"{average:.1f} {unit}");st.metric("Максимум",f"{period_max:.1f} {unit}");st.metric("Минимум",f"{period_min:.1f} {unit}")
    st.caption("Средние значения по каждому дню")

st.divider(); st.markdown('<p class="eyebrow">04 / ИСТОРИЯ ДАТЧИКОВ</p>',unsafe_allow_html=True); st.header("Функции")
for key in metrics:
    title,unit=LABELS[key]; st.subheader(title)
    ca,cb=st.columns([1,1.5],gap="large")
    with ca:
        commentary=ai_comment(key,tuple(round(float(v),2) for v in frame[key]),tuple(str(d) for d in frame["day"]),ai_provider,ai_api_url,ai_api_key,ai_model)
        ai_used=bool(commentary)
        if not commentary:
            vals=frame[key].astype(float); direction="растёт" if vals.iloc[-1]>vals.iloc[0] else "снижается"
            commentary=f"За последние дни показатель {direction}. Среднее значение — {vals.mean():.1f} {unit}. Следите за новыми измерениями, чтобы увидеть, сохранится ли этот тренд."
        st.markdown('<p class="eyebrow">🤖 КОММЕНТАРИЙ ИИ</p>',unsafe_allow_html=True)
        st.markdown(f'<div class="note">{html.escape(commentary)}</div>',unsafe_allow_html=True)
        st.caption("Комментарий создан автоматически по данным графика" if ai_used else "Локальный комментарий по статистике; ИИ API можно подключить через Secrets")
    with cb: st.plotly_chart(chart(frame,key),use_container_width=True,config={"displayModeBar":False},key=f"mini-{key}")

st.divider();st.markdown('<p class="eyebrow">ТЕХНОЛОГИИ</p><p class="tech">🔌 Arduino UNO　·　🌡️ DHT11/DHT22　·　📡 USB → облако　·　🤖 ИИ API</p>',unsafe_allow_html=True)
st.markdown('<div class="footer">EcoPulse — учебный экологический проект <span style="float:right">2026</span></div>',unsafe_allow_html=True)
