"""Embedded Dashboard HTML View for Capital Pádel Club Reception."""

RECEPTION_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Afluenc.IA | YieldPadel - Dashboard de Recepción</title>
  <style>
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    body {
      background-color: #0B0F19;
      color: #F1F5F9;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* Header */
    header {
      background-color: #111827;
      border-bottom: 1px solid #1E293B;
      padding: 0.85rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 60;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 1.25rem;
    }

    .logo-brand {
      font-size: 1.25rem;
      font-weight: 800;
      color: #06B6D4;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      text-decoration: none;
      letter-spacing: -0.02em;
    }

    .logo-badge {
      background: rgba(6, 182, 212, 0.15);
      border: 1px solid rgba(6, 182, 212, 0.3);
      color: #38BDF8;
      font-size: 0.7rem;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      font-weight: 700;
    }

    .venue-tag {
      font-size: 0.8rem;
      color: #94A3B8;
      display: flex;
      align-items: center;
      gap: 0.35rem;
      border-left: 1px solid #1E293B;
      padding-left: 1rem;
    }

    .header-right {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .badge-live {
      background-color: rgba(6, 78, 59, 0.7);
      color: #10B981;
      border: 1px solid rgba(16, 185, 129, 0.4);
      padding: 0.35rem 0.8rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      letter-spacing: 0.05em;
    }

    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background-color: #10B981;
      box-shadow: 0 0 10px #10B981;
      animation: pulse-dot-anim 2s infinite ease-in-out;
    }

    @keyframes pulse-dot-anim {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.2); }
    }

    .btn-icon {
      background: #1E293B;
      color: #CBD5E1;
      border: 1px solid #334155;
      padding: 0.45rem 0.75rem;
      border-radius: 8px;
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 600;
      transition: all 0.2s;
    }

    .btn-icon:hover {
      background: #334155;
      color: white;
    }

    /* Main Container */
    .main-container {
      display: grid;
      grid-template-columns: 1fr 350px;
      gap: 1.25rem;
      max-width: 1750px;
      margin: 1.25rem auto;
      padding: 0 1.25rem;
      width: 100%;
      flex: 1;
    }

    @media (max-width: 1200px) {
      .main-container {
        grid-template-columns: 1fr;
        padding: 0 1rem;
      }
    }

    /* Toolbar */
    .toolbar-container {
      background-color: #111827;
      border: 1px solid #1E293B;
      border-radius: 12px;
      padding: 0.85rem 1.15rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }

    .toolbar-row {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 0.75rem;
    }

    .filter-group {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .filter-label {
      font-size: 0.72rem;
      font-weight: 700;
      color: #94A3B8;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .pill-group {
      display: flex;
      background: #0B0F19;
      border: 1px solid #1E293B;
      border-radius: 8px;
      padding: 0.2rem;
      gap: 0.2rem;
    }

    .filter-pill {
      border: none;
      background: transparent;
      color: #94A3B8;
      padding: 0.32rem 0.75rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }

    .filter-pill.active {
      background: #0284C7;
      color: #FFFFFF;
      box-shadow: 0 2px 8px rgba(2, 132, 199, 0.4);
    }

    .filter-pill:hover:not(.active) {
      color: #FFFFFF;
      background: #1E293B;
    }

    .date-nav-group {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .date-pill {
      border: none;
      background: transparent;
      color: #94A3B8;
      padding: 0.32rem 0.65rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
    }

    .date-pill.active {
      background: #0284C7;
      color: #FFFFFF;
      box-shadow: 0 2px 8px rgba(2, 132, 199, 0.4);
    }

    .date-pill:hover:not(.active) {
      color: #FFFFFF;
      background: #1E293B;
    }

    .date-picker-input {
      background-color: #0B0F19;
      border: 1px solid #1E293B;
      border-radius: 8px;
      color: #F1F5F9;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 0.32rem 0.55rem;
      outline: none;
      cursor: pointer;
      color-scheme: dark;
      transition: border-color 0.2s;
    }

    .date-picker-input:focus {
      border-color: #06B6D4;
    }

    .current-date-badge {
      font-size: 0.78rem;
      color: #38BDF8;
      font-weight: 700;
      background: rgba(6, 182, 212, 0.1);
      border: 1px solid rgba(6, 182, 212, 0.25);
      padding: 0.3rem 0.6rem;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }

    .select-control {
      background-color: #0B0F19;
      border: 1px solid #1E293B;
      border-radius: 8px;
      color: #F1F5F9;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.35rem 0.65rem;
      outline: none;
      cursor: pointer;
      transition: border-color 0.2s;
    }
    .select-control:focus {
      border-color: #38BDF8;
    }

    .btn-seed {
      background: linear-gradient(135deg, #059669 0%, #10B981 100%);
      color: white;
      border: none;
      padding: 0.4rem 0.85rem;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
      transition: all 0.2s;
      white-space: nowrap;
    }
    .btn-seed:hover {
      background: linear-gradient(135deg, #047857 0%, #059669 100%);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
    }

    /* Section Title & Legend */
    .section-title {
      font-size: 1.05rem;
      font-weight: 700;
      color: #FFFFFF;
      margin-bottom: 0.75rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .calendar-legend {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      font-size: 0.7rem;
      color: #94A3B8;
      flex-wrap: wrap;
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }

    .legend-box {
      width: 12px;
      height: 12px;
      border-radius: 3px;
      display: inline-block;
    }
    .legend-box.emerald {
      background: #10B981;
      box-shadow: 0 0 6px rgba(16, 185, 129, 0.6);
    }
    .legend-box.amber {
      background: #F59E0B;
      box-shadow: 0 0 6px rgba(245, 158, 11, 0.6);
    }
    .legend-box.cyan {
      background: #06B6D4;
      box-shadow: 0 0 6px rgba(6, 182, 212, 0.6);
    }
    .legend-box.purple {
      background: #A855F7;
      box-shadow: 0 0 6px rgba(168, 85, 247, 0.6);
    }
    .legend-box.gray {
      background: #475569;
    }

    /* Calendar Wrapper & Matrix Grid */
    .calendar-wrapper {
      background-color: #0F172A;
      border: 1px solid #1E293B;
      border-radius: 12px;
      overflow-x: auto;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
      position: relative;
      max-height: 840px;
      overflow-y: auto;
    }

    .calendar-matrix {
      display: grid;
      position: relative;
      min-width: 1020px;
      background-color: #0B0F19;
    }

    /* Header Columns (Row 1) */
    .time-col-header {
      position: sticky;
      top: 0;
      left: 0;
      z-index: 45;
      background: #111827;
      border-bottom: 2px solid #38BDF8;
      border-right: 1px solid #1E293B;
      padding: 0.75rem 0.5rem;
      text-align: center;
      font-size: 0.72rem;
      font-weight: 800;
      color: #94A3B8;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .court-header {
      position: sticky;
      top: 0;
      z-index: 35;
      background: #111827;
      border-bottom: 2px solid #38BDF8;
      border-right: 1px solid #1E293B;
      padding: 0.65rem 0.5rem;
      text-align: center;
    }

    .court-header-title {
      font-size: 0.85rem;
      font-weight: 800;
      color: #F8FAFC;
      letter-spacing: -0.01em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .court-header-badge {
      font-size: 0.62rem;
      font-weight: 700;
      padding: 0.12rem 0.45rem;
      border-radius: 4px;
      margin-top: 0.2rem;
      display: inline-block;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .badge-central {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.4);
      color: #38BDF8;
    }
    .badge-std {
      background: rgba(148, 163, 184, 0.12);
      border: 1px solid rgba(148, 163, 184, 0.25);
      color: #94A3B8;
    }

    /* Vertical Time Labels (Col 1, Rows 2-N) */
    .time-slot-label {
      position: sticky;
      left: 0;
      z-index: 25;
      background: #0B0F19;
      border-right: 1px solid #1E293B;
      border-bottom: 1px dashed rgba(255, 255, 255, 0.07);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.68rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      color: #64748B;
      font-weight: 600;
      height: 52px;
    }

    /* Background Grid Cells */
    .grid-bg-cell {
      border-right: 1px solid #1E293B;
      border-bottom: 1px dashed rgba(255, 255, 255, 0.05);
      height: 52px;
      box-sizing: border-box;
    }

    /* Slot Card Block inside Calendar Matrix */
    .matrix-slot-card {
      border-radius: 8px;
      padding: 0.5rem 0.65rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      margin: 2px 3px;
      height: calc(100% - 4px);
      position: relative;
      z-index: 15;
      transition: all 0.2s ease;
      overflow: hidden;
      box-sizing: border-box;
      backdrop-filter: blur(4px);
    }

    .matrix-slot-card:hover {
      transform: translateY(-1px);
      z-index: 22;
    }

    /* Card Color Schemes */
    /* 1. Purple: Americano / Torneo */
    .card-theme-purple {
      background: linear-gradient(135deg, rgba(147, 51, 234, 0.25) 0%, rgba(88, 28, 135, 0.42) 100%);
      border: 1px solid #A855F7;
      box-shadow: 0 2px 10px rgba(168, 85, 247, 0.2);
    }
    .card-theme-purple:hover {
      border-color: #C084FC;
      box-shadow: 0 4px 16px rgba(168, 85, 247, 0.35);
    }

    /* 2. Blue / Emerald: Paid / Closed (4/4) */
    .card-theme-emerald {
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.22) 0%, rgba(6, 78, 59, 0.4) 100%);
      border: 1px solid #10B981;
      box-shadow: 0 2px 10px rgba(16, 185, 129, 0.2);
    }
    .card-theme-emerald:hover {
      border-color: #34D399;
      box-shadow: 0 4px 16px rgba(16, 185, 129, 0.35);
    }

    /* 3. Yellow / Amber: Open match (1/4 to 3/4) */
    .card-theme-amber {
      background: linear-gradient(135deg, rgba(245, 158, 11, 0.22) 0%, rgba(180, 83, 9, 0.38) 100%);
      border: 1px solid #F59E0B;
      box-shadow: 0 2px 10px rgba(245, 158, 11, 0.2);
    }
    .card-theme-amber:hover {
      border-color: #FBBF24;
      box-shadow: 0 4px 16px rgba(245, 158, 11, 0.35);
    }

    /* 4. Cyan / Petroleum: Clase / Academia */
    .card-theme-academy {
      background: linear-gradient(135deg, rgba(6, 182, 212, 0.22) 0%, rgba(14, 116, 144, 0.45) 100%);
      border: 1px solid #06B6D4;
      box-shadow: 0 2px 10px rgba(6, 182, 212, 0.25);
    }
    .card-theme-academy:hover {
      border-color: #22D3EE;
      box-shadow: 0 4px 16px rgba(6, 182, 212, 0.4);
    }

    /* 5. Soft Gray: Available / Free */
    .card-theme-gray {
      background: rgba(30, 41, 59, 0.55);
      border: 1px dashed rgba(148, 163, 184, 0.35);
      cursor: pointer;
    }
    .card-theme-gray:hover {
      border-color: #38BDF8;
      background: rgba(30, 41, 59, 0.85);
    }

    /* 6. Dark Red: Blocked / Maintenance */
    .card-theme-blocked {
      background: rgba(239, 68, 68, 0.15);
      border: 1px dashed rgba(239, 68, 68, 0.45);
    }

    /* Pulsing Alert Animation for < 30 min */
    @keyframes urgent-pulse {
      0% {
        box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.8);
        border-color: #EF4444;
      }
      70% {
        box-shadow: 0 0 0 8px rgba(239, 68, 68, 0);
        border-color: #F87171;
      }
      100% {
        box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
        border-color: #EF4444;
      }
    }

    .urgent-alert-box {
      animation: urgent-pulse 1.8s infinite;
    }

    .badge-urgent {
      background: #EF4444;
      color: #FFFFFF;
      font-size: 0.62rem;
      font-weight: 800;
      padding: 0.12rem 0.35rem;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      letter-spacing: 0.02em;
    }

    /* Dynamic Yield Badges */
    .badge-yield-promo {
      background: linear-gradient(135deg, #E11D48 0%, #BE123C 100%);
      color: #FFFFFF;
      font-size: 0.62rem;
      font-weight: 800;
      padding: 0.12rem 0.4rem;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      box-shadow: 0 0 8px rgba(225, 29, 72, 0.5);
      animation: pulse-promo 2s infinite ease-in-out;
    }

    @keyframes pulse-promo {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.85; transform: scale(1.03); }
    }

    .badge-yield-tier {
      font-size: 0.6rem;
      font-weight: 700;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .tier-pico {
      background: rgba(239, 68, 68, 0.18);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #F87171;
    }
    .tier-valle {
      background: rgba(16, 185, 129, 0.18);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34D399;
    }

    /* Inside Card Elements */
    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.25rem;
    }

    .card-time {
      font-size: 0.78rem;
      font-weight: 800;
      color: #FFFFFF;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    .card-dur-badge {
      font-size: 0.62rem;
      font-weight: 700;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.12);
      color: #E2E8F0;
    }

    .card-badges {
      display: flex;
      gap: 0.3rem;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 0.35rem;
    }

    .card-badge-status {
      font-size: 0.62rem;
      font-weight: 700;
      padding: 0.12rem 0.4rem;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }

    .badge-status-closed {
      background: rgba(16, 185, 129, 0.3);
      color: #6EE7B7;
      border: 1px solid rgba(16, 185, 129, 0.5);
    }
    .badge-status-open {
      background: rgba(245, 158, 11, 0.3);
      color: #FCD34D;
      border: 1px solid rgba(245, 158, 11, 0.5);
    }
    .badge-status-academy {
      background: rgba(6, 182, 212, 0.25);
      color: #67E8F9;
      border: 1px solid rgba(6, 182, 212, 0.6);
    }
    .badge-status-tournament {
      background: rgba(168, 85, 247, 0.3);
      color: #E9D5FF;
      border: 1px solid rgba(168, 85, 247, 0.5);
    }
    .badge-status-free {
      background: rgba(148, 163, 184, 0.2);
      color: #CBD5E1;
      border: 1px solid rgba(148, 163, 184, 0.3);
    }
    .badge-status-blocked {
      background: rgba(239, 68, 68, 0.2);
      color: #FCA5A5;
      border: 1px solid rgba(239, 68, 68, 0.4);
    }

    .card-category {
      font-size: 0.62rem;
      font-weight: 700;
      background: rgba(56, 189, 248, 0.15);
      color: #38BDF8;
      border: 1px solid rgba(56, 189, 248, 0.3);
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
    }

    /* Player mini chips inside matrix card */
    .card-players {
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
      margin: 0.25rem 0;
      max-height: 85px;
      overflow-y: auto;
    }

    .card-player-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 4px;
      padding: 0.15rem 0.35rem;
      font-size: 0.68rem;
    }

    .btn-card-drop {
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #FCA5A5;
      font-size: 0.6rem;
      border-radius: 3px;
      padding: 0.05rem 0.3rem;
      cursor: pointer;
      font-weight: 700;
      transition: all 0.15s;
    }
    .btn-card-drop:hover {
      background: #EF4444;
      color: white;
    }

    .card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 0.25rem;
      padding-top: 0.25rem;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
    }

    .card-price {
      font-size: 0.75rem;
      font-weight: 800;
      color: #38BDF8;
    }
    .card-price-sub {
      font-size: 0.6rem;
      color: #94A3B8;
      display: block;
    }

    .btn-card-action {
      background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%);
      color: white;
      border: none;
      padding: 0.22rem 0.55rem;
      border-radius: 5px;
      font-size: 0.68rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-card-action:hover {
      background: linear-gradient(135deg, #0369A1 0%, #075985 100%);
    }

    .btn-card-reserve {
      background: linear-gradient(135deg, #059669 0%, #0D9488 100%);
      color: white;
      border: none;
      padding: 0.22rem 0.55rem;
      border-radius: 5px;
      font-size: 0.68rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-card-reserve:hover {
      background: linear-gradient(135deg, #047857 0%, #0F766E 100%);
    }

    .card-full-badge {
      font-size: 0.65rem;
      font-weight: 700;
      color: #10B981;
    }

    /* Sidebar Components */
    .sidebar {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }

    .sidebar-card {
      background-color: #111827;
      border: 1px solid #1E293B;
      border-radius: 12px;
      padding: 1.15rem;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }

    .sidebar-title {
      font-size: 0.88rem;
      font-weight: 700;
      color: #FFFFFF;
      margin-bottom: 0.75rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .wa-textarea {
      width: 100%;
      height: 120px;
      background-color: #0B0F19;
      border: 1px solid #1E293B;
      border-radius: 8px;
      color: #F1F5F9;
      padding: 0.6rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.72rem;
      resize: vertical;
      outline: none;
      margin-bottom: 0.5rem;
    }

    .wa-textarea:focus {
      border-color: #10B981;
    }

    .btn-wa {
      width: 100%;
      background: linear-gradient(135deg, #059669 0%, #10B981 100%);
      color: white;
      border: none;
      padding: 0.6rem;
      border-radius: 8px;
      font-weight: 700;
      font-size: 0.8rem;
      cursor: pointer;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.2s;
    }

    .btn-wa:hover {
      background: linear-gradient(135deg, #047857 0%, #059669 100%);
    }

    .wa-result-box {
      margin-top: 0.65rem;
      background: #0B0F19;
      border: 1px solid #065F46;
      border-radius: 8px;
      padding: 0.65rem;
      font-size: 0.7rem;
      color: #A7F3D0;
      white-space: pre-wrap;
      font-family: monospace;
      max-height: 180px;
      overflow-y: auto;
    }

    .metric-box {
      background-color: #0B0F19;
      border: 1px solid #1E293B;
      border-radius: 8px;
      padding: 0.75rem;
      margin-bottom: 0.65rem;
    }

    .metric-header {
      display: flex;
      justify-content: space-between;
      font-size: 0.72rem;
      color: #94A3B8;
      margin-bottom: 0.25rem;
    }

    .metric-number {
      font-size: 1.4rem;
      font-weight: 800;
      color: #FFFFFF;
      letter-spacing: -0.02em;
    }

    .active-hold-item {
      background: #0B0F19;
      border: 1px solid #B45309;
      border-radius: 8px;
      padding: 0.65rem;
      margin-bottom: 0.5rem;
    }

    .btn-simulate {
      width: 100%;
      background: #1E293B;
      color: #10B981;
      border: 1px solid #059669;
      padding: 0.35rem;
      border-radius: 6px;
      font-size: 0.7rem;
      font-weight: 700;
      cursor: pointer;
      margin-top: 0.35rem;
      transition: all 0.2s;
    }

    .btn-simulate:hover {
      background: #065F46;
      color: white;
    }

    .event-feed {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      max-height: 220px;
      overflow-y: auto;
    }

    .event-item {
      display: flex;
      align-items: flex-start;
      gap: 0.6rem;
      font-size: 0.72rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid #1E293B;
    }

    .event-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #38BDF8;
      margin-top: 0.3rem;
      flex-shrink: 0;
    }

    /* Modal Backdrop and Box */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 100;
    }

    .modal-backdrop.open {
      display: flex;
    }

    .modal-box {
      background-color: #111827;
      border: 1px solid #1E293B;
      border-radius: 12px;
      width: 90%;
      max-width: 480px;
      padding: 1.5rem;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.25rem;
    }

    .modal-title {
      font-size: 1.05rem;
      font-weight: 700;
      color: #FFFFFF;
    }

    .btn-close {
      background: transparent;
      border: none;
      color: #94A3B8;
      font-size: 1.25rem;
      cursor: pointer;
    }

    .form-group {
      margin-bottom: 1rem;
    }

    .form-label {
      display: block;
      font-size: 0.75rem;
      font-weight: 600;
      color: #CBD5E1;
      margin-bottom: 0.35rem;
    }

    .form-control {
      width: 100%;
      background-color: #0B0F19;
      border: 1px solid #1E293B;
      border-radius: 8px;
      color: #F1F5F9;
      padding: 0.55rem 0.75rem;
      font-size: 0.8rem;
      outline: none;
    }

    .form-control:focus {
      border-color: #38BDF8;
    }

    .btn-submit {
      width: 100%;
      background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%);
      color: white;
      border: none;
      padding: 0.65rem;
      border-radius: 8px;
      font-weight: 700;
      font-size: 0.85rem;
      cursor: pointer;
      margin-top: 0.5rem;
    }

    /* Yield Info Callout inside Modal */
    .yield-callout {
      background: #0B0F19;
      border: 1px solid #1E293B;
      border-radius: 8px;
      padding: 0.85rem;
      margin-bottom: 1rem;
    }
  </style>
</head>
<body>

  <!-- Header -->
  <header>
    <div class="header-left">
      <a href="/dashboard" class="logo-brand">
        <span>⚡ Afluenc.IA</span>
        <span class="logo-badge">YieldPadel</span>
      </a>
      <div class="venue-tag">
        <span>📍 Capital Pádel Club</span>
        <span style="color: #38BDF8; font-weight: 700;">(5 Canchas)</span>
      </div>
    </div>
    <div class="header-right">
      <div class="badge-live">
        <div class="pulse-dot"></div>
        API Live
      </div>
      <button onclick="refreshData()" class="btn-icon" title="Refrescar">
        ↻ Refrescar
      </button>
    </div>
  </header>

  <!-- Main Container -->
  <main class="main-container">

    <!-- Columna Izquierda: Calendario Tipo Matriz de 5 Canchas -->
    <section>
      
      <!-- Toolbar Multi-Día, Zoom y Filtros -->
      <div class="toolbar-container">
        
        <!-- Fila 1: Selector de Fecha y Botón Sembrar 7 Días -->
        <div class="toolbar-row">
          <div class="date-nav-group">
            <span class="filter-label">Fecha:</span>
            <div class="pill-group">
              <button onclick="setRelativeDate(-1)" id="btn-date-yesterday" class="date-pill" title="Ver ayer">◀ Ayer</button>
              <button onclick="setRelativeDate(0)" id="btn-date-today" class="date-pill active" title="Ver hoy">● Hoy</button>
              <button onclick="setRelativeDate(1)" id="btn-date-tomorrow" class="date-pill" title="Ver mañana">Mañana ▶</button>
            </div>
            <input type="date" id="date-picker" onchange="onDateInputChange(this.value)" class="date-picker-input" title="Seleccionar fecha libre" />
            <span id="current-date-label" class="current-date-badge">📅 Hoy</span>
          </div>

          <!-- Botón de Sembrar Turnos 5 Canchas (7 Días) -->
          <button onclick="seedFiveCourts()" id="btn-seed-courts" class="btn-seed" title="Poblar los próximos 7 días para las 5 canchas en bloques de 90 min">
            🌱 + Sembrar Turnos (7 Días / 5 Canchas)
          </button>
        </div>

        <!-- Fila 2: Franjas Horarias, Zoom Cancha y Filtros de Estado -->
        <div class="toolbar-row">
          
          <!-- Filtro Franjas Horarias -->
          <div class="filter-group">
            <span class="filter-label">Franja Horaria:</span>
            <div class="pill-group">
              <button onclick="setTimeFilter('ALL')" id="btn-time-all" class="filter-pill active" title="Ver toda la jornada (06:00 a 24:00)">Todas las horas</button>
              <button onclick="setTimeFilter('MORNING')" id="btn-time-morning" class="filter-pill" title="Ver jornada de la mañana">Mañana (&lt;12pm)</button>
              <button onclick="setTimeFilter('AFTERNOON')" id="btn-time-afternoon" class="filter-pill" title="Ver jornada de la tarde">Tarde (12pm-6pm)</button>
              <button onclick="setTimeFilter('NIGHT')" id="btn-time-night" class="filter-pill" title="Ver jornada nocturna y pico">Noche / Pico (&gt;6pm)</button>
            </div>
          </div>

          <div class="filter-group">
            <span class="filter-label">Zoom Cancha:</span>
            <select id="court-zoom-select" onchange="setCourtZoom(this.value)" class="select-control">
              <option value="ALL">🏟️ Todas las Canchas (1-5)</option>
            </select>
          </div>

          <div class="filter-group">
            <span class="filter-label">Estado:</span>
            <div class="pill-group">
              <button onclick="setStatusFilter('ALL')" id="btn-status-all" class="filter-pill active">Todos</button>
              <button onclick="setStatusFilter('OPEN')" id="btn-status-open" class="filter-pill">Abiertos (1-3)</button>
              <button onclick="setStatusFilter('PAID')" id="btn-status-paid" class="filter-pill">Pagados</button>
            </div>
          </div>

        </div>

      </div>

      <!-- Título de Sección y Leyenda Visual -->
      <div class="section-title">
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <span>📅 Matriz Calendario Operativo (Bloques 90 min)</span>
          <span id="slots-count" style="font-size: 0.75rem; color: #38BDF8; font-weight: 600; background: rgba(56,189,248,0.1); padding: 0.2rem 0.6rem; border-radius: 999px; border: 1px solid rgba(56,189,248,0.25);">Cargando...</span>
        </div>
        
        <div class="calendar-legend">
          <span class="legend-item"><span class="legend-box emerald"></span> Pagado / Cerrado (4/4)</span>
          <span class="legend-item"><span class="legend-box amber"></span> Abierto (1-3)</span>
          <span class="legend-item"><span class="legend-box cyan"></span> 🎾 Clase / Academia</span>
          <span class="legend-item"><span class="legend-box purple"></span> Americano / Torneo</span>
          <span class="legend-item"><span class="legend-box gray"></span> Disponible (Click para Reservar)</span>
        </div>
      </div>

      <!-- Contenedor Matriz Calendario con Franjas Horarias -->
      <div class="calendar-wrapper" id="calendar-wrapper">
        <div id="calendar-matrix" class="calendar-matrix">
          <div style="grid-column: 1/-1; text-align: center; padding: 4rem; color: #64748B;">
            Cargando matriz de 5 canchas desde FastAPI...
          </div>
        </div>
      </div>

    </section>

    <!-- Columna Derecha: Métricas, WhatsApp Parser & Bajas -->
    <aside class="sidebar">

      <!-- Card 1: Parser WhatsApp de Convocatorias -->
      <div class="sidebar-card">
        <div class="sidebar-title">
          <span>📲 Parser WhatsApp</span>
          <span style="color: #10B981; font-size: 0.7rem;">Convocatorias</span>
        </div>
        <p style="font-size: 0.72rem; color: #94A3B8; margin-bottom: 0.4rem;">
          Pega el texto de WhatsApp para parsear jugadores con 🎾 e identidad canónica:
        </p>

        <textarea id="wa-input" class="wa-textarea" placeholder="Pega el mensaje aquí...">HOY 07 SEPTIEMBRE
Categoría: 4ta
⌚6:00pm - 7:30pm
📍Bogotá Pádel Center
💰30.000
🎾Juanda
🎾Edinson
🎾Charlie
🎾 Jose G
PARTIDO CERRADO</textarea>

        <div class="form-group" style="margin-bottom: 0.5rem;">
          <input type="tel" id="wa-sender-phone" placeholder="Teléfono remitente (ej: +573001234567)" class="form-control" style="font-size: 0.75rem; padding: 0.4rem 0.6rem;">
        </div>

        <button onclick="parseWhatsApp()" class="btn-wa">
          🚀 Sincronizar Convocatoria
        </button>

        <div id="wa-result" style="display: none;" class="wa-result-box"></div>
      </div>

      <!-- Card 2: Métricas del Día -->
      <div class="sidebar-card">
        <div class="sidebar-title">
          <span>Métricas Operativas</span>
          <span style="color: #10B981; font-size: 0.75rem;">● En Vivo</span>
        </div>

        <div class="metric-box">
          <div class="metric-header">
            <span>Ingresos del Día</span>
            <span style="color: #38BDF8;">Confirmado</span>
          </div>
          <div id="metric-revenue" class="metric-number">$0</div>
          <div style="font-size: 0.7rem; color: #64748B;">COP (Acumulado día consultado)</div>
        </div>

        <div class="metric-box">
          <div class="metric-header">
            <span>RevPAST Estimado</span>
            <span style="color: #10B981;">Meta: $1.5M</span>
          </div>
          <div style="font-size: 1.3rem; font-weight: 800; color: #FFFFFF;">$1.200.000 COP</div>
          <div class="progress-track" style="background: #1E293B; height: 6px; border-radius: 999px; overflow: hidden; margin-top: 0.4rem;">
            <div class="progress-fill" style="width: 78%; background: #10B981; height: 100%;"></div>
          </div>
        </div>
      </div>

      <!-- Card 3: Holds Activos -->
      <div class="sidebar-card">
        <div class="sidebar-title">
          <span>Holds Activos</span>
          <span style="color: #FBBF24; font-size: 0.7rem;">Bold / Wompi</span>
        </div>

        <div id="active-holds-container">
          <div style="background: #0B0F19; border: 1px solid #1E293B; border-radius: 8px; padding: 0.75rem; text-align: center; font-size: 0.72rem; color: #64748B;">
            No hay holds activos en este momento.
          </div>
        </div>
      </div>

      <!-- Card 4: Eventos Recientes -->
      <div class="sidebar-card">
        <div class="sidebar-title">
          <span>Eventos Recientes</span>
          <span style="color: #94A3B8; font-size: 0.7rem;">Auditoría</span>
        </div>

        <div id="event-feed" class="event-feed">
          <div class="event-item">
            <div class="event-dot"></div>
            <div>
              <div style="font-weight: 600; color: #F1F5F9;">Sistema Inicializado</div>
              <div style="color: #64748B; font-size: 0.68rem;">Capital Pádel Club (Matriz 5 Canchas Activa)</div>
            </div>
          </div>
        </div>
      </div>

    </aside>

  </main>

  <!-- Modal Interactivo para Crear Reserva / Bloqueo con Yield Management -->
  <div id="reserve-block-modal" class="modal-backdrop">
    <div class="modal-box">
      <div class="modal-header">
        <div>
          <div class="modal-title">⚡ Reserva & Yield Management</div>
          <div id="rb-modal-slot-desc" style="font-size: 0.75rem; color: #94A3B8; margin-top: 0.2rem;">Cargando detalles del turno...</div>
        </div>
        <button onclick="closeReserveOrBlockModal()" class="btn-close">✕</button>
      </div>

      <form id="reserve-block-form" onsubmit="handleReserveOrBlockSubmit(event)">
        <input type="hidden" id="rb-slot-id">

        <!-- Callout de Recomendación Yield -->
        <div class="yield-callout" id="rb-yield-box">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
            <span style="font-size: 0.72rem; color: #94A3B8; text-transform: uppercase; font-weight: 700;">Recomendación Yield</span>
            <span id="rb-yield-badge" class="badge-yield-tier tier-valle">🌿 VALLE</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <div id="rb-yield-price-display" style="font-size: 1.25rem; font-weight: 800; color: #38BDF8;">$80.000 COP</div>
            <div id="rb-yield-promo-tag" style="display: none;" class="badge-yield-promo">⚡ LAST-MINUTE PROMO (-25%)</div>
          </div>
          <div id="rb-yield-explanation" style="font-size: 0.68rem; color: #94A3B8; margin-top: 0.35rem; line-height: 1.3;">
            Tarifa dinámica sugerida según ocupación y proximidad horaria.
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Tipo de Turno / Operación</label>
          <select id="rb-slot-type-select" onchange="onSlotTypeChange(this.value)" class="form-control" style="background: #111827; border-color: #38BDF8; font-weight: 700;">
            <option value="MATCH">🎾 Cancha Completa (Reserva Particular)</option>
            <option value="SPLIT_MATCH">👥 Partido Abierto (4 Cupos por Separado)</option>
            <option value="CLASS">🎓 Clase / Academia (Con Profesor)</option>
            <option value="MAINTENANCE">🔧 Bloqueo por Mantenimiento</option>
          </select>
        </div>

        <!-- Campo Dinámico: Profesor de Academia -->
        <div class="form-group" id="rb-instructor-group" style="display: none;">
          <label class="form-label">👨‍🏫 Profesor / Entrenador Asignado</label>
          <input type="text" id="rb-instructor-name" placeholder="Ej: Prof. Marcos Rivas / Valentina Gómez" class="form-control">
          <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.25rem;">
            * Los slots de clase bloquean registros no autorizados por WhatsApp con aviso automático.
          </p>
        </div>

        <div class="form-group" id="rb-client-name-group">
          <label class="form-label">Nombre del Cliente / Titular / Alumno</label>
          <input type="text" id="rb-client-name" placeholder="Ej: Camilo Torres" class="form-control">
        </div>

        <div class="form-group" id="rb-client-phone-group">
          <label class="form-label">Teléfono (WhatsApp)</label>
          <input type="tel" id="rb-client-phone" placeholder="+57 300 123 4567" class="form-control">
        </div>

        <div class="form-group">
          <label class="form-label">Precio Cancha ($ COP)</label>
          <input type="number" id="rb-custom-price" step="1000" min="0" class="form-control" style="font-weight: 700; color: #38BDF8;">
          <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.25rem;">
            Pre-cargado con la sugerencia de Yield. Modificable si aplica cortesía o convenio especial.
          </p>
        </div>

        <button type="submit" id="btn-submit-rb" class="btn-submit">
          Confirmar Reserva / Bloqueo
        </button>
      </form>
    </div>
  </div>

  <!-- Modal Interactivo para Apartar Turno por Cupos (Hold) -->
  <div id="hold-modal" class="modal-backdrop">
    <div class="modal-box">
      <div class="modal-header">
        <div class="modal-title" id="modal-title">Apartar Turno</div>
        <button onclick="closeModal()" class="btn-close">✕</button>
      </div>

      <form id="hold-form" onsubmit="handleHoldSubmit(event)">
        <input type="hidden" id="modal-slot-id">
        <input type="hidden" id="modal-slot-mode">

        <div class="form-group">
          <label class="form-label">Condición de Pago / Tipo de Cliente</label>
          <select id="modal-tier" onchange="calculateModalPrice()" class="form-control" style="background: #111827; border-color: #38BDF8; font-weight: 600;">
            <option value="STANDARD">Estándar (Pago Pasarela Bold - Hold 15 min)</option>
            <option value="VIP_PAY_ON_SITE">VIP (Pago en Recepción - Sin Expiración)</option>
            <option value="MEMBER">Membresía / Socio (Costo $0 - Exento)</option>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">Nombre del Cliente</label>
          <input type="text" id="modal-name" required placeholder="Ej: Juan David Rivas" class="form-control">
        </div>

        <div class="form-group">
          <label class="form-label">Teléfono (WhatsApp)</label>
          <input type="tel" id="modal-phone" required placeholder="+57 300 123 4567" class="form-control">
        </div>

        <div class="form-group" id="modal-spots-wrapper">
          <label class="form-label">Cupos a Apartar</label>
          <select id="modal-spots-select" onchange="calculateModalPrice()" class="form-control"></select>
        </div>

        <div style="background: #0B0F19; border: 1px solid #1E293B; border-radius: 8px; padding: 0.85rem; margin-bottom: 1.25rem;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.35rem; font-size: 0.75rem; color: #94A3B8;">
            <span>Total a Pagar:</span>
            <span id="modal-ttl-info" style="color: #FBBF24; font-weight: 700;">⏳ TTL 15:00 min</span>
          </div>
          <div id="modal-total-display" style="font-size: 1.3rem; font-weight: 800; color: #38BDF8;">
            $0 COP
          </div>
        </div>

        <button type="submit" id="btn-submit-hold" class="btn-submit">
          Confirmar Reserva
        </button>
      </form>
    </div>
  </div>

  <!-- Modal Interactivo para Baja / Cancelación -->
  <div id="drop-modal" class="modal-backdrop">
    <div class="modal-box">
      <div class="modal-header">
        <div class="modal-title">Solicitar Baja de Jugador</div>
        <button onclick="closeDropModal()" class="btn-close">✕</button>
      </div>

      <form id="drop-form" onsubmit="handleDropSubmit(event)">
        <input type="hidden" id="drop-slot-id">

        <div class="form-group">
          <label class="form-label">Jugador a dar de baja:</label>
          <input type="text" id="drop-player-display" readonly class="form-control" style="color: #94A3B8; background: #0B0F19;">
        </div>

        <div class="form-group">
          <label class="form-label">Teléfono del Solicitante (WhatsApp):</label>
          <input type="tel" id="drop-phone-input" required class="form-control" placeholder="+57 300 123 4567">
          <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.35rem;">
            * Por seguridad y control anti-suplantación, solo el titular o su host pueden liberar el cupo.
          </p>
        </div>

        <button type="submit" id="btn-submit-drop" class="btn-submit" style="background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%);">
          Confirmar Baja
        </button>
      </form>
    </div>
  </div>

  <!-- Scripts -->
  <script>
    const API_BASE = '';
    let allSlots = [];
    let allCourts = [];
    let activeHoldsMap = {};
    let selectedSlot = null;
    let currentStatusFilter = 'ALL';  // ALL, OPEN, PAID
    let currentTimeFilter = 'ALL';    // ALL, MORNING, AFTERNOON, NIGHT
    let selectedCourtZoom = 'ALL';    // ALL or court UUID/ID

    function getLocalDateString(d) {
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    }

    let selectedDate = getLocalDateString(new Date());

    function setDate(dateStr) {
      if (!dateStr) return;
      selectedDate = dateStr;
      const picker = document.getElementById('date-picker');
      if (picker) picker.value = dateStr;
      updateDateUI();
      refreshData();
    }

    function setRelativeDate(offsetDays) {
      const d = new Date();
      d.setDate(d.getDate() + offsetDays);
      setDate(getLocalDateString(d));
    }

    function onDateInputChange(val) {
      if (val) {
        setDate(val);
      }
    }

    function formatDateDisplay(dateStr) {
      const parts = dateStr.split('-');
      const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
      const todayStr = getLocalDateString(new Date());

      const yesterday = new Date(); yesterday.setDate(yesterday.getDate() - 1);
      const yesterdayStr = getLocalDateString(yesterday);

      const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
      const tomorrowStr = getLocalDateString(tomorrow);

      let label = '';
      if (dateStr === todayStr) label = 'Hoy • ';
      else if (dateStr === yesterdayStr) label = 'Ayer • ';
      else if (dateStr === tomorrowStr) label = 'Mañana • ';

      const formatted = d.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' });
      return label + formatted;
    }

    function updateDateUI() {
      const todayStr = getLocalDateString(new Date());
      const yesterday = new Date(); yesterday.setDate(yesterday.getDate() - 1);
      const yesterdayStr = getLocalDateString(yesterday);
      const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
      const tomorrowStr = getLocalDateString(tomorrow);

      const btnYesterday = document.getElementById('btn-date-yesterday');
      const btnToday = document.getElementById('btn-date-today');
      const btnTomorrow = document.getElementById('btn-date-tomorrow');
      const label = document.getElementById('current-date-label');

      if (btnYesterday) btnYesterday.className = 'date-pill' + (selectedDate === yesterdayStr ? ' active' : '');
      if (btnToday) btnToday.className = 'date-pill' + (selectedDate === todayStr ? ' active' : '');
      if (btnTomorrow) btnTomorrow.className = 'date-pill' + (selectedDate === tomorrowStr ? ' active' : '');
      if (label) label.textContent = '📅 ' + formatDateDisplay(selectedDate);
    }

    function formatCOP(num) {
      return '$' + Number(num || 0).toLocaleString('es-CO') + ' COP';
    }

    function addEvent(title, subtitle, type = 'info') {
      const feed = document.getElementById('event-feed');
      if (!feed) return;
      const timeStr = new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      
      const div = document.createElement('div');
      div.className = 'event-item';
      div.innerHTML = `
        <div class="event-dot" style="${type === 'green' ? 'background: #10B981;' : (type === 'amber' ? 'background: #FBBF24;' : (type === 'red' ? 'background: #EF4444;' : (type === 'cyan' ? 'background: #06B6D4;' : '')))}"></div>
        <div style="flex: 1;">
          <div style="font-weight: 600; color: #F1F5F9;">${title}</div>
          <div style="color: #64748B; font-size: 0.68rem;">${subtitle} • ${timeStr}</div>
        </div>
      `;
      feed.insertBefore(div, feed.firstChild);
      while (feed.children.length > 15) feed.removeChild(feed.lastChild);
    }

    function setStatusFilter(status) {
      currentStatusFilter = status;
      document.getElementById('btn-status-all').className = 'filter-pill' + (status === 'ALL' ? ' active' : '');
      document.getElementById('btn-status-open').className = 'filter-pill' + (status === 'OPEN' ? ' active' : '');
      document.getElementById('btn-status-paid').className = 'filter-pill' + (status === 'PAID' ? ' active' : '');
      renderCalendarMatrix();
    }

    function setTimeFilter(timeFilter) {
      currentTimeFilter = timeFilter;
      document.getElementById('btn-time-all').className = 'filter-pill' + (timeFilter === 'ALL' ? ' active' : '');
      document.getElementById('btn-time-morning').className = 'filter-pill' + (timeFilter === 'MORNING' ? ' active' : '');
      document.getElementById('btn-time-afternoon').className = 'filter-pill' + (timeFilter === 'AFTERNOON' ? ' active' : '');
      document.getElementById('btn-time-night').className = 'filter-pill' + (timeFilter === 'NIGHT' ? ' active' : '');
      renderCalendarMatrix();
    }

    function setCourtZoom(courtVal) {
      selectedCourtZoom = courtVal;
      renderCalendarMatrix();
    }

    async function fetchCourts() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/slots/courts`);
        if (res.ok) {
          allCourts = await res.json();
          // Update Zoom Dropdown
          const select = document.getElementById('court-zoom-select');
          if (select) {
            const currentVal = select.value;
            select.innerHTML = '<option value="ALL">🏟️ Todas las Canchas (1-5)</option>';
            allCourts.forEach((c, idx) => {
              const opt = document.createElement('option');
              opt.value = c.id;
              opt.textContent = `📍 ${c.name}`;
              select.appendChild(opt);
            });
            if (currentVal && (currentVal === 'ALL' || allCourts.some(c => String(c.id) === String(currentVal)))) {
              select.value = currentVal;
            }
          }
        }
      } catch (err) {
        console.error('Error fetching courts:', err);
      }
    }

    async function refreshData() {
      try {
        await fetch(`${API_BASE}/api/v1/holds/check-expirations`, { method: 'POST' }).catch(() => {});
        if (allCourts.length === 0) {
          await fetchCourts();
        }
        const dateQuery = selectedDate ? `&date=${selectedDate}` : '';
        const res = await fetch(`${API_BASE}/api/v1/slots/?only_available=false${dateQuery}`);
        if (!res.ok) throw new Error('Error al conectar con la API');
        allSlots = await res.json();
        renderCalendarMatrix();
        updateMetrics();
      } catch (err) {
        console.error('Error fetching data:', err);
      }
    }

    function renderCalendarMatrix() {
      const container = document.getElementById('calendar-matrix');
      const countEl = document.getElementById('slots-count');
      if (!container) return;

      // Filter courts according to zoom
      let displayedCourts = allCourts;
      if (selectedCourtZoom !== 'ALL') {
        displayedCourts = allCourts.filter(c => String(c.id) === String(selectedCourtZoom));
        if (displayedCourts.length === 0) displayedCourts = allCourts;
      }

      // Configure Grid Template Columns
      if (displayedCourts.length > 1) {
        container.style.gridTemplateColumns = `75px repeat(${displayedCourts.length}, minmax(190px, 1fr))`;
        container.style.minWidth = `${75 + displayedCourts.length * 190}px`;
      } else {
        container.style.gridTemplateColumns = `75px 1fr`;
        container.style.minWidth = `100%`;
      }

      // Filter slots according to Status
      let filteredSlots = allSlots;
      if (currentStatusFilter === 'OPEN') {
        filteredSlots = allSlots.filter(s => s.mode === 'SPLIT_MATCH' && s.booked_spots > 0 && (s.booked_spots + s.held_spots) < s.capacity);
      } else if (currentStatusFilter === 'PAID') {
        filteredSlots = allSlots.filter(s => s.status === 'FULLY_BOOKED' || (s.booked_spots + s.held_spots) >= s.capacity);
      }

      // Determine operational time range based on Time Filter
      // ALL: 06:00 to 24:00 (360 to 1440 min, 36 half-hours)
      // MORNING: 06:00 to 12:00 (360 to 720 min, 12 half-hours)
      // AFTERNOON: 12:00 to 18:00 (720 to 1080 min, 12 half-hours)
      // NIGHT: 18:00 to 24:00 (1080 to 1440 min, 12 half-hours)
      let START_MINUTES = 360;
      let END_MINUTES = 1440;

      if (currentTimeFilter === 'MORNING') {
        START_MINUTES = 360;
        END_MINUTES = 720;
      } else if (currentTimeFilter === 'AFTERNOON') {
        START_MINUTES = 720;
        END_MINUTES = 1080;
      } else if (currentTimeFilter === 'NIGHT') {
        START_MINUTES = 1080;
        END_MINUTES = 1440;
      }

      const TOTAL_SLOTS = Math.round((END_MINUTES - START_MINUTES) / 30);

      // Filter slots by current time window
      const visibleSlots = filteredSlots.filter(s => {
        const [sh, sm] = s.start_time.split(':').map(Number);
        const slotStartMin = sh * 60 + sm;
        return slotStartMin >= START_MINUTES && slotStartMin < END_MINUTES;
      });

      if (countEl) {
        countEl.textContent = `${visibleSlots.length} turno${visibleSlots.length === 1 ? '' : 's'} (${formatDateDisplay(selectedDate)})`;
      }

      let html = '';

      // 1. Sticky Header Row (Row 1)
      html += `<div class="time-col-header" style="grid-row: 1; grid-column: 1;">HORA</div>`;
      displayedCourts.forEach((c, idx) => {
        const isCentral = c.name.toLowerCase().includes('central') || idx === 0;
        html += `
          <div class="court-header" style="grid-row: 1; grid-column: ${idx + 2};">
            <div class="court-header-title" title="${c.name}">${c.name}</div>
            <span class="court-header-badge ${isCentral ? 'badge-central' : 'badge-std'}">
              ${isCentral ? '⭐ Central' : 'Pista ' + (c.court_number || (idx + 1))}
            </span>
          </div>
        `;
      });

      // 2. Background Grid: Time labels (Col 1) and Empty Court cells (Col 2..N)
      for (let i = 0; i < TOTAL_SLOTS; i++) {
        const rowNum = i + 2;
        const curMin = START_MINUTES + i * 30;
        const hh = String(Math.floor(curMin / 60)).padStart(2, '0');
        const mm = String(curMin % 60).padStart(2, '0');
        const timeLabel = `${hh}:${mm}`;

        html += `<div class="time-slot-label" style="grid-row: ${rowNum}; grid-column: 1;">${timeLabel}</div>`;

        displayedCourts.forEach((c, cIdx) => {
          html += `<div class="grid-bg-cell" style="grid-row: ${rowNum}; grid-column: ${cIdx + 2};"></div>`;
        });
      }

      // 3. Render Slot Cards as Grid Blocks
      const todayStr = getLocalDateString(new Date());
      const isToday = (selectedDate === todayStr);
      const now = new Date();
      const currentNowMin = now.getHours() * 60 + now.getMinutes();

      visibleSlots.forEach(slot => {
        // Find court column
        const courtIdx = displayedCourts.findIndex(c => String(c.id) === String(slot.court_id));
        if (courtIdx === -1) return;
        const colNum = courtIdx + 2;

        // Parse times
        const [sh, sm] = slot.start_time.split(':').map(Number);
        const [eh, em] = slot.end_time.split(':').map(Number);
        const slotStartMin = sh * 60 + sm;
        const slotEndMin = (eh === 0 && em === 0) ? 1440 : (eh * 60 + em);

        // Determine grid row and span
        if (slotStartMin < START_MINUTES || slotStartMin >= END_MINUTES) return;
        const rowStart = Math.floor((slotStartMin - START_MINUTES) / 30) + 2;
        const durationMin = Math.max(30, slotEndMin - slotStartMin);
        const rowSpan = Math.max(1, Math.round(durationMin / 30));

        // Color coding & Categories
        const catLower = (slot.category || '').toLowerCase();
        const isTournament = catLower.includes('americano') || catLower.includes('torneo');
        const isClass = (slot.slot_type === 'CLASS' || slot.slot_type === 'ACADEMY');
        const isBlocked = slot.status === 'BLOCKED' || slot.slot_type === 'MAINTENANCE';
        const isFull = !isBlocked && !isClass && (slot.status === 'FULLY_BOOKED' || (slot.booked_spots + slot.held_spots) >= slot.capacity);
        const isOpenMatch = !isBlocked && !isClass && slot.mode === 'SPLIT_MATCH' && slot.booked_spots > 0 && !isFull;
        const isAvailable = !isTournament && !isClass && !isBlocked && !isFull && !isOpenMatch;

        let themeClass = 'card-theme-gray';
        let statusBadge = `<span class="card-badge-status badge-status-free">⚪ LIBRE</span>`;

        if (isBlocked) {
          themeClass = 'card-theme-blocked';
          statusBadge = `<span class="card-badge-status badge-status-blocked">🔧 BLOQUEO</span>`;
        } else if (isClass) {
          themeClass = 'card-theme-academy';
          statusBadge = `<span class="card-badge-status badge-status-academy">🎾 CLASE / ACADEMIA</span>`;
        } else if (isTournament) {
          themeClass = 'card-theme-purple';
          statusBadge = `<span class="card-badge-status badge-status-tournament">🏆 ${slot.category}</span>`;
        } else if (isFull) {
          themeClass = 'card-theme-emerald';
          statusBadge = `<span class="card-badge-status badge-status-closed">✓ CERRADO (4/4)</span>`;
        } else if (isOpenMatch) {
          themeClass = 'card-theme-amber';
          statusBadge = `<span class="card-badge-status badge-status-open">⚡ ABIERTO (${slot.booked_spots}/${slot.capacity})</span>`;
        }

        // Urgency check (< 30 min) for open matches
        const minutesUntilStart = slotStartMin - currentNowMin;
        const isUrgent = isToday && isOpenMatch && (minutesUntilStart > 0 && minutesUntilStart <= 30);
        if (isUrgent) {
          themeClass += ' urgent-alert-box';
        }

        // Yield promo and pricing tier tags
        let yieldBadgesHtml = '';
        if (slot.is_promo) {
          yieldBadgesHtml += `<span class="badge-yield-promo" title="Descuento Yield Last-Minute">⚡ PROMO -25%</span>`;
        }
        if (slot.pricing_tier === 'PICO') {
          yieldBadgesHtml += `<span class="badge-yield-tier tier-pico">🔥 PICO</span>`;
        } else if (slot.pricing_tier === 'VALLE') {
          yieldBadgesHtml += `<span class="badge-yield-tier tier-valle">🌿 VALLE</span>`;
        }

        const durLabel = durationMin === 60 ? '1h' : (durationMin === 90 ? '1.5h' : (durationMin === 120 ? '2h' : (durationMin / 60).toFixed(1) + 'h'));
        const priceStr = formatCOP(slot.mode === 'SPLIT_MATCH' ? slot.price_per_spot : slot.total_price);
        const priceSub = slot.mode === 'SPLIT_MATCH' ? 'por cupo' : 'cancha total';

        // Class Coach & Instructor Display
        let classInfoHtml = '';
        if (isClass) {
          const profName = slot.instructor_name || 'Prof. Asignado';
          classInfoHtml = `
            <div style="font-size: 0.7rem; color: #67E8F9; font-weight: 700; margin: 0.2rem 0; display: flex; align-items: center; gap: 0.25rem;">
              <span>👨‍🏫 Prof: ${profName}</span>
            </div>
            <div style="font-size: 0.62rem; color: #94A3B8; margin-bottom: 0.25rem;">
              <span style="background: rgba(15,23,42,0.7); padding: 0.1rem 0.35rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);">🚫 WhatsApp Inhabilitado</span>
            </div>
          `;
        }

        // Participants list
        const participants = slot.participants || [];
        let playersHtml = '';
        if (participants.length > 0 && rowSpan >= 3 && !isClass && !isBlocked) {
          const pRows = participants.map(p => `
            <div class="card-player-item">
              <span title="Tel: ${p.phone || ''} • ${p.client_tier}">🎾 ${p.display_name}</span>
              <button onclick="event.stopPropagation(); openDropModal(${slot.id}, '${p.display_name}', '${p.phone}')" class="btn-card-drop" title="Solicitar baja">✕</button>
            </div>
          `).join('');
          playersHtml = `<div class="card-players">${pRows}</div>`;
        }

        // Action Button
        let actionBtn = '';
        if (isBlocked) {
          actionBtn = `<span style="font-size: 0.65rem; color: #FCA5A5; font-weight: 700;">🔧 En Mantenimiento</span>`;
        } else if (isClass) {
          actionBtn = `<span style="font-size: 0.65rem; color: #38BDF8; font-weight: 700;">✓ Academia</span>`;
        } else if (isFull) {
          actionBtn = `<span class="card-full-badge">✓ Completo</span>`;
        } else if (isOpenMatch) {
          actionBtn = `<button onclick="event.stopPropagation(); openHoldModal(${slot.id})" class="btn-card-action">Apartar</button>`;
        } else {
          // Available slot
          actionBtn = `<button onclick="event.stopPropagation(); openReserveOrBlockModal(${slot.id})" class="btn-card-reserve">⚡ Reservar</button>`;
        }

        const cardOnClick = isAvailable ? `onclick="openReserveOrBlockModal(${slot.id})"` : '';

        html += `
          <div class="matrix-slot-card ${themeClass}" style="grid-row: ${rowStart} / span ${rowSpan}; grid-column: ${colNum};" ${cardOnClick}>
            <div>
              <div class="card-top">
                <span class="card-time">${slot.start_time.slice(0, 5)} - ${slot.end_time.slice(0, 5)}</span>
                <span class="card-dur-badge">${durLabel}</span>
              </div>

              <div class="card-badges">
                ${statusBadge}
                ${yieldBadgesHtml}
                ${isUrgent ? '<span class="badge-urgent">⚠️ &lt; 30 min</span>' : ''}
                ${slot.category && !isTournament && !isClass ? `<span class="card-category">Cat. ${slot.category}</span>` : ''}
              </div>

              ${classInfoHtml}
              ${playersHtml}
            </div>

            <div class="card-footer">
              <div>
                <span class="card-price">${priceStr}</span>
                <span class="card-price-sub">${priceSub}</span>
              </div>
              ${actionBtn}
            </div>
          </div>
        `;
      });

      container.innerHTML = html;
    }

    async function seedFiveCourts() {
      const btn = document.getElementById('btn-seed-courts');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Sembrando 7 días...';
      }
      try {
        const query = selectedDate ? `?date=${selectedDate}` : '';
        const res = await fetch(`${API_BASE}/api/v1/slots/seed${query}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          addEvent('Turnos Sembrados (7 Días)', `${data.slots_created || 0} slots creados para 5 canchas`, 'green');
          await refreshData();
        } else {
          alert(data.detail || 'Error al sembrar turnos');
        }
      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = '🌱 + Sembrar Turnos (7 Días / 5 Canchas)';
        }
      }
    }

    // Modal de Reserva / Bloqueo con Yield Management
    async function openReserveOrBlockModal(slotId) {
      const slot = allSlots.find(s => s.id === slotId);
      if (!slot) return;

      document.getElementById('rb-slot-id').value = slot.id;
      document.getElementById('rb-modal-slot-desc').textContent = `${slot.court_name || 'Cancha'} • ${slot.date} • ${slot.start_time.slice(0,5)} - ${slot.end_time.slice(0,5)}`;
      document.getElementById('rb-client-name').value = '';
      document.getElementById('rb-client-phone').value = '+57 ';
      document.getElementById('rb-instructor-name').value = '';
      document.getElementById('rb-slot-type-select').value = 'MATCH';
      onSlotTypeChange('MATCH');

      // Pre-cargar precio recomendado de Yield
      try {
        const res = await fetch(`${API_BASE}/api/v1/slots/${slotId}/yield-recommendation`);
        if (res.ok) {
          const yd = await res.json();
          document.getElementById('rb-custom-price').value = yd.recommended_price || slot.total_price;
          document.getElementById('rb-yield-price-display').textContent = formatCOP(yd.recommended_price);
          
          const tierBadge = document.getElementById('rb-yield-badge');
          if (yd.pricing_tier === 'PICO') {
            tierBadge.className = 'badge-yield-tier tier-pico';
            tierBadge.textContent = '🔥 HORARIO PICO';
          } else {
            tierBadge.className = 'badge-yield-tier tier-valle';
            tierBadge.textContent = '🌿 HORARIO VALLE';
          }

          const promoTag = document.getElementById('rb-yield-promo-tag');
          if (yd.is_promo) {
            promoTag.style.display = 'inline-flex';
            promoTag.textContent = `⚡ PROMO -${yd.promo_discount_percent}% (Ahorro ${formatCOP(yd.savings)})`;
          } else {
            promoTag.style.display = 'none';
          }

          document.getElementById('rb-yield-explanation').textContent = yd.explanation || 'Tarifa calculada por motor dinámico de ocupación.';
        } else {
          document.getElementById('rb-custom-price').value = slot.total_price;
        }
      } catch (e) {
        document.getElementById('rb-custom-price').value = slot.total_price;
      }

      document.getElementById('reserve-block-modal').classList.add('open');
    }

    function closeReserveOrBlockModal() {
      document.getElementById('reserve-block-modal').classList.remove('open');
    }

    function onSlotTypeChange(stype) {
      const instructorGroup = document.getElementById('rb-instructor-group');
      const clientNameGroup = document.getElementById('rb-client-name-group');
      const clientPhoneGroup = document.getElementById('rb-client-phone-group');

      if (stype === 'CLASS') {
        instructorGroup.style.display = 'block';
        clientNameGroup.style.display = 'block';
        clientPhoneGroup.style.display = 'block';
      } else if (stype === 'MAINTENANCE') {
        instructorGroup.style.display = 'none';
        clientNameGroup.style.display = 'none';
        clientPhoneGroup.style.display = 'none';
      } else {
        instructorGroup.style.display = 'none';
        clientNameGroup.style.display = 'block';
        clientPhoneGroup.style.display = 'block';
      }
    }

    async function handleReserveOrBlockSubmit(e) {
      e.preventDefault();
      const slotId = Number(document.getElementById('rb-slot-id').value);
      const stype = document.getElementById('rb-slot-type-select').value;
      const instructor = document.getElementById('rb-instructor-name').value.trim();
      const clientName = document.getElementById('rb-client-name').value.trim();
      const clientPhone = document.getElementById('rb-client-phone').value.trim();
      const customPrice = parseFloat(document.getElementById('rb-custom-price').value) || null;

      const btn = document.getElementById('btn-submit-rb');
      btn.disabled = true;
      btn.textContent = 'Procesando...';

      try {
        const payload = {
          slot_type: stype === 'SPLIT_MATCH' ? 'MATCH' : stype,
          mode: stype === 'SPLIT_MATCH' ? 'SPLIT_MATCH' : 'FULL_COURT',
          instructor_name: stype === 'CLASS' ? instructor : null,
          client_name: clientName || null,
          client_phone: clientPhone || null,
          custom_price: customPrice
        };

        const res = await fetch(`${API_BASE}/api/v1/slots/${slotId}/reserve-or-block`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al procesar reserva');

        if (stype === 'CLASS') {
          addEvent(`Clase Agendada: ${instructor || 'Profesor'}`, `Alumno: ${clientName || 'Asignado'} • ${formatCOP(data.total_price)}`, 'cyan');
        } else if (stype === 'MAINTENANCE') {
          addEvent(`Pista Bloqueada`, `Mantenimiento preventivo en turno #${slotId}`, 'red');
        } else {
          addEvent(`Reserva Confirmada`, `${clientName || 'Cancha Completa'} • ${formatCOP(data.total_price)}`, 'green');
        }

        closeReserveOrBlockModal();
        await refreshData();
      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Confirmar Reserva / Bloqueo';
      }
    }

    // Modal de Hold
    function openHoldModal(slotId) {
      const slot = allSlots.find(s => s.id === slotId);
      if (!slot) return;
      selectedSlot = slot;

      document.getElementById('modal-slot-id').value = slot.id;
      document.getElementById('modal-slot-mode').value = slot.mode;
      document.getElementById('modal-title').textContent = slot.mode === 'FULL_COURT' 
        ? 'Apartar Cancha Completa' 
        : 'Apartar Cupo / Partido Abierto';

      const wrapper = document.getElementById('modal-spots-wrapper');
      const select = document.getElementById('modal-spots-select');

      if (slot.mode === 'FULL_COURT') {
        wrapper.style.display = 'none';
        select.value = "4";
      } else {
        wrapper.style.display = 'block';
        select.innerHTML = '';
        for (let i = 1; i <= slot.available_spots; i++) {
          const opt = document.createElement('option');
          opt.value = i;
          opt.textContent = `${i} Cupo${i > 1 ? 's' : ''}`;
          select.appendChild(opt);
        }
      }

      calculateModalPrice();
      document.getElementById('hold-modal').classList.add('open');
    }

    function calculateModalPrice() {
      if (!selectedSlot) return;
      const tier = document.getElementById('modal-tier').value;
      const display = document.getElementById('modal-total-display');
      const ttlInfo = document.getElementById('modal-ttl-info');

      if (tier === 'MEMBER') {
        display.textContent = '$0 COP';
        display.style.color = '#10B981';
        ttlInfo.textContent = '✓ Socio Exento';
        ttlInfo.style.color = '#10B981';
        return;
      }

      if (tier === 'VIP_PAY_ON_SITE') {
        ttlInfo.textContent = '📍 Cobro en Recepción';
        ttlInfo.style.color = '#38BDF8';
      } else {
        ttlInfo.textContent = '⏳ TTL 15:00 min';
        ttlInfo.style.color = '#FBBF24';
      }

      display.style.color = '#38BDF8';
      if (selectedSlot.mode === 'FULL_COURT') {
        display.textContent = formatCOP(selectedSlot.total_price);
      } else {
        const spots = Number(document.getElementById('modal-spots-select').value) || 1;
        const total = spots * Number(selectedSlot.price_per_spot);
        display.textContent = formatCOP(total);
      }
    }

    function closeModal() {
      document.getElementById('hold-modal').classList.remove('open');
    }

    async function handleHoldSubmit(e) {
      e.preventDefault();
      const slotId = Number(document.getElementById('modal-slot-id').value);
      const mode = document.getElementById('modal-slot-mode').value;
      const name = document.getElementById('modal-name').value.trim();
      const phone = document.getElementById('modal-phone').value.trim();
      const tier = document.getElementById('modal-tier').value;
      const spots = mode === 'FULL_COURT' ? 4 : Number(document.getElementById('modal-spots-select').value);

      const btn = document.getElementById('btn-submit-hold');
      btn.disabled = true;
      btn.textContent = 'Guardando...';

      try {
        const res = await fetch(`${API_BASE}/api/v1/holds/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            slot_id: slotId,
            customer_name: name,
            customer_phone: phone,
            spots_held: spots,
            client_tier: tier
          })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al apartar');

        if (tier === 'MEMBER') {
          addEvent(`Membresía: ${data.customer_name}`, `Ref ${data.payment_reference} ($0)`, 'green');
        } else if (tier === 'VIP_PAY_ON_SITE') {
          addEvent(`Reserva VIP: ${data.customer_name}`, `Ref ${data.payment_reference} (Paga en recepción)`, 'green');
        } else {
          addEvent(`Hold Creado: ${data.customer_name}`, `Ref ${data.payment_reference} (15m Bold)`, 'amber');
          registerHoldTimer(data);
        }

        closeModal();
        await refreshData();
      } catch (err) {
        alert(err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Confirmar Reserva';
      }
    }

    // Modal de Baja / Drop Player
    function openDropModal(slotId, playerName, knownPhone) {
      document.getElementById('drop-slot-id').value = slotId;
      document.getElementById('drop-player-display').value = playerName;
      document.getElementById('drop-phone-input').value = (knownPhone && !knownPhone.includes('-WA-') && !knownPhone.includes('unknown')) ? knownPhone : '+57 ';
      document.getElementById('drop-modal').classList.add('open');
    }

    function closeDropModal() {
      document.getElementById('drop-modal').classList.remove('open');
    }

    async function handleDropSubmit(e) {
      e.preventDefault();
      const slotId = Number(document.getElementById('drop-slot-id').value);
      const phone = document.getElementById('drop-phone-input').value.trim();
      const playerName = document.getElementById('drop-player-display').value;

      const btn = document.getElementById('btn-submit-drop');
      btn.disabled = true;
      btn.textContent = 'Validando baja...';

      try {
        const res = await fetch(`${API_BASE}/api/v1/slots/drop-player`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            slot_id: slotId,
            sender_phone: phone
          })
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(`[${res.status}] ${data.detail || 'Error en baja'}`);
        }

        addEvent('Cupo Liberado (Baja)', `${playerName} (${data.freed_phone}) canceló su cupo. Slot reabierto.`, 'green');
        closeDropModal();
        await refreshData();
      } catch (err) {
        alert("Error de seguridad: " + err.message);
        addEvent('Baja Rechazada (403)', `${phone} no es titular de ${playerName}`, 'red');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Confirmar Baja';
      }
    }

    // Parser WhatsApp
    async function parseWhatsApp() {
      const raw = document.getElementById('wa-input').value;
      const senderPhone = document.getElementById('wa-sender-phone').value.trim();
      const resultBox = document.getElementById('wa-result');

      try {
        const payload = { raw_text: raw };
        if (senderPhone) payload.sender_phone = senderPhone;

        const res = await fetch(`${API_BASE}/api/v1/slots/parse-open-match`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al procesar convocatoria');

        resultBox.style.display = 'block';
        resultBox.textContent = data.whatsapp_reply;

        addEvent('Convocatoria WhatsApp Sincronizada', `${data.players.length}/4 jugadores • ${data.is_closed ? 'CERRADO' : 'ABIERTO'}`, 'green');
        await refreshData();
      } catch (err) {
        resultBox.style.display = 'block';
        resultBox.textContent = 'Error: ' + err.message;
      }
    }

    function registerHoldTimer(hold) {
      const expMs = new Date(hold.expires_at).getTime();
      activeHoldsMap[hold.payment_reference] = {
        ...hold,
        expMs: expMs
      };
      renderActiveHolds();
    }

    function renderActiveHolds() {
      const container = document.getElementById('active-holds-container');
      const holds = Object.values(activeHoldsMap);

      if (holds.length === 0) {
        container.innerHTML = `
          <div style="background: #0B0F19; border: 1px solid #1E293B; border-radius: 8px; padding: 0.75rem; text-align: center; font-size: 0.72rem; color: #64748B;">
            No hay holds activos en este momento.
          </div>
        `;
        return;
      }

      container.innerHTML = holds.map(h => {
        const diff = Math.max(0, Math.floor((h.expMs - Date.now()) / 1000));
        const mm = String(Math.floor(diff / 60)).padStart(2, '0');
        const ss = String(diff % 60).padStart(2, '0');

        return `
          <div class="active-hold-item">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.75rem; font-weight: 800; color: #38BDF8;">${h.payment_reference}</span>
              <span style="background: rgba(120, 53, 15, 0.4); color: #FBBF24; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.68rem; font-weight: 700;">⏳ ${mm}:${ss}</span>
            </div>
            <div style="font-size: 0.72rem; color: #CBD5E1; margin: 0.35rem 0;">
              ${h.customer_name} (${h.spots_held} cupo${h.spots_held > 1 ? 's' : ''}) • <strong>${formatCOP(h.amount_to_pay)}</strong>
            </div>
            <button onclick="simulateWebhookPayment('${h.payment_reference}')" class="btn-simulate">
              ✓ Simular Pago Webhook
            </button>
          </div>
        `;
      }).join('');
    }

    async function simulateWebhookPayment(ref) {
      try {
        const res = await fetch(`${API_BASE}/api/v1/webhooks/payment-mock`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            payment_reference: ref,
            status: 'APPROVED',
            transaction_id: 'TX-' + Math.random().toString(36).substring(2, 9).toUpperCase()
          })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al procesar');

        delete activeHoldsMap[ref];
        renderActiveHolds();
        addEvent('Pago Confirmado Bold', `Ref ${ref} • ${formatCOP(data.amount_paid)}`, 'green');
        await refreshData();
      } catch (err) {
        alert(err.message);
      }
    }

    function updateMetrics() {
      let total = 0;
      allSlots.forEach(s => {
        const p = Number(s.price_per_spot) || 0;
        total += (s.booked_spots * p);
      });
      document.getElementById('metric-revenue').textContent = formatCOP(total).replace(' COP', '');
    }

    setInterval(() => {
      const now = Date.now();
      let changed = false;
      Object.keys(activeHoldsMap).forEach(ref => {
        if (activeHoldsMap[ref].expMs <= now) {
          delete activeHoldsMap[ref];
          addEvent('Hold Expirado', `Ref ${ref} liberado`, 'amber');
          changed = true;
        }
      });
      if (Object.keys(activeHoldsMap).length > 0 || changed) renderActiveHolds();
    }, 1000);

    // Initial setup
    const picker = document.getElementById('date-picker');
    if (picker) picker.value = selectedDate;
    updateDateUI();
    fetchCourts().then(() => {
      refreshData();
    });
    setInterval(refreshData, 6000);
  </script>
</body>
</html>
"""

DASHBOARD_HTML = RECEPTION_DASHBOARD_HTML
