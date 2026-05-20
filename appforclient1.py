"""
📸 InstaTrend URL Analyzer
Аналитика конкретных Instagram Reels по прямым ссылкам
(100% Бесплатно, без API, использует yt-dlp)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import time
import re
import requests
from datetime import datetime

# ─────────────────────────────────────────────
# КОНФИГУРАЦИЯ СТРАНИЦЫ И СТИЛИ
# ─────────────────────────────────────────────
st.set_page_config(page_title="InstaTrend URL Analyzer", page_icon="🔗", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
section[data-testid="stSidebar"] { background: #0e0e11; border-right: 1px solid #2a2a2a; }
.kpi-card { background: linear-gradient(135deg, #833ab4 0%, #fd1d1d 50%, #fcb045 100%); padding: 2px; border-radius: 12px; transition: transform 0.2s;}
.kpi-inner { background: #1a1a24; border-radius: 10px; padding: 18px; text-align: center; height: 100%;}
.kpi-card:hover { transform: translateY(-3px); }
.kpi-value { font-size: 2.2rem; font-weight: 700; color: #fff; line-height: 1.1;}
.kpi-label { font-size: 0.85rem; color: #aaa; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.5px;}
.ig-card { background: #1a1a24; border: 1px solid #2a2a35; border-radius: 12px; padding: 16px; margin-bottom: 15px;}
.ig-card:hover { border-color: #fd1d1d; }
.score-bar { background: #2a2a35; border-radius: 6px; height: 8px; margin-top: 10px; overflow: hidden;}
.score-fill { background: linear-gradient(90deg, #fd1d1d, #fcb045); height: 100%; }
.ai-box { background: #1a2a1a; border-left: 4px solid #66bb6a; padding: 16px; border-radius: 8px; margin-bottom: 20px;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────
def fmt_number(n):
    if n is None: return "0"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}М"
    if n >= 1_000: return f"{n/1_000:.1f}К"
    return str(int(n))

def calc_score(views, likes, comments, days_ago):
    if views < 100: return 0
    er = (likes + comments * 3) / max(views, 1)
    recency = max(0, 1 - days_ago / 90)
    velocity = views / max(days_ago, 1)
    score = (min(views / 1_000_000 * 40, 40) + min(er * 2000, 30) + recency * 15 + min(velocity / 10_000 * 15, 15))
    return min(int(score), 100)

def extract_tags(caption):
    if not caption: return []
    return re.findall(r"#(\w+)", caption.lower())

def call_openai_api(api_key, ref_caption, context):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    system_prompt = "Ты сценарист для Instagram Reels. Твоя задача — анализировать вирусные видео конкурентов и писать на их основе новые, адаптированные под клиента сценарии."
    user_prompt = f"Оригинал конкурента:\n\"{ref_caption}\"\n\nНаш оффер:\n\"{context}\"\n\nНапиши сценарий: 1. ХУК (0-3 сек). 2. ВИЗУАЛ. 3. ТЕКСТ ОЗВУЧКИ. 4. CTA."
    
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": 0.7}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)


# ─────────────────────────────────────────────
# ПАРСЕР ПО ССЫЛКАМ ЧЕРЕЗ YT-DLP
# ─────────────────────────────────────────────
def parse_ig_urls(urls):
    try:
        import yt_dlp
    except ImportError:
        return None, "Библиотека yt-dlp не установлена. Запустите: pip install yt-dlp"

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    data = []
    failed_urls = []
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for idx, url in enumerate(urls):
            url = url.strip()
            if not url:
                continue
                
            progress_text.text(f"🔍 Анализ видео {idx+1}/{len(urls)}: {url}")
            
            try:
                info = ydl.extract_info(url, download=False)
                
                # Извлекаем данные (yt-dlp вытаскивает их из метатегов IG)
                views = info.get('view_count') or 0
                likes = info.get('like_count') or 0
                comments = info.get('comment_count') or 0
                caption = info.get('description') or info.get('title') or ""
                author = info.get('uploader') or info.get('channel') or "Неизвестно"
                timestamp = info.get('timestamp')
                
                if timestamp:
                    pub_date = datetime.fromtimestamp(timestamp)
                    days_ago = (datetime.now() - pub_date).days
                    date_str = pub_date.strftime("%Y-%m-%d")
                else:
                    days_ago = 30
                    date_str = "Н/Д"

                # Эвристика: если IG скрыл просмотры, восстанавливаем через лайки
                if views == 0 and likes > 0:
                    views = likes * 12

                data.append({
                    "url": url,
                    "author": f"@{author}",
                    "date": date_str,
                    "days_ago": days_ago,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "caption": caption,
                    "tags": extract_tags(caption),
                    "score": calc_score(views, likes, comments, days_ago)
                })
            except Exception as e:
                failed_urls.append(url)
                
            progress_bar.progress((idx + 1) / len(urls))
            
    progress_text.empty()
    progress_bar.empty()
    
    return data, failed_urls

# ─────────────────────────────────────────────
# БОКОВАЯ ПАНЕЛЬ И ВВОД ДАННЫХ
# ─────────────────────────────────────────────
if "ig_df" not in st.session_state: st.session_state.ig_df = pd.DataFrame()
if "openai_key" not in st.session_state: st.session_state.openai_key = ""

with st.sidebar:
    st.markdown("## 🔗 InstaTrend URL")
    st.markdown("Анализ Reels по прямым ссылкам")
    st.markdown("---")
    
    st.markdown("### 1. Вставьте ссылки на Reels")
    st.markdown("<span style='font-size:0.8rem; color:#888;'>Каждая ссылка с новой строки</span>", unsafe_allow_html=True)
    
    default_urls = """https://www.instagram.com/reel/C3tQ8vWIKpM/
https://www.instagram.com/reel/C4Hk9_1I5jH/
https://www.instagram.com/reel/C5M-X_6I0uJ/"""
    
    urls_input = st.text_area("Ссылки Instagram:", value=default_urls, height=200)
    
    run_btn = st.button("🚀 Анализировать", type="primary", use_container_width=True)
    
    st.markdown("---")
    st.markdown("### ⚙️ OpenAI API Ключ (Для копирайтера)")
    new_key = st.text_input("sk-...", value=st.session_state.openai_key, type="password")
    if st.button("💾 Сохранить ключ"):
        st.session_state.openai_key = new_key
        st.success("Сохранено!")


# ─────────────────────────────────────────────
# ИНТЕРФЕЙС И ОТОБРАЖЕНИЕ
# ─────────────────────────────────────────────
st.markdown("# 🔗 InstaTrend: Анализ по ссылкам")
st.markdown("Сбор статистики и генерация идей без риска блокировки аккаунта.")

if run_btn:
    urls_list = [u for u in urls_input.split('\n') if u.strip().startswith('http')]
    if not urls_list:
        st.warning("Введите хотя бы одну корректную ссылку (http...)")
    else:
        results, failed = parse_ig_urls(urls_list)
        
        if failed:
            st.warning(f"⚠️ Не удалось проанализировать {len(failed)} ссылок (возможно пост удален или доступ закрыт).")
            
        if results:
            df = pd.DataFrame(results)
            df = df.sort_values("score", ascending=False).reset_index(drop=True)
            st.session_state.ig_df = df
            st.success(f"✅ Успешно проанализировано {len(df)} Reels!")
        else:
            st.error("❌ Не удалось получить данные ни по одной ссылке.")
            st.session_state.ig_df = pd.DataFrame()

df = st.session_state.ig_df

if df.empty:
    st.info("👈 Вставьте ссылки в меню слева и нажмите **«Анализировать»**")
    st.stop()


# ─────────────────────────────────────────────
# ВКЛАДКИ (Как в предыдущей версии)
# ─────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🏆 Разбор ссылок", "📊 Сводная Аналитика", "🤖 ИИ Копирайтер"])

# ════════════════════════════════════════════
# ВКЛАДКА 1: РАЗБОР
# ════════════════════════════════════════════
with tab1:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"<div class='kpi-card'><div class='kpi-inner'><div class='kpi-value'>{fmt_number(df['views'].sum())}</div><div class='kpi-label'>Просмотров</div></div></div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='kpi-card'><div class='kpi-inner'><div class='kpi-value'>{int(df['score'].mean())}</div><div class='kpi-label'>Ср. Залётность</div></div></div>", unsafe_allow_html=True)
    with c3:
        avg_er = ((df['likes'] + df['comments']) / df['views'].replace(0,1)).mean() * 100
        st.markdown(f"<div class='kpi-card'><div class='kpi-inner'><div class='kpi-value'>{avg_er:.1f}%</div><div class='kpi-label'>Ср. ER (Вовлеч.)</div></div></div>", unsafe_allow_html=True)
    with c4:
        st.markdown(f"<div class='kpi-card'><div class='kpi-inner'><div class='kpi-value'>{len(df)}</div><div class='kpi-label'>Успешных видео</div></div></div>", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    for i, row in df.iterrows():
        score = row['score']
        color = "#fd1d1d" if score > 80 else ("#fcb045" if score > 50 else "#833ab4")
        
        st.markdown(f"""
        <div class='ig-card'>
            <div style='display:flex; justify-content:space-between; align-items:flex-start;'>
                <div style='flex:1;'>
                    <h4 style='margin:0; color:#fff;'>👤 {row['author']} <span style='font-weight:400; color:#888; font-size:0.9rem;'>• {row['days_ago']} дней назад</span></h4>
                    <p style='margin:10px 0; color:#ddd; font-size:0.95rem; line-height:1.4;'>{row['caption'][:300]}{'...' if len(row['caption'])>300 else ''}</p>
                    <div style='display:flex; gap:15px; color:#aaa; font-size:0.9rem;'>
                        <span>👁 <b>{fmt_number(row['views'])}</b></span>
                        <span>❤️ <b>{fmt_number(row['likes'])}</b></span>
                        <span>💬 <b>{fmt_number(row['comments'])}</b></span>
                    </div>
                </div>
                <div style='width: 150px; text-align:right;'>
                    <div style='font-size:1.8rem; font-weight:700; color:{color};'>{score} <span style='font-size:1rem; color:#888;'>/100</span></div>
                    <div style='font-size:0.8rem; color:#888; margin-top:-5px;'>Залётность</div>
                    <div class='score-bar'><div class='score-fill' style='width:{score}%; background:{color};'></div></div>
                    <a href='{row['url']}' target='_blank' style='display:inline-block; margin-top:15px; padding:6px 12px; background:#fff; color:#000; text-decoration:none; border-radius:4px; font-weight:600; font-size:0.85rem;'>Смотреть →</a>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ════════════════════════════════════════════
# ВКЛАДКА 2: АНАЛИТИКА
# ════════════════════════════════════════════
with tab2:
    df['engagement_rate'] = (df['likes'] + df['comments']) / df['views'].replace(0,1) * 100

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig_scatter = px.scatter(df, x='views', y='engagement_rate', size='score', color='days_ago',
                                hover_name='author', title='Просмотры vs Вовлеченность',
                                color_continuous_scale='Sunsetdark')
        fig_scatter.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd")
        st.plotly_chart(fig_scatter, use_container_width=True)
        
    with col_g2:
        top_er = df.nlargest(10, 'engagement_rate').sort_values('engagement_rate')
        fig_er = px.bar(top_er, x='engagement_rate', y='author', orientation='h',
                       title='Топ по Вовлеченности (ER %)',
                       color='score', color_continuous_scale='Sunsetdark')
        fig_er.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd")
        st.plotly_chart(fig_er, use_container_width=True)

    st.markdown("### 📋 Таблица данных")
    display_df = df[['author', 'date', 'views', 'likes', 'comments', 'engagement_rate', 'score', 'url']]
    st.dataframe(display_df.style.format({'views': '{:,.0f}', 'likes': '{:,.0f}', 'engagement_rate': '{:.1f}%'}), use_container_width=True)


# ════════════════════════════════════════════
# ВКЛАДКА 3: ИИ КОПИРАЙТЕР
# ════════════════════════════════════════════
with tab3:
    st.markdown("<div class='ai-box'>🤖 <b>ИИ Сценарист</b> — Пишет сценарии на основе разобранных вами ссылок.</div>", unsafe_allow_html=True)
    
    if not st.session_state.openai_key:
        st.warning("⚠️ Введите API-ключ OpenAI в боковой панели, чтобы генерировать тексты прямо здесь.")
    else:
        st.markdown("### 1. Выберите референс (из ваших ссылок)")
        ref_options = [f"[{row['score']}/100] {row['author']} - 👁 {fmt_number(row['views'])} - {row['caption'][:50]}..." for _, row in df.iterrows()]
        selected_ref = st.selectbox("Видео для адаптации:", ref_options)
        
        ref_idx = ref_options.index(selected_ref)
        ref_caption = df.iloc[ref_idx]['caption']
        
        st.markdown("### 2. Укажите ваш оффер")
        context = st.text_area("Что мы рекламируем?", placeholder="Например: Делаем бесплатную диагностику iPhone при залитии водой.")
        
        if st.button("✨ Сгенерировать сценарий", type="primary"):
            if not context:
                st.error("Пожалуйста, заполните ваш оффер.")
            else:
                with st.spinner("🧠 ИИ пишет сценарий..."):
                    script, err = call_openai_api(st.session_state.openai_key, ref_caption, context)
                    if err:
                        st.error(f"Ошибка API: {err}")
                    else:
                        st.success("✅ Сценарий готов!")
                        st.markdown("<div style='background:#1e1e2e; padding:20px; border-radius:10px; border:1px solid #4a4a5a;'>", unsafe_allow_html=True)
                        st.markdown(script)
                        st.markdown("</div>", unsafe_allow_html=True)