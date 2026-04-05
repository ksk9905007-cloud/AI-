import re

with open("lotto_ai.html", "r", encoding="utf-8") as f:
    text = f.read()

start_marker = "<style>"
end_marker = "</style>"
start_idx = text.find(start_marker)
end_idx = text.find(end_marker) + len(end_marker)

new_styles = """<style>
        :root {
            --primary: #4F46E5;
            --primary-light: #818CF8;
            --secondary: #10B981;
            --success: #059669;
            --danger: #EF4444;
            --bg: #F3F4F6;
            --card: #FFFFFF;
            --border: #E5E7EB;
            --text-main: #111827;
            --text-muted: #6B7280;
            
            /* Lotto Ball Colors */
            --b1: #FBBF24; --b1t: #78350F;
            --b2: #60A5FA; --b2t: #1E3A8A;
            --b3: #F87171; --b3t: #7F1D1D;
            --b4: #9CA3AF; --b4t: #1F2937;
            --b5: #34D399; --b5t: #064E3B;
        }
        
        * { margin:0; padding:0; box-sizing:border-box; }
        body { 
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif; 
            background: linear-gradient(135deg, #F3F4F6 0%, #E5E7EB 100%); 
            color: var(--text-main); 
            min-height: 100vh; 
            -webkit-font-smoothing: antialiased;
        }

        /* ─ Header ─ */
        header {
            background: rgba(255, 255, 255, 0.85); 
            backdrop-filter: blur(12px);
            border-bottom: 1px solid rgba(255,255,255,0.3);
            padding: 1.2rem 2rem; 
            display: flex; justify-content: space-between; align-items: center;
            position: sticky; top: 0; z-index: 200; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.03);
        }
        .logo { font-size: 1.5rem; font-weight: 900; color: var(--primary); display: flex; align-items: center; gap: 8px; letter-spacing: -0.5px;}
        .logo em { color: #F59E0B; font-style: normal; }
        #headerStatus { 
            font-size: 0.85rem; font-weight: 700; padding: 0.5rem 1rem; 
            border-radius: 50px; background: #FEF2F2; color: var(--danger);
            border: 1px solid #FECACA; transition: all 0.3s ease;
        }

        /* ─ Layout ─ */
        .wrap { 
            max-width: 1200px; margin: 2.5rem auto; padding: 0 1.5rem; 
            display: grid; grid-template-columns: 1fr 400px; gap: 2rem; 
        }
        @media(max-width:960px){ .wrap{grid-template-columns: 1fr;} }

        /* ─ Card ─ */
        .card { 
            background: var(--card); border: 1px solid rgba(255,255,255,0.5); 
            border-radius: 1.5rem; padding: 1.8rem; margin-bottom: 1.5rem; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02); 
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .card:hover { box-shadow: 0 15px 35px rgba(0,0,0,0.06), 0 2px 5px rgba(0,0,0,0.03); }
        .card-title { 
            font-size: 1.15rem; font-weight: 800; margin-bottom: 1.5rem; 
            display: flex; align-items: center; gap: 10px; color: var(--text-main); 
        }

        /* ─ Lotto Balls ─ */
        .ball-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .ball { 
            width: 46px; height: 46px; border-radius: 50%; 
            display: flex; align-items: center; justify-content: center; 
            font-weight: 800; font-size: 1.1rem; 
            box-shadow: inset 0 -3px 0 rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.1); 
            text-shadow: 0 1px 1px rgba(255,255,255,0.5);
        }
        .ball.sm { width: 34px; height: 34px; font-size: 0.85rem; box-shadow: inset 0 -2px 0 rgba(0,0,0,0.1), 0 2px 4px rgba(0,0,0,0.08); }
        .ball.lg { width: 56px; height: 56px; font-size: 1.3rem; }
        .plus { color: var(--text-muted); font-size: 1.5rem; font-weight: 800; margin: 0 4px;}
        .c1{background: var(--b1); color: var(--b1t);}
        .c2{background: var(--b2); color: var(--b2t);}
        .c3{background: var(--b3); color: var(--b3t);}
        .c4{background: var(--b4); color: var(--b4t);}
        .c5{background: var(--b5); color: var(--b5t);}

        /* ─ Latest Result ─ */
        .draw-meta { font-size: 0.95rem; color: var(--text-muted); margin-bottom: 1.2rem; font-weight: 500; }
        .draw-no-badge { 
            font-weight: 800; color: var(--primary); font-size: 1.1rem; 
            background: #EEF2FF; padding: 0.3rem 0.8rem; border-radius: 8px; margin-right: 8px;
        }
        .amount-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.5rem; }
        .amount-item { 
            background: #F8FAFC; border-radius: 1rem; padding: 1.2rem; 
            border: 1px solid #F1F5F9; text-align: center;
        }
        .amount-label { font-size: 0.85rem; color: var(--text-muted); font-weight: 600; margin-bottom: 0.4rem; }
        .amount-val { font-size: 1.2rem; font-weight: 800; color: var(--primary); }

        /* ─ Prediction Panel ─ */
        .predict-panel {
            background: linear-gradient(135deg, #1E1B4B 0%, #312E81 100%);
            color: #FFFFFF; border-radius: 1.5rem; padding: 2.2rem; margin-bottom: 1.5rem;
            box-shadow: 0 20px 40px rgba(30,27,75,0.15);
            position: relative; overflow: hidden;
        }
        .predict-panel::after {
            content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.05) 0%, transparent 60%);
            pointer-events: none;
        }
        .predict-panel .card-title { color: #FFFFFF; font-size: 1.25rem; }
        .predict-display { display: flex; gap: 12px; justify-content: center; min-height: 64px; margin: 2rem 0; flex-wrap: wrap; }
        .p-ball {
            width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
            font-weight: 800; font-size: 1.4rem; background: rgba(255,255,255,0.1);
            border: 2px solid rgba(255,255,255,0.2); transform: scale(0.8); opacity: 0;
            transition: all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
            box-shadow: inset 0 2px 4px rgba(255,255,255,0.1);
        }
        .p-ball.on { transform: scale(1); opacity: 1; border-color: #FCD34D; background: #FCD34D; color: #78350F; box-shadow: 0 10px 20px rgba(0,0,0,0.2); }

        /* ─ Buttons ─ */
        .btn { 
            padding: 0.9rem 1.4rem; border-radius: 1rem; font-weight: 700; cursor: pointer; 
            border: none; font-family: inherit; display: flex; align-items: center; justify-content: center; 
            gap: 8px; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); font-size: 1rem; letter-spacing: -0.02em;
        }
        .btn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .btn-primary { background: var(--primary); color: #fff; box-shadow: 0 4px 14px rgba(79, 70, 229, 0.3); }
        .btn-primary:hover { background: #4338CA; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(79, 70, 229, 0.4); }
        .btn-outline { background: #fff; border: 2px solid var(--border); color: var(--text-main); }
        .btn-outline:hover { background: #F9FAFB; border-color: #D1D5DB; }
        .btn-gold { background: linear-gradient(135deg, #F59E0B, #D97706); color: #fff; box-shadow: 0 4px 15px rgba(245,158,11,0.3); }
        .btn-gold:hover { filter: brightness(1.1); transform: translateY(-2px); box-shadow: 0 6px 20px rgba(245,158,11,0.4); }
        .btn-success { background: var(--secondary); color: #fff; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.3); }
        .btn-success:hover { background: var(--success); transform: translateY(-2px); box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4); }
        .btn-danger { background: var(--danger); color: #fff; }
        .btn-sm { padding: 0.6rem 1rem; font-size: 0.85rem; border-radius: 0.75rem; }
        .btn-full { width: 100%; margin-top: 1rem; padding: 1.1rem; font-size: 1.05rem; }
        button:disabled { opacity: 0.6; cursor: not-allowed; transform: none !important; box-shadow: none !important; }

        /* ─ Purchase History ─ */
        .history-wrap { max-height: 420px; overflow-y: auto; padding-right: 5px; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 10px; }
        
        .history-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.9rem; }
        .history-table th { 
            background: #F8FAFC; padding: 1rem; font-weight: 700; text-align: left; 
            color: var(--text-muted); border-bottom: 2px solid #E2E8F0; 
        }
        .history-table th:first-child { border-top-left-radius: 12px; }
        .history-table th:last-child { border-top-right-radius: 12px; }
        .history-table td { padding: 1rem; border-bottom: 1px solid #F1F5F9; vertical-align: middle; color: var(--text-main); }
        .history-table tr:hover td { background: #F8FAFC; }
        .history-item td:first-child { font-weight: 700; color: var(--primary); }
        
        .win-badge { padding: 0.35rem 0.75rem; border-radius: 20px; font-size: 0.8rem; font-weight: 800; white-space: nowrap; display: inline-block; text-align: center;}
        .win-1 { background: #FEF3C7; color: #92400E; box-shadow: inset 0 0 0 1px #FDE68A; }
        .win-2 { background: #E0E7FF; color: #3730A3; box-shadow: inset 0 0 0 1px #C7D2FE; }
        .win-3 { background: #D1FAE5; color: #065F46; box-shadow: inset 0 0 0 1px #A7F3D0; }
        .win-4 { background: #FCE7F3; color: #9D174D; box-shadow: inset 0 0 0 1px #FBCFE8; }
        .win-5 { background: #EDE9FE; color: #5B21B6; box-shadow: inset 0 0 0 1px #DDD6FE; }
        .win-0 { background: #F1F5F9; color: #64748B; box-shadow: inset 0 0 0 1px #E2E8F0; }
        .win-none { background: #FFFFFF; color: #94A3B8; border: 1px dashed #CBD5E1; }
        
        .check-btn { 
            padding: 0.4rem 0.8rem; border-radius: 0.5rem; background: var(--primary-light); 
            color: #fff; border: none; cursor: pointer; font-size: 0.8rem; font-weight: 700; transition: background 0.2s;
        }
        .check-btn:hover:not(:disabled) { background: var(--primary); }

        /* ─ Toast ─ */
        #toast { 
            position: fixed; top: 24px; left: 50%; transform: translate(-50%, -20px); 
            background: rgba(17, 24, 39, 0.9); backdrop-filter: blur(8px); color: #fff; 
            padding: 0.85rem 1.8rem; border-radius: 50px; font-size: 0.95rem; font-weight: 600;
            z-index: 9999; opacity: 0; transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1); 
            pointer-events: none; box-shadow: 0 10px 30px rgba(0,0,0,0.15); 
        }
        #toast.show { opacity: 1; transform: translate(-50%, 0); }
        
        .btn-link { 
            text-decoration: none; color: var(--primary); font-size: 0.9rem; font-weight: 700;
            display: flex; align-items: center; gap: 6px; padding: 0.6rem 1.2rem;
            background: #EEF2FF; border-radius: 50px; border: 1px solid #E0E7FF;
            transition: all 0.3s ease;
        }
        .btn-link:hover { background: var(--primary); color: #fff; transform: translateY(-2px); box-shadow: 0 6px 15px rgba(79, 70, 229, 0.25); }
        .btn-link svg { width: 16px; height: 16px; }

        /* ─ Modal ─ */
        .modal { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(6px); display: none; align-items: center; justify-content: center; z-index: 1000; opacity: 0; transition: opacity 0.3s; }
        .modal.open { display: flex; opacity: 1; }
        .modal-box { 
            background: #fff; padding: 2.5rem; border-radius: 1.5rem; width: 92%; max-width: 440px; 
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25); transform: scale(0.95); transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); 
        }
        .modal.open .modal-box { transform: scale(1); }
        .modal-title { font-size: 1.3rem; font-weight: 800; margin-bottom: 0.5rem; color: var(--text-main); letter-spacing: -0.02em;}
        .modal-desc { font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1.5rem; line-height: 1.6; }
        
        .input-wrap { margin-bottom: 1.2rem; }
        .input-wrap label { display: block; font-size: 0.8rem; font-weight: 700; color: var(--text-muted); margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .input-wrap input { 
            width: 100%; padding: 0.9rem 1.2rem; border: 2px solid #E5E7EB; border-radius: 1rem; 
            font-family: inherit; font-size: 1.05rem; outline: none; transition: all 0.2s; background: #F9FAFB;
        }
        .input-wrap input:focus { border-color: var(--primary); background: #fff; box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.1); }
        #modalStatus { font-size: 0.85rem; margin: 1rem 0; min-height: 1.2rem; color: var(--text-muted); font-weight: 500;}

        /* ─ 구매 성공 팝업 ─ */
        .success-modal .modal-box {
            text-align: center; background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
            border: 2px solid #34D399; box-shadow: 0 20px 40px rgba(52, 211, 153, 0.2);
        }
        .success-icon { font-size: 4.5rem; margin-bottom: 0.8rem; animation: bounce 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        @keyframes bounce { 0%,100%{transform:scale(1)} 50%{transform:scale(1.15)} }
        .success-title { font-size: 1.6rem; font-weight: 900; color: #065F46; margin-bottom: 0.5rem; letter-spacing: -0.02em; }
        .success-draw { font-size: 1rem; color: #047857; margin-bottom: 1.2rem; font-weight: 600;}
        .success-numbers { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin: 1.5rem 0; }
        .success-time { font-size: 0.85rem; color: #10B981; margin-bottom: 1.5rem; font-weight: 500;}

        /* ─ Search ─ */
        .search-wrap { margin-bottom: 1.2rem; position: relative; }
        .search-wrap input { 
            width: 100%; padding: 0.8rem 1.2rem 0.8rem 2.8rem; border: 2px solid #E5E7EB; 
            border-radius: 1rem; font-size: 0.95rem; outline: none; transition: all 0.2s; background: #F9FAFB;
        }
        .search-wrap input:focus { border-color: var(--primary); background: #fff; box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.05); }
        .search-wrap svg { position: absolute; left: 1rem; top: 50%; transform: translateY(-50%); width: 18px; height: 18px; color: #9CA3AF; }
        
        /* ─ QR Scanner ─ */
        .qr-overlay { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(10px); z-index: 2000; display: none; flex-direction: column; align-items: center; justify-content: center; color: #fff; opacity: 0; transition: opacity 0.3s; }
        .qr-overlay.open { display: flex; opacity: 1; }
        .qr-video-wrap { width: 90%; max-width: 360px; aspect-ratio: 1; position: relative; border-radius: 1.5rem; overflow: hidden; border: 4px solid rgba(255,255,255,0.2); box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
        #qrVideo { width: 100%; height: 100%; object-fit: cover; }
        .qr-scanner-line { position: absolute; top: 0; left: 0; width: 100%; height: 3px; background: #34D399; box-shadow: 0 0 20px #34D399, 0 0 10px #34D399; animation: scan 2.5s cubic-bezier(0.4, 0, 0.2, 1) infinite; }
        @keyframes scan { 0% { top: 0 } 50% { top: 100% } 100% { top: 0 } }
        /* ─ Utilities ─ */
        .flex-between { display: flex; justify-content: space-between; align-items: center; }
</style>"""

if start_idx != -1 and text.find(end_marker) != -1:
    text = text[:start_idx] + new_styles + text[end_idx:]
    with open("lotto_ai.html", "w", encoding="utf-8") as f:
        f.write(text)
    print("Styles updated successfully.")
else:
    print("Could not find style tags in HTML.")
