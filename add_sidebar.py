import bs4
from bs4 import BeautifulSoup

with open("lotto_ai.html", "r", encoding="utf-8") as f:
    html = f.read()

# 1. Update Layout CSS
css_addition = """
        /* ─ Sidebar Navigation ─ */
        .layout-container {
            max-width: 1440px; margin: 2.5rem auto; padding: 0 1.5rem;
            display: grid; grid-template-columns: 240px 1fr; gap: 2.5rem;
            align-items: start;
        }
        @media(max-width:1100px) {
            .layout-container { grid-template-columns: 1fr; }
        }
        
        .sidebar {
            background: var(--card); border: 1px solid rgba(255,255,255,0.5);
            border-radius: 1.5rem; padding: 1.5rem 1rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.04);
            position: sticky; top: 100px;
        }
        
        .side-nav { display: flex; flex-direction: column; gap: 0.5rem; }
        .nav-item {
            display: flex; align-items: center; gap: 12px; padding: 1rem 1.2rem;
            border-radius: 1rem; cursor: pointer; color: var(--text-muted);
            font-weight: 700; font-size: 1.05rem; transition: all 0.3s ease;
        }
        .nav-item:hover { background: #F3F4F6; color: var(--text-main); }
        .nav-item.active {
            background: var(--primary); color: #fff;
            box-shadow: 0 4px 15px rgba(79, 70, 229, 0.3);
        }
        .nav-icon { font-size: 1.25rem; }
        
        /* ─ View Sections ─ */
        .view-section { display: none; animation: fadeIn 0.4s ease; }
        .view-section.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        
        /* Inner Grid for Main View */
        .main-view-grid {
            display: grid; grid-template-columns: 1fr 400px; gap: 2rem;
        }
        @media(max-width:960px) { .main-view-grid { grid-template-columns: 1fr; } }
        
        /* Analysis UI */
        .analysis-filters {
            display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;
        }
        .filter-select {
            padding: 0.8rem 1rem; border: 2px solid var(--border); border-radius: 0.8rem;
            font-family: inherit; font-size: 0.95rem; outline: none; background: #fff;
        }
        .analysis-stat-grid {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1.2rem; margin-bottom: 1.5rem;
        }
        .stat-card {
            background: #F8FAFC; border-radius: 1rem; padding: 1.2rem; text-align: center; border: 1px solid var(--border);
        }
        .stat-title { font-size: 0.85rem; color: var(--text-muted); font-weight: 700; margin-bottom: 0.5rem;}
        .stat-value { font-size: 1.5rem; font-weight: 900; color: var(--primary); }
"""

# Replace `.wrap` CSS rule with nothing inside style to avoid duplication,
# but using `replace` might be tricky. Let's just insert before `</style>`.
html = html.replace("</style>", css_addition + "\n</style>")
html = html.replace(".wrap { \n            max-width: 1200px; margin: 2.5rem auto; padding: 0 1.5rem; \n            display: grid; grid-template-columns: 1fr 400px; gap: 2rem; \n        }", "")
html = html.replace("@media(max-width:960px){ .wrap{grid-template-columns: 1fr;} }", "")

# 2. Restructure HTML Body
# We need to wrap the contents inside `<div class="wrap">` with our new structure.
soup = BeautifulSoup(html, "html.parser")
wrap_div = soup.find("div", class_="wrap")

if wrap_div:
    wrap_div['class'] = "main-view-grid"
    
    # Create Layout Container
    layout_container = soup.new_tag("div", **{"class": "layout-container"})
    
    # Create Sidebar
    sidebar = BeautifulSoup('''
        <aside class="sidebar">
            <nav class="side-nav">
                <a class="nav-item active" onclick="switchNavTab('main')">
                    <span class="nav-icon">🎱</span> Main
                </a>
                <a class="nav-item" onclick="switchNavTab('lotto')">
                    <span class="nav-icon">📊</span> 로또분석
                </a>
                <a class="nav-item" onclick="switchNavTab('youtube')">
                    <span class="nav-icon">▶️</span> 유튜브
                </a>
                <a class="nav-item" onclick="switchNavTab('invest')">
                    <span class="nav-icon">📈</span> 투자(주식/코인)
                </a>
            </nav>
        </aside>
    ''', "html.parser")
    
    # Create Main Content Area
    main_area = soup.new_tag("main", **{"class": "content-area"})
    
    # Main View
    view_main = soup.new_tag("div", **{"id": "view-main", "class": "view-section active"})
    view_main.append(wrap_div.extract())
    
    # Analysis View
    view_lotto = BeautifulSoup('''
        <div id="view-lotto" class="view-section">
            <div class="card" style="margin-bottom: 2rem;">
                <div class="card-title">📊 정밀 로또 데이터 분석</div>
                <div class="analysis-filters">
                    <select class="filter-select" id="analysisPeriod">
                        <option value="1year">최근 1년 (기본)</option>
                        <option value="6months">최근 6개월</option>
                        <option value="3months">최근 3개월</option>
                        <option value="all">역대 전체</option>
                    </select>
                    <select class="filter-select" id="analysisType">
                        <option value="all">전체 구매 방식</option>
                        <option value="auto">자동</option>
                        <option value="manual">수동</option>
                    </select>
                    <button class="btn btn-primary" onclick="alert('분석을 시작합니다.')">🔍 분석 실행</button>
                </div>
                
                <h3 style="font-size:1.05rem; margin-bottom:1rem; color:var(--text-main);">🏆 가장 많이 나온 번호 빈도 분석</h3>
                <div class="analysis-stat-grid" id="freqStats">
                    <div class="stat-card">
                        <div class="stat-title">1위 번호 (출현 78회)</div>
                        <div class="ball c1" style="margin: 0 auto;">34</div>
                    </div>
                     <div class="stat-card">
                        <div class="stat-title">2위 번호 (출현 72회)</div>
                        <div class="ball c3" style="margin: 0 auto;">18</div>
                    </div>
                     <div class="stat-card">
                        <div class="stat-title">3위 번호 (출현 68회)</div>
                        <div class="ball c4" style="margin: 0 auto;">27</div>
                    </div>
                </div>

                <h3 style="font-size:1.05rem; margin-bottom:1rem; margin-top:2rem; color:var(--text-main);">📅 주차별 분석 및 통계 확률</h3>
                <div style="background:#F9FAFB; border-radius:1rem; padding:2rem; text-align:center; color:var(--text-muted); border:1px dashed var(--border);">
                    <div style="font-size:2rem; margin-bottom:1rem;">📉</div>
                    <p style="font-weight:700; margin-bottom:0.5rem;">통계 확률 분석 차트</p>
                    <p style="font-size:0.9rem;">동행복권 API 데이터를 연동하여 주차별 흐름과 당첨 확률 시뮬레이션 그래프가 제공될 예정입니다.</p>
                </div>
            </div>
        </div>
    ''', "html.parser")
    
    # YouTube View
    view_youtube = BeautifulSoup('''
        <div id="view-youtube" class="view-section">
            <div class="card">
                <div class="card-title">▶️ 추천 유튜브 영상</div>
                <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:1.5rem;">
                    <!-- Placeholder videos -->
                    <div style="background:#000; border-radius:1rem; aspect-ratio:16/9; display:flex; align-items:center; justify-content:center; color:#fff; font-size:2rem;">📺</div>
                    <div style="background:#000; border-radius:1rem; aspect-ratio:16/9; display:flex; align-items:center; justify-content:center; color:#fff; font-size:2rem;">📺</div>
                    <div style="background:#000; border-radius:1rem; aspect-ratio:16/9; display:flex; align-items:center; justify-content:center; color:#fff; font-size:2rem;">📺</div>
                </div>
            </div>
        </div>
    ''', "html.parser")
    
    # Invest View
    view_invest = BeautifulSoup('''
        <div id="view-invest" class="view-section">
            <div class="card">
                <div class="card-title">📈 투자 인사이트 (주식/코인)</div>
                <div style="background:#F9FAFB; padding:2rem; border-radius:1rem; text-align:center;">
                    <h3 style="color:var(--text-main); margin-bottom:1rem;">💰 실시간 시황 분석</h3>
                    <p style="color:var(--text-muted); font-size:0.95rem;">코스피, 나스닥, 비트코인 등 주요 투자 자산의 트렌드 지표가 연동됩니다.</p>
                </div>
            </div>
        </div>
    ''', "html.parser")
    
    main_area.append(view_main)
    main_area.append(view_lotto)
    main_area.append(view_youtube)
    main_area.append(view_invest)
    
    layout_container.append(sidebar)
    layout_container.append(main_area)
    
    # Replace old header sibling with layout_container
    # wrap_div was already extracted, so we insert after header
    header = soup.find("header")
    header.insert_after(layout_container)
    
    # Inject JavaScript logic for tabs
    js_script = """
    function switchNavTab(tabId) {
        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        event.currentTarget.classList.add('active');
        
        document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
        document.getElementById('view-' + tabId).classList.add('active');
    }
    """
    script_tag = soup.find_all("script")[-1]
    script_tag.insert(0, bs4.NavigableString(js_script))
    
    # Save back
    with open("lotto_ai.html", "w", encoding="utf-8") as f:
        f.write(str(soup))
    print("Added sidebar layout and tabs successfully.")
else:
    print("Could not find wrap div.")
