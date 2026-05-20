"""
📸 InstaTrend Pro v2.0
Парсер Instagram Reels + Глубокая Аналитика + ИИ Копирайтер
(Без платных API для парсинга, использует Instaloader)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import re
import requests
from datetime import datetime
import instaloader

# ─────────────────────────────────────────────
# КОНФИГУРАЦИЯ СТРАНИЦЫ И СТИЛИ
# ─────────────────────────────────────────────
st.set_page_config(page_title="InstaTrend Pro", page_icon="📸", layout="wide")

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
.warning-box { background: #2d1a1a; border-left: 4px solid #fd1d1d; padding: 12px 16px; border-radius: 4px; color: #f8b4b4; font-size: 0.85rem; margin-bottom: 15px;}
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
    """Вызов OpenAI API для генерации сценария"""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    system_prompt = "Ты креативный сценарист для Instagram Reels. Твоя задача — анализировать вирусные видео конкурентов и писать на их основе новые, адаптированные под клиента сценарии."
    user_prompt = f"""
Оригинальный текст успешного видео конкурента:
"{ref_caption}"

Контекст и оффер нашего клиента:
"{context}"

Задача: Напиши готовый сценарий для Reels. 
Формат ответа строго по пунктам:
1. ХУК (0-3 секунды) — цепляющая фраза или действие.
2. ВИЗУАЛ — что именно снимать, какой план, что в кадре.
3. ТЕКСТ ОЗВУЧКИ — динамичный текст на 15-30 секунд.
4. ПРИЗЫВ К ДЕЙСТВИЮ (CTA) — как перевести зрителя в клиента.
"""
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)


# ─────────────────────────────────────────────
# ОСНОВНОЙ ПАРСЕР INSTAGRAM
# ─────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def scrape_instagram(hashtag, limit, min_views, username, password, delay):
    L = instaloader.Instaloader(
        quiet=True, video_metadata_formats=[], download_pictures=False, 
        download_videos=False, download_video_thumbnails=False,
        download_geotags=False, download_comments=False, save_metadata=False
    )
    
    if username and password:
        try:
            L.login(username, password)
        except instaloader.exceptions.BadCredentialsException:
            return None, "Неверный логин или пароль."
        except instaloader.exceptions.TwoFactorAuthRequiredException:
            return None, "Требуется 2FA. Отключите её на фейковом аккаунте."
        except Exception as e:
            return None, f"Ошибка входа: {str(e)}"

    clean_tag = hashtag.replace("#", "").replace(" ", "").strip()
    data = []
    
    try:
        tag_obj = instaloader.Hashtag.from_name(L.context, clean_tag)
        posts = tag_obj.get_top_posts()
        
        count = 0
        for post in posts:
            if count >= limit: break
            if not post.is_video: continue

            likes = post.likes
            comments = post.comments
            views = post.video_view_count
            
            if not views or views == 0:
                views = (likes * 12) if likes > 0 else 0
                    
            if views < min_views: continue

            days_ago = (datetime.now() - post.date).days
            
            data.append({
                "shortcode": post.shortcode,
                "url": f"https://www.instagram.com/p/{post.shortcode}/",
                "author": f"@{post.owner_username}",
                "date": post.date.strftime("%Y-%m-%d"),
                "days_ago": days_ago,
                "views": views,
                "likes": likes,
                "comments": comments,
                "caption": post.caption or "",
                "tags": extract_tags(post.caption),
                "score": calc_score(views, likes, comments, days_ago)
            })
            
            count += 1
            if delay > 0: time.sleep(delay)
                
        return data, None
        
    except instaloader.exceptions.LoginRequiredException:
        return None, "Instagram заблокировал анонимный доступ. Нужен логин/пароль."
    except Exception as e:
        if "429" in str(e):
            return None, "Слишком много запросов (Rate Limit 429). Увеличьте задержку."
        return None, f"Ошибка парсинга: {str(e)}"


# ─────────────────────────────────────────────
# БОКОВАЯ ПАНЕЛЬ
# ─────────────────────────────────────────────
if "ig_df" not in st.session_state: st.session_state.ig_df = pd.DataFrame()
if "openai_key" not in st.session_state: st.session_state.openai_key = ""

with st.sidebar:
    st.markdown("## 📸 InstaTrend Pro")
    st.markdown("Аналитика IG Reels и ИИ")
    st.markdown("---")
    
    st.markdown("### 1. Доступ к Instagram")
    st.markdown("""<div class='warning-box' style='padding:8px; font-size:0.75rem;'>
    Используйте <b>фейковый</b> аккаунт для парсинга.
    </div>""", unsafe_allow_html=True)
    ig_user = st.text_input("Логин IG", placeholder="user123_test")
    ig_pass = st.text_input("Пароль IG", type="password")
    
    st.markdown("---")
    st.markdown("### 2. Параметры поиска")
    query = st.text_input("Хэштег (без #)", "ремонттелефонов")
    
    col1, col2 = st.columns(2)
    with col1:
        limit = st.number_input("Искать видео", min_value=10, max_value=200, value=50, step=10)
    with col2:
        delay = st.slider("Пауза (сек)", 0.0, 5.0, 1.5)
        
    min_views = st.number_input("Минимум просмотров", min_value=0, value=5000, step=1000)
    
    run_btn = st.button("🚀 Начать парсинг", type="primary", use_container_width=True)

# ─────────────────────────────────────────────
# ИНТЕРФЕЙС И ОТОБРАЖЕНИЕ
# ─────────────────────────────────────────────
st.markdown("# 📸 InstaTrend Pro: Аналитика Reels")

if run_btn:
    if not query:
        st.warning("Введите хэштег для поиска!")
    else:
        with st.spinner("🕵️‍♂️ Собираем видео. Имитируем поведение человека (задержка включена)..."):
            results, error = scrape_instagram(query, limit, min_views, ig_user, ig_pass, delay)
            
            if error:
                st.error(f"❌ Ошибка: {error}")
            elif not results:
                st.warning("🤷‍♂️ По вашему запросу ничего не найдено (или отфильтровалось).")
                st.session_state.ig_df = pd.DataFrame()
            else:
                df = pd.DataFrame(results)
                df = df.sort_values("score", ascending=False).reset_index(drop=True)
                st.session_state.ig_df = df
                st.success(f"✅ Успешно собрано {len(df)} Reels!")

df = st.session_state.ig_df

if df.empty:
    st.info("👈 Настройте параметры слева и нажмите **«Начать парсинг»**")
    st.stop()


# ─────────────────────────────────────────────
# ВКЛАДКИ
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🏆 Топ Reels", "📊 Глубокая Аналитика", "🤖 ИИ Копирайтер", "⚙️ Настройки"])

# ════════════════════════════════════════════
# ВКЛАДКА 1: ТОП REELS
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
        st.markdown(f"<div class='kpi-card'><div class='kpi-inner'><div class='kpi-value'>{len(df)}</div><div class='kpi-label'>Видео в топе</div></div></div>", unsafe_allow_html=True)
        
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
                    <a href='{row['url']}' target='_blank' style='display:inline-block; margin-top:15px; padding:6px 12px; background:#fff; color:#000; text-decoration:none; border-radius:4px; font-weight:600; font-size:0.85rem;'>Смотреть Reels →</a>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ════════════════════════════════════════════
# ВКЛАДКА 2: ГЛУБОКАЯ АНАЛИТИКА
# ════════════════════════════════════════════
with tab2:
    df['engagement_rate'] = (df['likes'] + df['comments']) / df['views'].replace(0,1) * 100
    
    st.markdown("### 📈 Динамика публикаций (когда выложили топ-ролики)")
    df_time = df.copy()
    df_time['date_dt'] = pd.to_datetime(df_time['date'])
    timeline = df_time.groupby(df_time['date_dt'].dt.to_period("D").astype(str))['views'].sum().reset_index()
    fig_time = px.line(timeline, x='date_dt', y='views', markers=True, 
                       title="Суммарные просмотры по дате публикации",
                       color_discrete_sequence=['#fcb045'])
    fig_time.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd", xaxis_title="Дата", yaxis_title="Просмотры")
    fig_time.update_xaxes(gridcolor="#2a2a35"); fig_time.update_yaxes(gridcolor="#2a2a35")
    st.plotly_chart(fig_time, use_container_width=True)

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig_scatter = px.scatter(df, x='views', y='engagement_rate', size='score', color='days_ago',
                                hover_name='author', hover_data=['likes'], 
                                title='Просмотры vs Вовлеченность (ER %)',
                                color_continuous_scale='Sunsetdark')
        fig_scatter.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd")
        fig_scatter.update_xaxes(gridcolor="#2a2a35"); fig_scatter.update_yaxes(gridcolor="#2a2a35")
        st.plotly_chart(fig_scatter, use_container_width=True)
        
    with col_g2:
        top_er = df.nlargest(10, 'engagement_rate').sort_values('engagement_rate')
        fig_er = px.bar(top_er, x='engagement_rate', y='author', orientation='h',
                       title='Лидеры по Вовлеченности (Топ-10)',
                       color='score', color_continuous_scale='Sunsetdark')
        fig_er.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd")
        fig_er.update_xaxes(gridcolor="#2a2a35")
        st.plotly_chart(fig_er, use_container_width=True)

    st.markdown("### 🏷️ Облако тегов (Treemap)")
    all_tags = [t for tags_list in df['tags'] for t in tags_list]
    if all_tags:
        tag_counts = pd.Series(all_tags).value_counts().reset_index()
        tag_counts.columns = ['Тег', 'Частота']
        tag_counts = tag_counts[~tag_counts['Тег'].str.contains(query.replace("#", "").lower())] # Убираем базовый
        
        fig_tags = px.treemap(tag_counts.head(40), path=['Тег'], values='Частота',
                             color='Частота', color_continuous_scale='Purpor')
        fig_tags.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd", margin=dict(t=10, l=10, r=10, b=10))
        st.plotly_chart(fig_tags, use_container_width=True)

    st.markdown("### 📋 Таблица данных")
    display_df = df[['author', 'date', 'views', 'likes', 'comments', 'engagement_rate', 'score', 'url']]
    display_df = display_df.rename(columns={'author':'Автор', 'date':'Дата', 'views':'Просмотры', 'likes':'Лайки', 'comments':'Комменты', 'engagement_rate':'ER %', 'score':'Рейтинг', 'url':'Ссылка'})
    st.dataframe(display_df.style.format({'Просмотры': '{:,.0f}', 'Лайки': '{:,.0f}', 'ER %': '{:.1f}%'}), use_container_width=True)
    
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Скачать таблицу в CSV", data=csv, file_name=f"instatrend_{query}.csv", mime="text/csv")


# ════════════════════════════════════════════
# ВКЛАДКА 3: ИИ КОПИРАЙТЕР
# ════════════════════════════════════════════
with tab3:
    st.markdown("<div class='ai-box'>🤖 <b>ИИ Сценарист</b> — Автоматически пишет сценарии для ваших Reels, копируя структуру залетающих видео конкурентов.</div>", unsafe_allow_html=True)
    
    if not st.session_state.openai_key:
        st.warning("⚠️ Для работы автоматического генератора введите API-ключ OpenAI во вкладке «Настройки».")
        st.markdown("Либо скопируйте шаблон ниже и вставьте его вручную в ChatGPT:")
        
        top_vid = df.iloc[0]
        st.code(f"""Я владелец бизнеса по ремонту смартфонов.
Изучи текст вирусного Reels конкурента:
"{top_vid['caption'][:500]}"

Напиши мне сценарий для похожего видео:
1. Хук (0-3 сек)
2. Визуал (что в кадре)
3. Озвучка
4. Призыв к действию""", language="text")
        
    else:
        st.markdown("### 1. Выберите референс (залетающее видео)")
        ref_options = [f"[{row['score']}/100] {row['author']} - 👁 {fmt_number(row['views'])} - {row['caption'][:50]}..." for _, row in df.head(10).iterrows()]
        selected_ref = st.selectbox("Видео для адаптации:", ref_options)
        
        ref_idx = ref_options.index(selected_ref)
        ref_caption = df.iloc[ref_idx]['caption']
        
        st.markdown("### 2. Укажите ваш оффер (Контекст)")
        context = st.text_area("Что мы рекламируем?", placeholder="Например: Делаем бесплатную диагностику iPhone при залитии водой. Находимся в Москве, м. Бауманская.")
        
        if st.button("✨ Сгенерировать сценарий", type="primary"):
            if not context:
                st.error("Пожалуйста, заполните ваш оффер.")
            else:
                with st.spinner("🧠 ИИ анализирует референс и пишет сценарий..."):
                    script, err = call_openai_api(st.session_state.openai_key, ref_caption, context)
                    if err:
                        st.error(f"Ошибка API: {err}")
                    else:
                        st.success("✅ Сценарий готов!")
                        st.markdown("<div style='background:#1e1e2e; padding:20px; border-radius:10px; border:1px solid #4a4a5a;'>", unsafe_allow_html=True)
                        st.markdown(script)
                        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════
# ВКЛАДКА 4: НАСТРОЙКИ
# ════════════════════════════════════════════
with tab4:
    st.markdown("### ⚙️ Интеграция с нейросетями")
    st.markdown("Для работы вкладки «ИИ Копирайтер» необходим API-ключ от OpenAI (ChatGPT).")
    
    new_key = st.text_input("OpenAI API Key (sk-...)", value=st.session_state.openai_key, type="password")
    if st.button("💾 Сохранить ключ"):
        st.session_state.openai_key = new_key
        st.success("Ключ сохранен в текущей сессии!")
        
    st.markdown("---")
    st.markdown("### 🔧 Системные требования")
    st.code("pip install streamlit pandas plotly instaloader requests", language="bash")