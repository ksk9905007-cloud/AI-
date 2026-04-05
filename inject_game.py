import bs4
from bs4 import BeautifulSoup

file_path = 'lotto_ai.html'
with open(file_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

if not soup.find(id='view-minigame'):
    # 1. Sidebar Nav
    side_nav = soup.find(class_='side-nav')
    if side_nav:
        item = BeautifulSoup('<a class="nav-item" onclick="switchNavTab(\'minigame\')"><span class="nav-icon">🎮</span> 미니게임</a>', 'html.parser')
        side_nav.append(item)

    # 2. View Section
    content_area = soup.find('main', class_='content-area')
    if content_area:
        game_view = BeautifulSoup('''
        <div id="view-minigame" class="view-section">
            <div class="card">
                <div class="card-title">🎮 스트레스 해소 미니게임 존 (10선)</div>
                <p class="modal-desc" style="margin-bottom:1.5rem;">잠시 쉬어가며 스트레스를 날려버리세요! 원하는 게임을 선택하세요.</p>
                
                <div id="gameSelector" style="display:grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap:1rem; margin-bottom:2rem;">
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('bubble')"><span style="font-size:2rem; margin-bottom:0.5rem;">🫧</span> 버블 팝업</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('fidget')"><span style="font-size:2rem; margin-bottom:0.5rem;">🌀</span> 피젯 스피너</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('clicker')"><span style="font-size:2rem; margin-bottom:0.5rem;">🖱️</span> 무한 클릭</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('rain')"><span style="font-size:2rem; margin-bottom:0.5rem;">🌧️</span> 힐링 빗소리</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('color')"><span style="font-size:2rem; margin-bottom:0.5rem;">🎨</span> 컬러 테라피</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('box')"><span style="font-size:2rem; margin-bottom:0.5rem;">📦</span> 박스 부수기</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('neon')"><span style="font-size:2rem; margin-bottom:0.5rem;">💡</span> 네온 페인팅</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('ball')"><span style="font-size:2rem; margin-bottom:0.5rem;">🎾</span> 공 튕기기</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('fire')"><span style="font-size:2rem; margin-bottom:0.5rem;">🔥</span> 장작불 멍</button>
                    <button class="btn btn-outline" style="flex-direction:column; padding:1.2rem; height:auto;" onclick="loadGame('breath')"><span style="font-size:2rem; margin-bottom:0.5rem;">🧘</span> 호흡 가이드</button>
                </div>
                
                <div id="gameContainer" style="background:#f8fafc; border: 2px dashed var(--border); border-radius:1.5rem; min-height:450px; display:flex; align-items:center; justify-content:center; position:relative; overflow:hidden; touch-action:none;">
                    <div style="color:var(--text-muted); text-align:center; font-weight:600;">상단 메뉴에서 게임을 선택해주세요.</div>
                </div>
            </div>
        </div>
        ''', 'html.parser')
        content_area.append(game_view)

    # 3. Game Logic script
    script_str = '''
    function loadGame(gameId) {
        const container = document.getElementById('gameContainer');
        container.innerHTML = '';
        container.style.background = '#f8fafc';
        
        switch(gameId) {
            case 'bubble':
                container.innerHTML = '<div style="padding:1rem; text-align:center; position:absolute; top:0; z-index:10; font-weight:700; color:var(--primary);">버블을 마구 터뜨리세요! 🫧</div>';
                for(let i=0; i<35; i++) createBubble();
                break;
            case 'fidget':
                container.innerHTML = '<div style="text-align:center;"><div id="spinner" style="font-size:10rem; transition: transform 0.15s ease-out; cursor:pointer; user-select:none;" onclick="spin()">🌀</div><p style="margin-top:2rem; font-weight:700;">스피너를 클릭해서 쌩쌩 돌리세요!</p></div>';
                window.spinDeg = 0;
                break;
            case 'clicker':
                window.clickCount = 0;
                container.innerHTML = `<div style="text-align:center;"><div id="cCount" style="font-size:5rem; font-weight:900; color:var(--primary); margin-bottom:1rem;">0</div><button class="btn btn-primary" style="font-size:2rem; padding:2rem 4rem; border-radius:3rem; box-shadow:0 10px 30px rgba(79,70,229,0.3);" onclick="hitClicker()">CLICK!</button><p style="margin-top:2rem; color:var(--text-muted);">무념무상 클릭하며 잡념을 날리세요</p></div>`;
                break;
            case 'breath':
                container.innerHTML = '<div style="text-align:center;"><div id="breathBall" style="width:100px; height:100px; background:var(--primary-light); border-radius:50%; margin: 0 auto; transition: all 4s ease-in-out; opacity:0.6; box-shadow:0 0 50px var(--primary-light);"></div><h2 id="bText" style="margin-top:3rem; color:var(--primary); font-weight:800;">숨을 들이마시세요...</h2></div>';
                runBreath();
                break;
            case 'color':
                container.innerHTML = '<div style="display:grid; grid-template-columns: repeat(5, 1fr); gap:12px; padding:25px; width:100%; height:100%; box-sizing:border-box;">' + 
                    Array(25).fill(0).map(() => `<div style="background:hsl(${Math.random()*360}, 70%, 60%); border-radius:15px; cursor:pointer; transition:all 0.3s;" onclick="this.style.background=\\\'hsl(\\\'+Math.random()*360+\\\', 70%, 50%)\\\'"></div>`).join('') + '</div>';
                break;
            case 'box':
                container.innerHTML = '<div style="padding:1rem; position:absolute; top:0; font-weight:700; color:var(--danger);">박스를 조각조각 부수세요! 📦</div>';
                for(let i=0; i<18; i++) createBox();
                break;
            case 'fire':
                container.style.background = '#0f172a';
                container.innerHTML = '<div style="text-align:center;"><span style="font-size:7rem; display:block; animation: flicker 1s infinite alternate;">🔥</span><h2 style="color:#f97316; margin-top:2rem;">장작 타는 소리에 집중하며 불멍...</h2><p style="color:#64748b; margin-top:1rem;">마음의 평화를 찾으세요.</p></div>';
                break;
            case 'rain':
                container.style.background = '#1e293b';
                container.innerHTML = '<div style="text-align:center;"><span style="font-size:6rem; display:block; filter: drop-shadow(0 0 20px #3b82f6);">🌧️</span><h2 style="color:#60a5fa; margin-top:2rem;">토닥토닥 빗소리 힐링...</h2></div>';
                break;
            default:
                container.innerHTML = '<div style="text-align:center; padding:2rem;"><span style="font-size:4rem;">🚧</span><h2 style="margin-top:1.5rem;">곧 공개될 게임입니다!</h2></div>';
        }
    }
    function createBubble() {
        const container = document.getElementById(\'gameContainer\');
        if(!container || !container.innerHTML.includes(\'버블\')) return;
        const b = document.createElement(\'div\');
        const size = Math.random() * 40 + 30;
        b.className = \'picker-ball\';
        b.style.cssText = `position:absolute; width:${size}px; height:${size}px; background:rgba(147,197,253,0.3); border:2px solid #fff; left:${Math.random()*90}%; top:${Math.random()*85}%; transition:all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);`;
        b.onclick = () => { 
            b.style.transform = \'scale(2.5)\'; 
            b.style.opacity = \'0\'; 
            b.innerHTML = \'✨\';
            setTimeout(() => { b.remove(); createBubble(); }, 250); 
        };
        container.appendChild(b);
    }
    function spin() { 
        window.spinDeg += 120; 
        document.getElementById(\'spinner\').style.transform = `rotate(${window.spinDeg}deg)`; 
    }
    function hitClicker() { 
        window.clickCount++; 
        document.getElementById(\'cCount\').innerText = window.clickCount; 
        const btn = event.currentTarget;
        btn.style.transform = \'scale(0.95)\';
        setTimeout(() => btn.style.transform = \'scale(1)\', 50);
    }
    function createBox() {
        const container = document.getElementById(\'gameContainer\');
        if(!container || !container.innerHTML.includes(\'박스\')) return;
        const b = document.createElement(\'div\');
        b.style.cssText = `position:absolute; width:70px; height:70px; background:#d97706; border-radius:12px; left:${Math.random()*85}%; top:${Math.random()*80}%; cursor:pointer; display:flex; align-items:center; justify-content:center; font-size:1.8rem; box-shadow:0 4px 0 #92400e; transition:all 0.1s;`;
        b.innerText = \'📦\';
        b.onclick = () => { 
            b.innerText = \'💥\'; 
            b.style.background = \'#ef4444\'; 
            b.style.transform = \'scale(1.2)\';
            setTimeout(() => { b.remove(); createBox(); }, 300); 
        };
        container.appendChild(b);
    }
    function runBreath() {
        const ball = document.getElementById(\'breathBall\');
        const text = document.getElementById(\'bText\');
        if(!ball) return;
        ball.style.transform = \'scale(2.6)\';
        ball.style.opacity = \'0.9\';
        text.innerText = \'숨을 깊게 들이마시세요...\';
        setTimeout(() => {
            if(!ball) return;
            ball.style.transform = \'scale(1)\';
            ball.style.opacity = \'0.4\';
            text.innerText = \'천천히 내뱉으세요...\';
            setTimeout(runBreath, 4000);
        }, 4000);
    }
    '''
    new_script = soup.new_tag('script')
    new_script.string = script_str
    soup.body.append(new_script)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))
