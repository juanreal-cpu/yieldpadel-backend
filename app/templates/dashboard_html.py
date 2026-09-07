"""Embedded dashboard HTML template module."""

RECEPTION_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Afluenc.IA | YieldPadel - Panel Operativo SaaS</title>
  <!-- Leaflet CSS & JS for Geospatial Radar Map -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <style>
    /* Leaflet Custom Pins */
    .radar-pin-target {
      display: flex;
      align-items: center;
      justify-content: center;
      background: #0F172A;
      color: #F59E0B;
      border: 2px solid #F59E0B;
      border-radius: 50%;
      box-shadow: 0 0 14px rgba(245, 158, 11, 0.7), 0 2px 6px rgba(0,0,0,0.3);
      font-size: 16px;
      font-weight: 800;
      cursor: pointer;
      animation: pulse 2.5s infinite;
    }
    .radar-pin-competitor {
      display: flex;
      align-items: center;
      justify-content: center;
      background: #0284C7;
      color: #FFFFFF;
      border: 2px solid #FFFFFF;
      border-radius: 12px;
      padding: 2px 7px;
      font-size: 11px;
      font-weight: 800;
      box-shadow: 0 2px 6px rgba(0,0,0,0.25);
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.2s;
    }
    .radar-pin-competitor:hover {
      background: #0369A1;
      transform: scale(1.08);
    }
    .leaflet-popup-content-wrapper {
      border-radius: 10px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.15);
      font-family: inherit;
    }
    .leaflet-popup-content {
      margin: 10px 12px;
      line-height: 1.4;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    body {
      background-color: #F8FAFC;
      color: #0F172A;
      min-height: 100vh;
      display: flex;
      overflow-x: hidden;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
      100% { opacity: 1; transform: scale(1); }
    }

    /* ======================================================== */
    /* 1. ESTRUCTURA GENERAL SAAS: SIDEBAR FIJO & MAIN AREA     */
    /* ======================================================== */
    .saas-layout {
      display: flex;
      width: 100%;
      min-height: 100vh;
    }

    /* SIDEBAR FIJO A LA IZQUIERDA (w-64 = 260px) */
    .saas-sidebar {
      width: 260px;
      min-width: 260px;
      height: 100vh;
      position: fixed;
      top: 0;
      left: 0;
      background-color: #FFFFFF;
      border-right: 1px solid #E2E8F0;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      z-index: 50;
      box-shadow: 2px 0 8px rgba(0, 0, 0, 0.03);
    }

    .sidebar-brand {
      padding: 1.25rem 1.25rem 1rem 1.25rem;
      border-bottom: 1px solid #F1F5F9;
    }

    .brand-title {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      text-decoration: none;
    }

    .brand-icon {
      font-size: 1.35rem;
      line-height: 1;
    }

    .brand-name {
      font-size: 1.15rem;
      font-weight: 800;
      color: #0F172A;
      letter-spacing: -0.02em;
    }

    .brand-badge {
      background: rgba(2, 132, 199, 0.1);
      border: 1px solid rgba(2, 132, 199, 0.3);
      color: #0284C7;
      font-size: 0.65rem;
      padding: 0.12rem 0.4rem;
      border-radius: 4px;
      font-weight: 800;
      letter-spacing: 0.03em;
    }

    .brand-sub {
      font-size: 0.72rem;
      color: #64748B;
      font-weight: 600;
      margin-top: 0.35rem;
      display: flex;
      align-items: center;
      gap: 0.3rem;
    }

    /* Menú Vertical de Navegación */
    .sidebar-nav {
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
      padding: 1rem 0.75rem;
      flex: 1;
      overflow-y: auto;
    }

    .sidebar-nav-item {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.65rem 0.85rem;
      border-radius: 8px;
      border: none;
      background: transparent;
      color: #475569;
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
      text-align: left;
      transition: all 0.18s ease;
      width: 100%;
    }

    .sidebar-nav-item:hover {
      background-color: #F1F5F9;
      color: #0F172A;
    }

    .sidebar-nav-item.active {
      background-color: #F1F5F9;
      color: #0F172A;
      font-weight: 700;
      box-shadow: inset 3px 0 0 #0284C7;
    }

    .sidebar-nav-item .nav-icon {
      font-size: 0.95rem;
      width: 20px;
      height: 20px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
      flex-shrink: 0;
    }

    /* Pie del Sidebar */
    .sidebar-footer {
      padding: 1rem 1.25rem;
      border-top: 1px solid #F1F5F9;
      background-color: #FAFAFA;
      display: flex;
      flex-direction: column;
      gap: 0.65rem;
    }

    .api-live-badge {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      font-size: 0.72rem;
      font-weight: 700;
      color: #059669;
    }

    .live-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background-color: #10B981;
      animation: pulse 2s infinite;
    }

    .btn-refresh-sidebar {
      background: #FFFFFF;
      border: 1px solid #CBD5E1;
      color: #334155;
      padding: 0.4rem 0.75rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      transition: all 0.2s;
    }

    .btn-refresh-sidebar:hover {
      background: #F1F5F9;
      color: #0F172A;
      border-color: #94A3B8;
    }

    /* MAIN CONTENT AREA (Offset by sidebar w-64) */
    .saas-main-content {
      margin-left: 260px;
      width: calc(100% - 260px);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background-color: #F8FAFC;
    }

    /* ======================================================== */
    /* 2. BANNER EJECUTIVO SUPERIOR (HEADER OSCURO DE CONTRASTE) */
    /* ======================================================== */
    .executive-banner {
      background-color: #0F172A;
      color: #F8FAFC;
      padding: 1.25rem 2rem;
      border-bottom: 1px solid #1E293B;
      box-shadow: 0 4px 14px rgba(15, 23, 42, 0.15);
      position: sticky;
      top: 0;
      z-index: 45;
    }

    .banner-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    .banner-title-area {
      display: flex;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }

    .banner-main-title {
      font-size: 1.25rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: #FFFFFF;
    }

    .banner-date-badge {
      background: rgba(30, 41, 59, 0.85);
      border: 1px solid #334155;
      color: #38BDF8;
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.2rem 0.65rem;
      border-radius: 999px;
    }

    .banner-venue-badge {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.72rem;
      color: #94A3B8;
      font-weight: 600;
    }

    .badge-status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #38BDF8;
    }

    /* Fila de 5 Tarjetas KPIs Compactas */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(170px, 1fr));
      gap: 0.85rem;
    }

    @media (max-width: 1400px) {
      .kpi-grid {
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      }
    }

    .kpi-card {
      background-color: rgba(30, 41, 59, 0.9);
      border: 1px solid rgba(51, 65, 85, 0.6);
      border-radius: 10px;
      padding: 0.85rem 1rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
      backdrop-filter: blur(8px);
    }

    .kpi-label {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.68rem;
      font-weight: 600;
      color: #94A3B8;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.35rem;
    }

    .kpi-tag {
      font-size: 0.6rem;
      font-weight: 700;
      padding: 0.12rem 0.4rem;
      border-radius: 4px;
      letter-spacing: 0.02em;
    }
    .kpi-tag-cyan { background: rgba(14, 165, 233, 0.15); color: #7DD3FC; border: 1px solid rgba(125, 211, 252, 0.25); }
    .kpi-tag-emerald { background: rgba(16, 185, 129, 0.15); color: #6EE7B7; border: 1px solid rgba(110, 231, 183, 0.25); }
    .kpi-tag-amber { background: rgba(245, 158, 11, 0.15); color: #FCD34D; border: 1px solid rgba(252, 211, 77, 0.25); }
    .kpi-tag-purple { background: rgba(168, 85, 247, 0.15); color: #D8B4FE; border: 1px solid rgba(216, 180, 254, 0.25); }

    .kpi-value {
      font-size: 1.5rem;
      font-weight: 600;
      color: #FFFFFF;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0.15rem 0;
      letter-spacing: -0.02em;
    }

    .kpi-val-green { color: #FFFFFF; }
    .kpi-val-cyan { color: #FFFFFF; }
    .kpi-val-amber { color: #FFFFFF; }
    .kpi-val-purple { color: #FFFFFF; }

    .kpi-sub {
      font-size: 0.72rem;
      color: #94A3B8;
      font-weight: 400;
    }

    .kpi-progress {
      background: #0F172A;
      height: 4px;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 0.35rem;
    }

    .kpi-progress-bar {
      height: 100%;
      background: #10B981;
      border-radius: 999px;
    }

    /* ======================================================== */
    /* 3. ÁREA DE TRABAJO PRINCIPAL (#F8FAFC / SLATE-50)        */
    /* ======================================================== */
    .saas-work-area {
      flex: 1;
      padding: 1.5rem 2rem;
      max-width: 100%;
    }

    .modular-view {
      width: 100%;
    }

    /* Main Container Grid (Matriz de 5 Canchas - 100% Ancho Completo) */
    .main-container {
      display: block;
      width: 100%;
      max-width: 100%;
    }

    /* BARRA DE HERRAMIENTAS OPERATIVA (Card Blanca, Sombra Suave) */
    .toolbar-container {
      background-color: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
      display: flex;
      flex-direction: column;
    }

    .toolbar-top-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    .toolbar-divider {
      border-top: 1px solid #E2E8F0;
      margin: 0.75rem 0;
    }

    .toolbar-bottom-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    .date-nav-group {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      flex-wrap: wrap;
    }

    .pill-group {
      display: flex;
      background: #F1F5F9;
      border: 1px solid #E2E8F0;
      border-radius: 8px;
      padding: 0.2rem;
      gap: 0.2rem;
    }

    .date-pill {
      border: none;
      background: transparent;
      color: #64748B;
      padding: 0.35rem 0.75rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }

    .date-pill.active {
      background: #0284C7;
      color: #FFFFFF;
      box-shadow: 0 2px 6px rgba(2, 132, 199, 0.35);
    }

    .date-pill:hover:not(.active) {
      color: #0F172A;
      background: #E2E8F0;
    }

    .date-picker-input {
      background-color: #FFFFFF;
      border: 1px solid #CBD5E1;
      border-radius: 8px;
      color: #0F172A;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.35rem 0.65rem;
      outline: none;
      cursor: pointer;
      transition: border-color 0.2s;
    }
    .date-picker-input:focus {
      border-color: #0284C7;
      box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.15);
    }

    .toolbar-actions-group {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    /* Botones de Acción (Fila Superior) */
    .btn-action-primary-purple {
      background: linear-gradient(135deg, #7C3AED 0%, #6D28D9 100%);
      border: 1px solid #7C3AED;
      color: #FFFFFF;
      padding: 0.45rem 0.9rem;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      box-shadow: 0 2px 6px rgba(124, 58, 237, 0.25);
      transition: all 0.2s;
    }
    .btn-action-primary-purple:hover {
      background: linear-gradient(135deg, #6D28D9 0%, #5B21B6 100%);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(124, 58, 237, 0.35);
    }

    .btn-action-emerald {
      background: linear-gradient(135deg, #059669 0%, #047857 100%);
      border: 1px solid #059669;
      color: #FFFFFF;
      padding: 0.45rem 0.9rem;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      box-shadow: 0 2px 6px rgba(5, 150, 105, 0.25);
      transition: all 0.2s;
    }
    .btn-action-emerald:hover {
      background: linear-gradient(135deg, #047857 0%, #065F46 100%);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(5, 150, 105, 0.35);
    }

    .btn-action-flash {
      background: linear-gradient(135deg, #E11D48 0%, #BE123C 100%);
      border: 1px solid #E11D48;
      color: #FFFFFF;
      padding: 0.45rem 0.9rem;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      box-shadow: 0 2px 6px rgba(225, 29, 72, 0.25);
      transition: all 0.2s;
    }
    .btn-action-flash:hover {
      background: linear-gradient(135deg, #BE123C 0%, #9F1239 100%);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(225, 29, 72, 0.35);
    }

    .btn-action-cyan {
      background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%);
      border: 1px solid #0284C7;
      color: #FFFFFF;
      padding: 0.45rem 0.9rem;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      box-shadow: 0 2px 6px rgba(2, 132, 199, 0.25);
      transition: all 0.2s;
    }
    .btn-action-cyan:hover {
      background: linear-gradient(135deg, #0369A1 0%, #075985 100%);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(2, 132, 199, 0.35);
    }

    .badge-urgency-dot {
      background: #EF4444;
      color: #FFFFFF;
      font-size: 0.6rem;
      font-weight: 800;
      padding: 0.08rem 0.35rem;
      border-radius: 999px;
      letter-spacing: 0.02em;
    }

    /* Filtros (Fila Inferior) */
    .filter-group {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .filter-label {
      font-size: 0.72rem;
      font-weight: 700;
      color: #64748B;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .filter-pill {
      border: none;
      background: transparent;
      color: #64748B;
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
      box-shadow: 0 2px 6px rgba(2, 132, 199, 0.35);
    }

    .filter-pill:hover:not(.active) {
      color: #0F172A;
      background: #E2E8F0;
    }

    /* Selector Zoom Cancha */
    .select-zoom {
      width: 210px;
      background-color: #FFFFFF;
      border: 1px solid #CBD5E1;
      border-radius: 8px;
      color: #0F172A;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.35rem 0.65rem;
      outline: none;
      cursor: pointer;
      transition: border-color 0.2s;
    }
    .select-zoom:focus {
      border-color: #0284C7;
      box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.15);
    }

    /* Section Title & Legend */
    .section-title {
      font-size: 0.9rem;
      font-weight: 800;
      color: #0F172A;
      margin-bottom: 0.75rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .calendar-legend {
      display: flex;
      gap: 0.85rem;
      align-items: center;
      font-size: 0.7rem;
      color: #64748B;
      font-weight: 600;
      flex-wrap: wrap;
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }

    .legend-box {
      width: 10px;
      height: 10px;
      border-radius: 3px;
    }
    .legend-box.emerald { background: #10B981; }
    .legend-box.amber { background: #F59E0B; }
    .legend-box.sky { background: #0284C7; }
    .legend-box.purple { background: #7C3AED; }
    .legend-box.gray { background: #FFFFFF; border: 1px dashed #94A3B8; }

    /* ======================================================== */
    /* 4. MATRIZ CALENDARIO 5 CANCHAS EN MODO CLARO PROFESIONAL */
    /* ======================================================== */
    .calendar-wrapper {
      background-color: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      overflow-x: auto;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
      position: relative;
      min-height: 440px;
    }

    .calendar-matrix {
      display: grid;
      position: relative;
    }

    /* Encabezados de Canchas (Fondo Slate-100, Etiquetas Oscuras) */
    .court-header {
      background: #F1F5F9;
      border-bottom: 2px solid #CBD5E1;
      border-right: 1px solid #E2E8F0;
      padding: 0.75rem 0.5rem;
      text-align: center;
      position: sticky;
      top: 0;
      z-index: 30;
      user-select: none;
    }

    .court-header-title {
      font-size: 0.85rem;
      font-weight: 800;
      color: #0F172A;
      letter-spacing: -0.01em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .court-header-badge {
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 700;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      margin-top: 0.2rem;
    }
    .badge-central {
      background: rgba(245, 158, 11, 0.15);
      color: #B45309;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .badge-std {
      background: rgba(2, 132, 199, 0.1);
      color: #0284C7;
      border: 1px solid rgba(2, 132, 199, 0.25);
    }

    .time-col-header {
      background: #F1F5F9;
      border-bottom: 2px solid #CBD5E1;
      border-right: 1px solid #E2E8F0;
      padding: 0.75rem 0.4rem;
      text-align: center;
      font-size: 0.72rem;
      font-weight: 800;
      color: #475569;
      position: sticky;
      top: 0;
      left: 0;
      z-index: 40;
    }

    .time-slot-label {
      background: #F8FAFC;
      border-bottom: 1px solid #E2E8F0;
      border-right: 1px solid #E2E8F0;
      padding: 0.4rem 0.5rem;
      font-size: 0.72rem;
      font-weight: 700;
      color: #64748B;
      text-align: center;
      position: sticky;
      left: 0;
      z-index: 20;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      height: 60px;
    }

    .grid-bg-cell {
      border-bottom: 1px dashed #E2E8F0;
      border-right: 1px solid #F1F5F9;
      height: 60px;
      box-sizing: border-box;
      pointer-events: none;
    }

    /* Tarjetas de Turnos en la Grilla */
    .matrix-slot-card {
      margin: 2px 4px;
      border-radius: 8px;
      padding: 0.5rem 0.65rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      position: relative;
      z-index: 15;
      transition: all 0.2s ease;
      overflow: hidden;
      box-sizing: border-box;
    }

    .matrix-slot-card:hover {
      transform: translateY(-1px);
      z-index: 22;
    }

    /* ESQUEMAS DE COLOR CLARO PROFESIONAL */
    /* 1. DISPONIBLE / LIBRE */
    .card-theme-gray {
      background: #FFFFFF;
      border: 1px dashed #CBD5E1;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
      cursor: pointer;
    }
    .card-theme-gray:hover {
      border-color: #0284C7;
      background: #F0F9FF;
      box-shadow: 0 2px 8px rgba(2, 132, 199, 0.15);
    }
    .card-theme-gray .card-time { color: #334155; }
    .card-theme-gray .card-price { color: #0F172A; }

    /* 2. ABIERTO (1/4 a 3/4) - Ámbar / Amarillo claro */
    .card-theme-amber {
      background: #FFFBEB;
      border: 1px solid #F59E0B;
      box-shadow: 0 2px 6px rgba(245, 158, 11, 0.12);
    }
    .card-theme-amber:hover {
      border-color: #D97706;
      box-shadow: 0 4px 12px rgba(245, 158, 11, 0.22);
    }
    .card-theme-amber .card-time { color: #78350F; }
    .card-theme-amber .card-price { color: #92400E; }
    .card-theme-amber .card-player-item {
      background: #1E293B;
      color: #F8FAFC;
    }

    /* 3. PAGADO / CERRADO (4/4) - Esmeralda claro */
    .card-theme-emerald {
      background: #ECFDF5;
      border: 1px solid #10B981;
      box-shadow: 0 2px 6px rgba(16, 185, 129, 0.12);
    }
    .card-theme-emerald:hover {
      border-color: #059669;
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.22);
    }
    .card-theme-emerald .card-time { color: #064E3B; }
    .card-theme-emerald .card-price { color: #065F46; }
    .card-theme-emerald .card-player-item {
      background: #D1FAE5;
      color: #065F46;
      border: 1px solid #A7F3D0;
    }

    /* 4. CLASE / ACADEMIA - Sky / Azul claro */
    .card-theme-academy {
      background: #F0F9FF;
      border: 1px solid #38BDF8;
      box-shadow: 0 2px 6px rgba(56, 189, 248, 0.12);
    }
    .card-theme-academy:hover {
      border-color: #0284C7;
      box-shadow: 0 4px 12px rgba(56, 189, 248, 0.22);
    }
    .card-theme-academy .card-time { color: #0C4A6E; }
    .card-theme-academy .card-price { color: #0369A1; }

    /* 5. AMERICANO / TORNEO - Violeta claro */
    .card-theme-purple {
      background: #FAF5FF;
      border: 1px solid #A855F7;
      box-shadow: 0 2px 6px rgba(168, 85, 247, 0.12);
    }
    .card-theme-purple:hover {
      border-color: #7C3AED;
      box-shadow: 0 4px 12px rgba(168, 85, 247, 0.22);
    }
    .card-theme-purple .card-time { color: #581C87; }
    .card-theme-purple .card-price { color: #6B21A8; }

    /* 6. BLOQUEADO / MANTENIMIENTO */
    .card-theme-blocked {
      background: #FEF2F2;
      border: 1px dashed #F87171;
    }
    .card-theme-blocked .card-time { color: #991B1B; }

    /* Badges Internos del Card */
    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.25rem;
    }

    .card-time {
      font-size: 0.78rem;
      font-weight: 800;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    .card-dur-badge {
      font-size: 0.62rem;
      font-weight: 700;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      background: rgba(15, 23, 42, 0.06);
      color: #475569;
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
      background: #D1FAE5;
      color: #047857;
      border: 1px solid #6EE7B7;
    }
    .badge-status-open {
      background: #FEF3C7;
      color: #B45309;
      border: 1px solid #FCD34D;
    }
    .badge-status-academy {
      background: #E0F2FE;
      color: #0369A1;
      border: 1px solid #7DD3FC;
    }
    .badge-status-tournament {
      background: #F3E8FF;
      color: #6B21A8;
      border: 1px solid #D8B4FE;
    }
    .badge-status-free {
      background: #F1F5F9;
      color: #475569;
      border: 1px solid #CBD5E1;
    }
    .badge-status-blocked {
      background: #FEE2E2;
      color: #B91C1C;
      border: 1px solid #FCA5A5;
    }

    .card-category {
      font-size: 0.62rem;
      color: #64748B;
      background: #F1F5F9;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      border: 1px solid #E2E8F0;
    }

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
      box-shadow: 0 1px 4px rgba(225, 29, 72, 0.4);
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
      background: #FEE2E2;
      border: 1px solid #FCA5A5;
      color: #B91C1C;
    }
    .tier-valle {
      background: #ECFDF5;
      border: 1px solid #A7F3D0;
      color: #047857;
    }

    .card-players {
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
      margin: 0.35rem 0;
    }

    .card-player-item {
      font-size: 0.7rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.15rem 0.35rem;
      border-radius: 4px;
    }

    .btn-card-drop {
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #EF4444;
      font-size: 0.6rem;
      padding: 0.05rem 0.25rem;
      border-radius: 3px;
      cursor: pointer;
      line-height: 1;
    }
    .btn-card-drop:hover {
      background: #EF4444;
      color: #FFFFFF;
    }

    .card-footer {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      border-top: 1px solid rgba(0, 0, 0, 0.06);
      padding-top: 0.35rem;
      margin-top: 0.35rem;
    }

    .card-price {
      font-size: 0.78rem;
      font-weight: 800;
    }

    .card-price-sub {
      font-size: 0.58rem;
      color: #64748B;
      display: block;
    }

    .btn-card-reserve {
      background: #0284C7;
      border: 1px solid #0284C7;
      color: #FFFFFF;
      font-size: 0.65rem;
      font-weight: 700;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-card-reserve:hover {
      background: #0369A1;
    }

    .btn-card-action {
      background: #D97706;
      border: 1px solid #D97706;
      color: #FFFFFF;
      font-size: 0.65rem;
      font-weight: 700;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-card-action:hover {
      background: #B45309;
    }

    .card-full-badge {
      font-size: 0.65rem;
      color: #059669;
      font-weight: 700;
    }

    /* Urgent Pulse Animation */
    @keyframes urgent-pulse {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); border-color: #EF4444; }
      70% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); border-color: #F87171; }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); border-color: #EF4444; }
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
    }

    /* ======================================================== */
    /* 5. SIDEBAR DERECHO (WHATSAPP, AUDIT, HOLDS)             */
    /* ======================================================== */
    .sidebar {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }

    .sidebar-card {
      background-color: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      padding: 1.25rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }

    .sidebar-title {
      font-size: 0.85rem;
      font-weight: 800;
      color: #0F172A;
      margin-bottom: 0.85rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #F1F5F9;
      padding-bottom: 0.5rem;
    }

    .metric-box {
      background-color: #F8FAFC;
      border: 1px solid #E2E8F0;
      border-radius: 8px;
      padding: 0.85rem;
      margin-bottom: 0.75rem;
    }
    .metric-box:last-child {
      margin-bottom: 0;
    }

    .metric-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.72rem;
      color: #64748B;
      font-weight: 600;
      margin-bottom: 0.35rem;
    }

    .metric-number {
      font-size: 1.4rem;
      font-weight: 800;
      color: #0284C7;
      font-family: ui-monospace, monospace;
    }

    .wa-textarea {
      width: 100%;
      height: 120px;
      background-color: #F8FAFC;
      border: 1px solid #CBD5E1;
      border-radius: 8px;
      color: #0F172A;
      padding: 0.65rem;
      font-size: 0.75rem;
      resize: vertical;
      margin-bottom: 0.65rem;
      font-family: ui-monospace, monospace;
    }
    .wa-textarea:focus {
      border-color: #10B981;
      background-color: #FFFFFF;
      outline: none;
    }

    .btn-wa {
      width: 100%;
      background: linear-gradient(135deg, #059669 0%, #047857 100%);
      color: #FFFFFF;
      border: none;
      padding: 0.65rem;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      box-shadow: 0 2px 6px rgba(5, 150, 105, 0.25);
      transition: all 0.2s;
    }
    .btn-wa:hover {
      filter: brightness(1.1);
    }

    .wa-result-box {
      margin-top: 0.75rem;
      background-color: #F8FAFC;
      border: 1px solid #E2E8F0;
      border-radius: 8px;
      padding: 0.65rem;
      font-size: 0.7rem;
      color: #334155;
      white-space: pre-wrap;
      max-height: 140px;
      overflow-y: auto;
    }

    .event-feed {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      max-height: 240px;
      overflow-y: auto;
    }

    .event-item {
      font-size: 0.72rem;
      color: #475569;
      padding: 0.45rem 0.6rem;
      background-color: #F8FAFC;
      border-radius: 6px;
      border-left: 3px solid #0284C7;
      display: flex;
      gap: 0.5rem;
      align-items: flex-start;
    }

    .event-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: #0284C7;
      margin-top: 4px;
    }

    /* Modal Styling */
    .modal-overlay {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 23, 42, 0.65);
      backdrop-filter: blur(4px);
      z-index: 100;
      align-items: center;
      justify-content: center;
    }
    .modal-overlay.active {
      display: flex;
    }

    .modal-card {
      background: #FFFFFF;
      border: 1px solid #CBD5E1;
      border-radius: 12px;
      width: 100%;
      max-width: 480px;
      padding: 1.5rem;
      color: #0F172A;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
    }

    .modal-title {
      font-size: 1.1rem;
      font-weight: 800;
      margin-bottom: 0.75rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #E2E8F0;
      padding-bottom: 0.5rem;
    }

    .form-group {
      margin-bottom: 0.85rem;
    }

    .form-label {
      font-size: 0.72rem;
      font-weight: 700;
      color: #475569;
      margin-bottom: 0.25rem;
      display: block;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .form-control {
      width: 100%;
      background: #F8FAFC;
      border: 1px solid #CBD5E1;
      border-radius: 6px;
      padding: 0.5rem 0.65rem;
      color: #0F172A;
      font-size: 0.8rem;
      outline: none;
    }
    .form-control:focus {
      border-color: #0284C7;
      background: #FFFFFF;
    }

    .modal-actions {
      display: flex;
      gap: 0.5rem;
      justify-content: flex-end;
      margin-top: 1.25rem;
    }

    .btn-secondary {
      background: #F1F5F9;
      border: 1px solid #CBD5E1;
      color: #475569;
      padding: 0.5rem 1rem;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-secondary:hover {
      background: #E2E8F0;
      color: #0F172A;
    }

    .btn-primary {
      background: #0284C7;
      border: none;
      color: #FFFFFF;
      padding: 0.5rem 1rem;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
    }
    .btn-primary:hover {
      background: #0369A1;
    }

    .btn-seed {
      background: #0284C7;
      border: none;
      color: #FFFFFF;
      padding: 0.45rem 0.85rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
    }

    /* Benchmarking & Pro Placeholders */
    .pro-badge {
      background: linear-gradient(135deg, #A855F7 0%, #6366F1 100%);
      color: #FFFFFF;
      font-size: 0.65rem;
      font-weight: 800;
      padding: 0.15rem 0.5rem;
      border-radius: 4px;
      letter-spacing: 0.05em;
    }
  
    /* Multi-Sport Pills & Themes */
    .sport-selector-group {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      flex-wrap: wrap;
    }
    .sport-pill {
      border: 1px solid #CBD5E1;
      background: #FFFFFF;
      color: #475569;
      padding: 0.35rem 0.85rem;
      border-radius: 6px;
      font-size: 0.78rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s ease;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }
    .sport-pill:hover:not(.active) {
      color: #0F172A;
      background: #F1F5F9;
      border-color: #94A3B8;
    }
    .sport-pill.active {
      background: #0284C7;
      border-color: #0284C7;
      color: #FFFFFF;
      box-shadow: 0 2px 6px rgba(2, 132, 199, 0.35);
    }
    .sport-pill.active.active-pickleball {
      background: #D97706 !important;
      border-color: #D97706 !important;
      box-shadow: 0 2px 6px rgba(217, 119, 6, 0.35) !important;
    }
    .sport-pill.active.active-volleyball {
      background: #EA580C !important;
      border-color: #EA580C !important;
      box-shadow: 0 2px 6px rgba(234, 88, 12, 0.35) !important;
    }
    .sport-pill.active.active-pilates {
      background: #7C3AED !important;
      border-color: #7C3AED !important;
      box-shadow: 0 2px 6px rgba(124, 58, 237, 0.35) !important;
    }

    /* Multi-Sport Card Themes */
    .card-theme-volleyball {
      background: #FFFBEB;
      border: 1px solid #F59E0B;
      box-shadow: 0 2px 6px rgba(245, 158, 11, 0.15);
    }
    .card-theme-volleyball:hover {
      border-color: #D97706;
      box-shadow: 0 4px 12px rgba(245, 158, 11, 0.25);
    }
    .card-theme-volleyball .card-time { color: #92400E; }
    .card-theme-volleyball .card-price { color: #B45309; }

    .card-theme-pilates {
      background: #FAF5FF;
      border: 1px solid #C084FC;
      box-shadow: 0 2px 6px rgba(192, 132, 252, 0.15);
    }
    .card-theme-pilates:hover {
      border-color: #A855F7;
      box-shadow: 0 4px 12px rgba(192, 132, 252, 0.25);
    }
    .card-theme-pilates .card-time { color: #6B21A8; }
    .card-theme-pilates .card-price { color: #7E22CE; }

    .badge-status-volleyball {
      background: #FEF3C7;
      color: #92400E;
      border: 1px solid #FDE68A;
    }
    .badge-status-pilates {
      background: #F3E8FF;
      color: #7E22CE;
      border: 1px solid #E9D5FF;
    }


    /* ======================================================== */
    /* ESTILOS: PANEL AUDITORÍA INFERIOR & HOLDS                */
    /* ======================================================== */
    .bottom-audit-panel {
      background-color: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      margin-top: 1.5rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
      overflow: hidden;
    }
    .audit-panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.85rem 1.25rem;
      background-color: #F8FAFC;
      border-bottom: 1px solid #E2E8F0;
      cursor: pointer;
      user-select: none;
    }
    .audit-panel-header:hover {
      background-color: #F1F5F9;
    }
    .badge-audit-count {
      background: #FEF3C7;
      color: #D97706;
      border: 1px solid #FDE68A;
      font-size: 0.68rem;
      font-weight: 700;
      padding: 0.15rem 0.5rem;
      border-radius: 999px;
    }
    .btn-toggle-audit {
      background: transparent;
      border: none;
      color: #64748B;
      font-size: 0.75rem;
      font-weight: 700;
      cursor: pointer;
    }
    .audit-panel-body {
      padding: 1.25rem;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.25rem;
    }
    @media (max-width: 900px) {
      .audit-panel-body {
        grid-template-columns: 1fr;
      }
    }

    /* ======================================================== */
    /* ESTILOS: ASISTENTE BOT FLOTANTE & DRAWER LATERAL         */
    /* ======================================================== */
    .btn-floating-bot {
      position: fixed;
      bottom: 1.75rem;
      right: 1.75rem;
      z-index: 100;
      background: linear-gradient(135deg, #059669 0%, #047857 100%);
      color: #FFFFFF;
      border: 1px solid rgba(255, 255, 255, 0.25);
      border-radius: 999px;
      padding: 0.75rem 1.35rem;
      font-size: 0.85rem;
      font-weight: 800;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      box-shadow: 0 4px 16px rgba(5, 150, 105, 0.4);
      transition: all 0.25s ease;
    }
    .btn-floating-bot:hover {
      transform: translateY(-2px) scale(1.02);
      box-shadow: 0 6px 20px rgba(5, 150, 105, 0.5);
    }
    .bot-floating-dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background-color: #34D399;
      animation: pulse 1.8s infinite;
    }

    .bot-drawer-backdrop {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(15, 23, 42, 0.4);
      backdrop-filter: blur(2px);
      z-index: 210;
    }
    .bot-drawer-backdrop.active {
      display: block;
    }

    .bot-drawer {
      position: fixed;
      top: 0;
      right: 0;
      width: 440px;
      max-width: 92vw;
      height: 100vh;
      background: #FFFFFF;
      box-shadow: -4px 0 25px rgba(0, 0, 0, 0.15);
      z-index: 220;
      display: flex;
      flex-direction: column;
      transform: translateX(100%);
      transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .bot-drawer.active {
      transform: translateX(0);
    }

    .bot-drawer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1.1rem 1.25rem;
      border-bottom: 1px solid #E2E8F0;
      background: #F8FAFC;
    }
    .btn-close-drawer {
      background: none;
      border: none;
      font-size: 1.5rem;
      line-height: 1;
      color: #64748B;
      cursor: pointer;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
    }
    .btn-close-drawer:hover {
      background: #E2E8F0;
      color: #0F172A;
    }

    .bot-drawer-body {
      padding: 1.25rem;
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }

    /* ======================================================== */
    /* ESTILOS: ANIMACIÓN Y BADGE 'ON FIRE' EN SLOTS CRÍTICOS   */
    /* ======================================================== */
    @keyframes fireGlow {
      0% {
        box-shadow: 0 0 4px rgba(245, 158, 11, 0.4), inset 0 0 4px rgba(245, 158, 11, 0.1);
        border-color: #F59E0B;
      }
      50% {
        box-shadow: 0 0 14px rgba(239, 68, 68, 0.6), inset 0 0 8px rgba(245, 158, 11, 0.25);
        border-color: #EF4444;
      }
      100% {
        box-shadow: 0 0 4px rgba(245, 158, 11, 0.4), inset 0 0 4px rgba(245, 158, 11, 0.1);
        border-color: #F59E0B;
      }
    }

    .matrix-slot-card.slot-on-fire {
      animation: fireGlow 2s infinite ease-in-out;
      border: 1.5px solid #F59E0B !important;
    }

    .badge-critical-fire {
      background: linear-gradient(135deg, #EF4444 0%, #F59E0B 100%);
      color: #FFFFFF;
      font-size: 0.6rem;
      font-weight: 800;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      box-shadow: 0 1px 4px rgba(239, 68, 68, 0.4);
      letter-spacing: 0.02em;
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
    }

    .btn-card-remate-flash {
      background: linear-gradient(135deg, #E11D48 0%, #EA580C 100%);
      color: #FFFFFF;
      border: none;
      font-size: 0.65rem;
      font-weight: 800;
      padding: 0.25rem 0.55rem;
      border-radius: 6px;
      cursor: pointer;
      box-shadow: 0 2px 5px rgba(225, 29, 72, 0.3);
      transition: all 0.18s;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      margin-top: 0.25rem;
    }
    .btn-card-remate-flash:hover {
      transform: translateY(-1px);
      box-shadow: 0 3px 8px rgba(225, 29, 72, 0.45);
    }

    /* ======================================================== */
    /* ESTILOS: AUTOCOMPLETADO DE CLIENTES CRM EN MODAL        */
    /* ======================================================== */
    .customer-dropdown {
      position: absolute;
      top: 100%;
      left: 0;
      right: 0;
      max-height: 200px;
      overflow-y: auto;
      background: #FFFFFF;
      border: 1px solid #CBD5E1;
      border-radius: 8px;
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
      z-index: 1000;
      margin-top: 4px;
    }
    .customer-dropdown-item {
      padding: 0.6rem 0.85rem;
      border-bottom: 1px solid #F1F5F9;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: background 0.15s;
    }
    .customer-dropdown-item:hover {
      background-color: #F8FAFC;
    }
    .customer-dropdown-item:last-child {
      border-bottom: none;
    }
    .customer-item-name {
      font-weight: 700;
      color: #0F172A;
      font-size: 0.8rem;
    }
    .customer-item-phone {
      font-size: 0.72rem;
      color: #64748B;
      font-family: monospace;
    }
    .customer-item-badge {
      font-size: 0.62rem;
      font-weight: 800;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      background: #E0F2FE;
      color: #0284C7;
    }

    /* ======================================================== */
    /* LINEA DE TIEMPO HORIZONTAL CONTINUA                     */
    /* ======================================================== */
    .timeline-continuous-bar {
      display: inline-flex;
      align-items: center;
      background: #F1F5F9;
      border: 1px solid #CBD5E1;
      border-radius: 999px;
      padding: 2px;
      position: relative;
      gap: 2px;
    }
    .timeline-step {
      border: none;
      background: transparent;
      padding: 0.28rem 0.65rem;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 600;
      color: #64748B;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      transition: all 0.18s ease;
      white-space: nowrap;
    }
    .timeline-step:hover {
      color: #0F172A;
      background: rgba(255, 255, 255, 0.7);
    }
    .timeline-step.active {
      background: #0284C7;
      color: #FFFFFF;
      font-weight: 700;
      box-shadow: 0 1px 4px rgba(2, 132, 199, 0.3);
    }
    .timeline-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #94A3B8;
    }
    .timeline-step.active .timeline-dot {
      background: #FFFFFF;
    }

    /* ======================================================== */
    /* TABLA RANKING CRM & SUGERENCIAS ASCENSO                  */
    /* ======================================================== */
    .table-ranking th {
      font-weight: 700;
      color: #475569;
    }
    .table-ranking td {
      padding: 0.85rem 1rem;
      border-bottom: 1px solid #F1F5F9;
      font-size: 0.8rem;
      color: #1E293B;
      vertical-align: middle;
    }
    .table-ranking tr:hover td {
      background-color: #F8FAFC;
    }
    .badge-rank-pos {
      font-weight: 800;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 0.72rem;
    }
    .badge-rank-1 { background: #FEF3C7; color: #B45309; border: 1px solid #FDE68A; }
    .badge-rank-2 { background: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; }
    .badge-rank-3 { background: #FFEDD5; color: #C2410C; border: 1px solid #FED7AA; }
    .badge-rank-other { background: #F8FAFC; color: #64748B; border: 1px solid #E2E8F0; }

    .badge-promotion-sug {
      background: linear-gradient(135deg, #FEF3C7 0%, #DCFCE7 100%);
      color: #166534;
      border: 1px solid #86EFAC;
      font-size: 0.65rem;
      font-weight: 800;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      animation: pulse 2s infinite;
    }
    .btn-approve-promote {
      background: #059669;
      color: #FFFFFF;
      border: none;
      padding: 0.25rem 0.55rem;
      border-radius: 6px;
      font-size: 0.68rem;
      font-weight: 800;
      cursor: pointer;
      margin-left: 0.4rem;
      transition: all 0.15s;
    }
    .btn-approve-promote:hover {
      background: #047857;
      transform: scale(1.04);
    }

    /* ======================================================== */
    /* TARJETAS DE TORNEO AMERICANO                            */
    /* ======================================================== */
    .tourn-card {
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      padding: 1.15rem;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s;
    }
    .tourn-card:hover {
      box-shadow: 0 6px 16px rgba(124, 58, 237, 0.1);
      border-color: #DDD6FE;
    }
    .tourn-card-finished {
      border-left: 4px solid #10B981;
      background: #FAFBFD;
    }
    .tourn-card-active {
      border-left: 4px solid #7C3AED;
    }

      /* ESTILOS REFORZADOS BARRA DE CONTROL SAAS LIMPIA */
    .sidebar-nav-item.active {
      background-color: #F1F5F9 !important; /* slate-100 */
      color: #0F172A !important; /* slate-900 */
      font-weight: 500 !important; /* font-medium */
      box-shadow: inset 3px 0 0 #0284C7;
    }

    .sport-pill {
      color: #475569;
      background: transparent;
      border: none;
      cursor: pointer;
      font-weight: 600;
    }
    .sport-pill:hover {
      background-color: #F1F5F9;
      color: #0F172A;
    }
    .sport-pill.active {
      background-color: #0F172A !important; /* bg-slate-900 */
      color: #FFFFFF !important;
      font-weight: 700 !important;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    }

    .timeline-btn {
      color: #475569;
      background: transparent;
      border: none;
      cursor: pointer;
      font-weight: 500;
    }
    .timeline-btn:hover {
      background-color: #F8FAFC;
      color: #0F172A;
    }
    .timeline-btn.active {
      background-color: #0F172A !important;
      color: #FFFFFF !important;
      font-weight: 700 !important;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    }

  </style>
</head>
<body>

  <!-- ======================================================== -->
  <!-- LAYOUT SAAS PROFESIONAL: SIDEBAR FIJO + CONTENIDO        -->
  <!-- ======================================================== -->
  <div class="saas-layout">

    <!-- 1. SIDEBAR FIJO A LA IZQUIERDA (w-64) -->
    <aside class="saas-sidebar">
      <div>
        <!-- Logo & Marca -->
        <div class="sidebar-brand">
          <a href="/dashboard" class="brand-title">
            <span class="brand-icon">⚡</span>
            <span class="brand-name">Afluenc.IA</span>
            <span class="brand-badge">YieldPadel</span>
          </a>
          <div class="brand-sub">
            <span>📍 Capital Pádel Club (5 Canchas)</span>
          </div>
        </div>

        <!-- Menú Vertical de Navegación -->
        <nav class="sidebar-nav modular-nav-bar">
          <button class="sidebar-nav-item active" id="tab-matrix" onclick="switchMainView('view-matrix')">
            <span class="nav-icon">📅</span>
            <span class="nav-text">Matriz Calendario</span>
          </button>
          <button class="sidebar-nav-item" id="tab-yield" onclick="switchMainView('view-yield')">
            <span class="nav-icon">🏆</span>
            <span class="nav-text">Torneos Americanos</span>
          </button>
          <button class="sidebar-nav-item" id="tab-crm" onclick="switchMainView('view-crm')">
            <span class="nav-icon">👥</span>
            <span class="nav-text">CRM Jugadores</span>
          </button>
          <button class="sidebar-nav-item" id="tab-radar" onclick="switchMainView('view-radar')">
            <span class="nav-icon">📈</span>
            <span class="nav-text">Radar de Precios</span>
          </button>
          <button class="sidebar-nav-item" id="tab-indicators" onclick="switchMainView('view-indicators')">
            <span class="nav-icon">💡</span>
            <span class="nav-text">Motor de Yield</span>
          </button>
          <button class="sidebar-nav-item" id="tab-config" onclick="switchMainView('view-config')">
            <span class="nav-icon">⚙️</span>
            <span class="nav-text">Configuración del Club</span>
          </button>
        </nav>
      </div>

      <!-- Pie del Sidebar -->
      <div class="sidebar-footer">
        <div class="api-live-badge">
          <span class="live-dot"></span>
          <span>🟢 API Live (Bogotá)</span>
        </div>
        <button onclick="fetchSlots()" class="btn-refresh-sidebar" title="Refrescar turnos en vivo">
          ↻ Refrescar Datos
        </button>
      </div>
    </aside>

    <!-- 2. CONTENIDO PRINCIPAL SAAS -->
    <div class="saas-main-content">

      <!-- ======================================================== -->
      <!-- 2. BANNER EJECUTIVO SUPERIOR (HEADER OSCURO #0F172A)     -->
      <!-- ======================================================== -->
      <header class="executive-banner">
        <div class="banner-header">
          <div class="banner-title-area">
            <h1 class="banner-main-title">Panel Operativo Capital Pádel Club</h1>
            <div class="banner-date-badge" id="banner-date-display">📅 Hoy (07/09/2026)</div>
          </div>
          <div class="banner-venue-badge">
            <span class="badge-status-dot"></span>
            <span id="banner-venue-badge-text">Sede Principal • 5 Pistas Panorámicas</span>
          </div>
        </div>

        <!-- Fila de 5 Tarjetas KPIs Compactas -->
        <div class="kpi-grid">
          <!-- KPI 1: Clientes Activos -->
          <div class="kpi-card">
            <div class="kpi-label">
              <span>Clientes Activos</span>
              <span class="kpi-tag kpi-tag-cyan">+12 este mes</span>
            </div>
            <div class="kpi-value" id="kpi-active-clients">134</div>
            <div class="kpi-sub">registrados en el club</div>
          </div>

          <!-- KPI 2: Ingresos Confirmados -->
          <div class="kpi-card">
            <div class="kpi-label">
              <span>Ingresos Confirmados</span>
              <span class="kpi-tag kpi-tag-emerald">En Vivo</span>
            </div>
            <div class="kpi-value kpi-val-green" id="kpi-revenue">$2.970.500 COP</div>
            <div class="kpi-sub">acumulado de la fecha</div>
          </div>

          <!-- KPI 3: Tasa de Ocupación Hoy -->
          <div class="kpi-card">
            <div class="kpi-label">
              <span>Tasa Ocupación Hoy</span>
              <span class="kpi-tag kpi-tag-emerald" id="kpi-occupancy-tag">Alta demanda</span>
            </div>
            <div class="kpi-value kpi-val-cyan" id="kpi-occupancy">84%</div>
            <div class="kpi-progress">
              <div class="kpi-progress-bar" id="kpi-occupancy-bar" style="width: 84%;"></div>
            </div>
          </div>

          <!-- KPI 4: Partidos Abiertos por Completar -->
          <div class="kpi-card">
            <div class="kpi-label">
              <span>Partidos Abiertos</span>
              <span class="kpi-tag kpi-tag-amber" id="kpi-open-tag">Completar</span>
            </div>
            <div class="kpi-value kpi-val-amber" id="kpi-open-matches">4 abiertos</div>
            <div class="kpi-sub" id="kpi-open-spots-sub">chips de cupos libres</div>
          </div>

          <!-- KPI 5: RevPAST Proyectado -->
          <div class="kpi-card">
            <div class="kpi-label">
              <span>RevPAST Proyectado</span>
              <span class="kpi-tag kpi-tag-purple">Meta $1.5M</span>
            </div>
            <div class="kpi-value kpi-val-purple" id="kpi-revpast">$1.200.000 COP</div>
            <div class="kpi-sub">por cancha disponible</div>
          </div>
        </div>
      </header>

      <!-- ======================================================== -->
      <!-- 3. ÁREA DE TRABAJO PRINCIPAL (#F8FAFC)                  -->
      <!-- ======================================================== -->
      <div class="saas-work-area">

        <!-- ======================================================== -->
        <!-- VISTA 1: 📅 MATRIZ CALENDARIO (OPERACIÓN EN TIEMPO REAL) -->
        <!-- ======================================================== -->
        <div id="view-matrix" class="modular-view">
          
          <!-- BARRA DE HERRAMIENTAS OPERATIVA (Card Blanca 2 Filas) -->
<!-- BARRA DE CONTROL EN 2 FILAS CON ESTÉTICA SAAS LIMPIA -->
          <div class="bg-white border border-slate-200 rounded-xl p-4 mb-6 shadow-sm flex flex-col gap-3.5">
            
            <!-- FILA 1: Fecha & Acciones Principales -->
            <div class="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
              
              <!-- Izquierda: Selector compacto de navegación temporal -->
              <div class="flex items-center gap-2">
                <div class="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 shadow-sm">
                  <button type="button" onclick="setRelativeDate(-1)" id="btn-date-yesterday" class="px-2.5 py-1.5 text-xs font-semibold rounded-md text-slate-700 hover:bg-white hover:shadow-xs transition" title="Día anterior">
                    &lt;
                  </button>
                  <button type="button" onclick="setRelativeDate(0)" id="btn-date-today" class="px-3 py-1.5 text-xs font-bold rounded-md bg-white text-slate-900 shadow-xs transition" title="Ir a hoy">
                    Hoy
                  </button>
                  <button type="button" onclick="setRelativeDate(1)" id="btn-date-tomorrow" class="px-2.5 py-1.5 text-xs font-semibold rounded-md text-slate-700 hover:bg-white hover:shadow-xs transition" title="Día siguiente">
                    &gt;
                  </button>
                </div>
                <input type="date" id="selected-date" onchange="onDateInputChange(this.value)" class="h-9 px-3 text-sm rounded-lg border border-slate-300 bg-white shadow-sm font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900" title="Seleccionar fecha" />
              </div>

              <!-- Derecha: Botones de acción agrupados con estilo profesional -->
              <div class="flex items-center gap-2 flex-wrap">
                <!-- [🏆 + Torneo Americano] (bg-violet-600 hover:bg-violet-700 text-white shadow-sm) -->
                <button type="button" onclick="openCreateAmericanoModal()" id="btn-create-americano" class="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg bg-violet-600 hover:bg-violet-700 text-white shadow-sm transition">
                  <span>🏆</span> + Torneo Americano
                </button>

                <!-- [📢 Difundir WhatsApp] (bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm) -->
                <button type="button" onclick="broadcastAvailability()" id="btn-broadcast-avail" class="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition">
                  <span>📢</span> Difundir WhatsApp
                </button>

                <!-- [⚡ Remate Flash] (border border-rose-300 bg-rose-50 text-rose-700 hover:bg-rose-100) -->
                <button type="button" onclick="broadcastPromoUrgent()" id="btn-broadcast-promo" class="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg border border-rose-300 bg-rose-50 text-rose-700 hover:bg-rose-100 transition shadow-xs">
                  <span>⚡</span> Remate Flash
                  <span class="px-1 py-0.2 text-[9px] font-bold bg-rose-200 text-rose-800 rounded-full">-25%</span>
                </button>

                <!-- [🌱 Sembrar 7 Días] (border border-slate-200 hover:bg-slate-50 text-slate-700) -->
                <button type="button" onclick="seedFiveCourts()" id="btn-seed-courts" class="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 transition shadow-xs">
                  <span>🌱</span> Sembrar 7 Días
                </button>
              </div>

            </div>

            <!-- FILA 2: Deporte y Filtros de Visualización -->
            <div class="flex flex-wrap items-center justify-between gap-3 pt-0.5">
              
              <!-- Izquierda: Selector de Deporte como Pestañas/Pills (Segmented Control) -->
              <div class="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1 gap-1" id="sport-selector-container">
                <button type="button" onclick="setSportFilter('PADEL')" id="btn-sport-padel" class="sport-pill active px-3 py-1.5 text-xs font-semibold rounded-md transition" title="5 Pistas de Pádel">
                  🎾 Pádel
                </button>
                <button type="button" onclick="setSportFilter('PICKLEBALL')" id="btn-sport-pickleball" class="sport-pill px-3 py-1.5 text-xs font-semibold rounded-md transition" title="2 Pistas de Pickleball">
                  🏓 Pickleball
                </button>
                <button type="button" onclick="setSportFilter('VOLLEYBALL')" id="btn-sport-volleyball" class="sport-pill px-3 py-1.5 text-xs font-semibold rounded-md transition" title="1 Cancha de Arena de Vóley">
                  🏐 Vóley
                </button>
                <button type="button" onclick="setSportFilter('PILATES')" id="btn-sport-pilates" class="sport-pill px-3 py-1.5 text-xs font-semibold rounded-md transition" title="1 Estudio de Pilates">
                  🧘 Pilates
                </button>
              </div>

              <!-- Centro: Filtro horario en línea horizontal minimalista -->
              <div class="inline-flex rounded-lg border border-slate-200 bg-white p-1 gap-1 shadow-xs" id="time-filter-container">
                <button type="button" onclick="setTimeFilter('ALL')" id="btn-time-all" class="timeline-btn active px-2.5 py-1 text-xs font-medium rounded-md transition">
                  Todo el día
                </button>
                <button type="button" onclick="setTimeFilter('MORNING')" id="btn-time-morning" class="timeline-btn px-2.5 py-1 text-xs font-medium rounded-md transition">
                  Mañana (6-12)
                </button>
                <button type="button" onclick="setTimeFilter('AFTERNOON')" id="btn-time-afternoon" class="timeline-btn px-2.5 py-1 text-xs font-medium rounded-md transition">
                  Tarde (12-18)
                </button>
                <button type="button" onclick="setTimeFilter('NIGHT')" id="btn-time-night" class="timeline-btn px-2.5 py-1 text-xs font-medium rounded-md transition">
                  Noche (18-24)
                </button>
              </div>

              <!-- Derecha: Filtro de estado y desplegable compacto de Cancha -->
              <div class="flex items-center gap-3">
                <div class="inline-flex rounded-lg border border-slate-200 bg-white p-1 gap-1 shadow-xs">
                  <button type="button" onclick="setStatusFilter('ALL')" id="btn-status-all" class="filter-pill active px-2.5 py-1 text-xs font-medium rounded-md">
                    Todos
                  </button>
                  <button type="button" onclick="setStatusFilter('OPEN')" id="btn-status-open" class="filter-pill px-2.5 py-1 text-xs font-medium rounded-md">
                    Abiertos
                  </button>
                  <button type="button" onclick="setStatusFilter('PAID')" id="btn-status-paid" class="filter-pill px-2.5 py-1 text-xs font-medium rounded-md">
                    Pagados
                  </button>
                </div>

                <select id="court-zoom-select" onchange="setCourtZoom(this.value)" class="h-8 text-xs rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-slate-900 shadow-xs">
                  <option value="ALL">🏟️ Todas las Canchas</option>
                </select>
              </div>

            </div>

          </div>

          <!-- Contenedor Principal: Matriz 5 Canchas a Ancho Completo (100%) -->
          <main class="main-container">

            <section style="width: 100%;">
              
              <!-- Título de Sección y Leyenda Visual -->
              <div class="section-title">
                <div style="display: flex; align-items: center; gap: 0.6rem;">
                  <span id="matrix-title-text">📅 Matriz Calendario Operativo (🎾 Pádel - 5 Canchas)</span>
                  <span id="slots-count" style="font-size: 0.75rem; color: #0284C7; font-weight: 700; background: #E0F2FE; padding: 0.2rem 0.6rem; border-radius: 999px; border: 1px solid #BAE6FD;">Cargando...</span>
                </div>
                
                <div class="calendar-legend">
                  <span class="legend-item"><span class="legend-box emerald"></span> Pagado / Cerrado (4/4)</span>
                  <span class="legend-item"><span class="legend-box amber"></span> Abierto (1-3)</span>
                  <span class="legend-item"><span class="legend-box sky"></span> 🎾 Clase / Academia</span>
                  <span class="legend-item"><span class="legend-box purple"></span> 🏆 Americano / Torneo</span>
                  <span class="legend-item"><span class="legend-box gray"></span> Disponible (Click para Reservar)</span>
                </div>
              </div>

              <!-- Contenedor Matriz Calendario Profesional Claro -->
              <div class="calendar-wrapper" id="calendar-wrapper">
                <div id="calendar-matrix" class="calendar-matrix">
                  <div id="grid-loader" style="grid-column: 1/-1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem; text-align: center; color: #64748B;">
                    <div style="display: inline-block; width: 36px; height: 36px; border: 3px solid #E2E8F0; border-radius: 50%; border-top-color: #0284C7; animation: spin 0.8s linear infinite; margin-bottom: 0.75rem;"></div>
                    <div style="font-size: 0.85rem; font-weight: 700; color: #0F172A;">Cargando turnos de la jornada...</div>
                    <div style="font-size: 0.72rem; color: #64748B; margin-top: 0.25rem;">Consultando disponibilidad y tarifas dinámicas</div>
                  </div>
                </div>
              </div>

              <!-- PANEL INFERIOR AUDITORÍA, HOLDS ACTIVOS Y AUDIT LOG -->
              <div class="bottom-audit-panel" id="bottom-audit-panel">
                <div class="audit-panel-header" onclick="toggleAuditPanel()">
                  <div style="display: flex; align-items: center; gap: 0.6rem;">
                    <span style="font-size: 1.1rem;">📋</span>
                    <span style="font-weight: 700; color: #0F172A; font-size: 0.85rem;">Holds Activos Bold/Wompi & Auditoría de Eventos</span>
                    <span class="badge-audit-count" id="audit-holds-count">0 holds activos</span>
                  </div>
                  <button type="button" class="btn-toggle-audit" id="btn-toggle-audit">▲ Colapsar Panel</button>
                </div>
                <div class="audit-panel-body" id="audit-panel-body">
                  <!-- Card Holds Activos -->
                  <div class="sidebar-card">
                    <div class="sidebar-title">
                      <span>Holds Activos Temporales</span>
                      <span style="color: #D97706; font-size: 0.7rem; font-weight: 700;">Bold / Wompi (15 min)</span>
                    </div>
                    <div id="active-holds-container">
                      <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 0.75rem; text-align: center; font-size: 0.72rem; color: #64748B;">
                        No hay holds activos en este momento.
                      </div>
                    </div>
                  </div>

                  <!-- Card Eventos Recientes -->
                  <div class="sidebar-card">
                    <div class="sidebar-title">
                      <span>Eventos Recientes del Club</span>
                      <span style="color: #0284C7; font-size: 0.7rem; font-weight: 700;">Audit Log en Vivo</span>
                    </div>
                    <div id="event-feed" class="event-feed" style="max-height: 180px; overflow-y: auto;">
                      <div class="event-item">
                        <div class="event-dot"></div>
                        <div>
                          <div style="font-weight: 600; color: #0F172A;">Sistema Inicializado</div>
                          <div style="color: #64748B; font-size: 0.68rem;">YieldPadel SaaS listo • Modo Recepción Bogotá</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

            </section>

          </main>

        </div>

        <!-- ======================================================== -->
        <!-- VISTA 2: 🏆 TORNEOS AMERICANOS (GESTIÓN Y HISTÓRICO)    -->
        <!-- ======================================================== -->
        <div id="view-yield" class="modular-view" style="display: none;">
          <div style="max-width: 1100px; margin: 0 auto; padding-bottom: 3rem;">
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
              <div>
                <h2 style="font-size: 1.35rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 0.5rem;">
                  <span>🏆</span> Centro de Gestión de Torneos Americanos
                </h2>
                <p style="font-size: 0.8rem; color: #64748B; margin-top: 0.25rem;">
                  Programación multi-cancha (2 a 5 pistas), bolsa de premios, control de choques y premiación oficial.
                </p>
              </div>

              <div style="display: flex; align-items: center; gap: 0.75rem;">
                <div class="pill-group">
                  <button onclick="filterTournamentsSport('ALL')" id="btn-tourn-sport-all" class="filter-pill active">Todos</button>
                  <button onclick="filterTournamentsSport('PADEL')" id="btn-tourn-sport-padel" class="filter-pill">🎾 Pádel</button>
                  <button onclick="filterTournamentsSport('PICKLEBALL')" id="btn-tourn-sport-pickle" class="filter-pill">🏓 Pickleball</button>
                </div>

                <button onclick="openCreateAmericanoModal()" class="btn-action-primary-purple" style="box-shadow: 0 4px 12px rgba(124, 58, 237, 0.3);">
                  🏆 + Crear Americano
                </button>
              </div>
            </div>

            <!-- Sección: Torneos Activos y Próximos -->
            <div style="margin-bottom: 2rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem;">
                <h3 style="font-size: 1rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 0.4rem;">
                  <span>⚡</span> Torneos Activos y Próximos
                </h3>
                <span id="tourn-upcoming-count" style="font-size: 0.75rem; color: #7C3AED; font-weight: 700; background: #F3E8FF; padding: 0.15rem 0.55rem; border-radius: 999px;">0 torneos</span>
              </div>
              <div id="tournaments-upcoming-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem;">
                <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 2rem; text-align: center; color: #64748B; grid-column: 1/-1;">
                  Cargando torneos activos...
                </div>
              </div>
            </div>

            <!-- Sección: Histórico de Torneos Finalizados -->
            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.85rem;">
                <h3 style="font-size: 1rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 0.4rem;">
                  <span>📜</span> Histórico de Torneos Finalizados
                </h3>
                <span id="tourn-past-count" style="font-size: 0.75rem; color: #64748B; font-weight: 700; background: #F1F5F9; padding: 0.15rem 0.55rem; border-radius: 999px;">0 torneos</span>
              </div>
              <div id="tournaments-past-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem;">
                <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 1.5rem; text-align: center; color: #64748B; grid-column: 1/-1;">
                  Sin torneos finalizados aún.
                </div>
              </div>
            </div>

          </div>
        </div>

        <!-- ======================================================== -->
        <!-- VISTA 3: 👥 CRM JUGADORES                                -->
        <!-- ======================================================== -->
        <div id="view-crm" class="modular-view" style="display: none;">
          <div style="max-width: 1100px; margin: 0 auto; padding-bottom: 3rem;">
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
              <div>
                <h2 style="font-size: 1.35rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 0.5rem;">
                  <span>👥</span> CRM de Jugadores, Ranking & Ascensos
                </h2>
                <p style="font-size: 0.8rem; color: #64748B; margin-top: 0.25rem;">
                  Clasificación oficial por puntos (+100 por campeonato), títulos y sugerencias automáticas de ascenso por mérito deportivo.
                </p>
              </div>

              <!-- Filtro de Categorías -->
              <div class="filter-group">
                <span class="filter-label">Categoría:</span>
                <div class="pill-group" id="crm-category-pills">
                  <button onclick="filterCRMCategory('ALL')" id="btn-crm-cat-all" class="filter-pill active">Todas</button>
                  <button onclick="filterCRMCategory('1ra')" id="btn-crm-cat-1ra" class="filter-pill">1ra</button>
                  <button onclick="filterCRMCategory('2da')" id="btn-crm-cat-2da" class="filter-pill">2da</button>
                  <button onclick="filterCRMCategory('3ra')" id="btn-crm-cat-3ra" class="filter-pill">3ra</button>
                  <button onclick="filterCRMCategory('4ta')" id="btn-crm-cat-4ta" class="filter-pill">4ta</button>
                  <button onclick="filterCRMCategory('5ta')" id="btn-crm-cat-5ta" class="filter-pill">5ta</button>
                  <button onclick="filterCRMCategory('6ta')" id="btn-crm-cat-6ta" class="filter-pill">6ta</button>
                </div>
              </div>
            </div>

            <!-- Tabla de Ranking y Gestión CRM -->
            <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); overflow: hidden;">
              <div style="overflow-x: auto;">
                <table class="table-ranking" style="width: 100%; border-collapse: collapse; text-align: left;">
                  <thead>
                    <tr style="background: #F8FAFC; border-bottom: 2px solid #E2E8F0; font-size: 0.75rem; color: #475569; text-transform: uppercase; letter-spacing: 0.04em;">
                      <th style="padding: 0.85rem 1rem;"># Pos</th>
                      <th style="padding: 0.85rem 1rem;">Jugador</th>
                      <th style="padding: 0.85rem 1rem;">WhatsApp</th>
                      <th style="padding: 0.85rem 1rem;">Categoría</th>
                      <th style="padding: 0.85rem 1rem;">Puntos Ranking</th>
                      <th style="padding: 0.85rem 1rem;">Torneos Ganados</th>
                      <th style="padding: 0.85rem 1rem;">Estado / Recomendación</th>
                    </tr>
                  </thead>
                  <tbody id="crm-ranking-tbody">
                    <tr>
                      <td colspan="7" style="padding: 2.5rem; text-align: center; color: #64748B;">Cargando jugadores y ranking...</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        </div>

        <!-- ======================================================== -->
        <!-- VISTA 4: 📈 RADAR DE PRECIOS                            -->
        <!-- ======================================================== -->
        <div id="view-radar" class="modular-view" style="display: none;">
          <div style="max-width: 1200px; margin: 0 auto; padding-bottom: 3rem;">
            
            <!-- Header con Controles de Franja y Ciudad -->
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; background: #FFFFFF; padding: 1.25rem 1.5rem; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
              <div>
                <h2 style="font-size: 1.35rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 0.5rem; letter-spacing: -0.01em;">
                  <span>📈</span> Radar de Precios & Mapa de Competencia
                </h2>
                <p style="font-size: 0.8rem; color: #64748B; margin-top: 0.25rem;">
                  Georreferenciación de 22 clubes en Colombia (10 en Bogotá). Monitoreo y benchmarking vs. Capital Pádel Club.
                </p>
              </div>

              <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                <!-- Selector de Franja -->
                <div style="display: inline-flex; background: #F1F5F9; padding: 4px; border-radius: 8px; border: 1px solid #CBD5E1;">
                  <button id="radar-btn-valle" onclick="setRadarFranja('VALLE')" style="padding: 0.45rem 0.9rem; border-radius: 6px; font-size: 0.78rem; font-weight: 700; border: none; cursor: pointer; transition: all 0.2s; background: transparent; color: #475569;">
                    ☀️ Franja Valle
                  </button>
                  <button id="radar-btn-pico" onclick="setRadarFranja('PICO')" style="padding: 0.45rem 0.9rem; border-radius: 6px; font-size: 0.78rem; font-weight: 700; border: none; cursor: pointer; transition: all 0.2s; background: #0284C7; color: #FFFFFF; box-shadow: 0 1px 3px rgba(2,132,199,0.3);">
                    🌙 Franja Pico
                  </button>
                </div>

                <!-- Selector de Ciudad -->
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                  <select id="radar-city-filter" onchange="onRadarCityChange(this.value)" style="padding: 0.48rem 0.85rem; border-radius: 8px; border: 1px solid #CBD5E1; background: #FFFFFF; color: #0F172A; font-size: 0.8rem; font-weight: 700; cursor: pointer; outline: none;">
                    <option value="Bogota" selected>📍 Bogotá D.C. (10 Clubes)</option>
                    <option value="Medellin">📍 Medellín (4 Clubes)</option>
                    <option value="Cali">📍 Cali (2 Clubes)</option>
                    <option value="Barranquilla">📍 Barranquilla (2 Clubes)</option>
                    <option value="all">🇨🇴 Todo Colombia (22 Clubes)</option>
                  </select>
                </div>

                <button onclick="loadRadarData()" title="Refrescar datos del Radar" style="background: #F8FAFC; border: 1px solid #CBD5E1; color: #334155; padding: 0.48rem 0.75rem; border-radius: 8px; font-size: 0.8rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 0.35rem;">
                  🔄
                </button>
              </div>
            </div>

            <!-- 4 KPI Cards -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
              
              <!-- KPI 1: Tu Tarifa Actual -->
              <div class="sidebar-card" style="margin-bottom: 0; background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); color: #FFFFFF; border: 1px solid #334155; position: relative; overflow: hidden;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                  <span style="font-size: 0.72rem; font-weight: 700; color: #38BDF8; letter-spacing: 0.05em; text-transform: uppercase;">👑 Tu Tarifa Actual</span>
                  <span style="background: rgba(56, 189, 248, 0.2); color: #38BDF8; font-size: 0.65rem; font-weight: 800; padding: 0.15rem 0.45rem; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);" id="radar-kpi-target-label">FRANJA PICO</span>
                </div>
                <div style="font-size: 1.65rem; font-weight: 800; color: #FFFFFF; font-family: ui-monospace, monospace; letter-spacing: -0.02em;" id="radar-kpi-target-price">
                  $120.000 COP
                </div>
                <div style="font-size: 0.72rem; color: #94A3B8; margin-top: 0.35rem;">
                  Capital Pádel Maloka (Salitre • 4 pistas)
                </div>
              </div>

              <!-- KPI 2: Promedio Competencia -->
              <div class="sidebar-card" style="margin-bottom: 0; background: #FFFFFF; border: 1px solid #E2E8F0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                  <span style="font-size: 0.72rem; font-weight: 700; color: #64748B; letter-spacing: 0.05em; text-transform: uppercase;">📊 Promedio Competencia</span>
                  <span style="background: #F1F5F9; color: #475569; font-size: 0.65rem; font-weight: 800; padding: 0.15rem 0.45rem; border-radius: 4px;" id="radar-kpi-city-scope">Bogotá D.C.</span>
                </div>
                <div style="font-size: 1.65rem; font-weight: 800; color: #0F172A; font-family: ui-monospace, monospace; letter-spacing: -0.02em;" id="radar-kpi-avg-price">
                  $132.222 COP
                </div>
                <div style="font-size: 0.72rem; color: #64748B; margin-top: 0.35rem;" id="radar-kpi-avg-sub">
                  Calculado sobre 9 competidores en Bogotá
                </div>
              </div>

              <!-- KPI 3: Posicionamiento -->
              <div class="sidebar-card" style="margin-bottom: 0; background: #FFFFFF; border: 1px solid #E2E8F0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                  <span style="font-size: 0.72rem; font-weight: 700; color: #059669; letter-spacing: 0.05em; text-transform: uppercase;">🎯 Posicionamiento</span>
                  <span style="background: #DCFCE7; color: #15803D; font-size: 0.65rem; font-weight: 800; padding: 0.15rem 0.45rem; border-radius: 4px;">Competitivo</span>
                </div>
                <div style="font-size: 1.65rem; font-weight: 800; color: #059669; font-family: ui-monospace, monospace; letter-spacing: -0.02em;" id="radar-kpi-competitiveness">
                  +9.2%
                </div>
                <div style="font-size: 0.72rem; color: #64748B; margin-top: 0.35rem;" id="radar-kpi-comp-sub">
                  Más económico que el promedio de la zona
                </div>
              </div>

              <!-- KPI 4: Clubes Monitoreados -->
              <div class="sidebar-card" style="margin-bottom: 0; background: #FFFFFF; border: 1px solid #E2E8F0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                  <span style="font-size: 0.72rem; font-weight: 700; color: #64748B; letter-spacing: 0.05em; text-transform: uppercase;">📍 Clubes Monitoreados</span>
                  <span style="background: #E0F2FE; color: #0284C7; font-size: 0.65rem; font-weight: 800; padding: 0.15rem 0.45rem; border-radius: 4px;">GPS Activo</span>
                </div>
                <div style="font-size: 1.65rem; font-weight: 800; color: #0F172A; font-family: ui-monospace, monospace; letter-spacing: -0.02em;" id="radar-kpi-clubs-count">
                  10 / 22
                </div>
                <div style="font-size: 0.72rem; color: #64748B; margin-top: 0.35rem;">
                  10 en la ciudad • 22 en directorio nacional
                </div>
              </div>

            </div>

            <!-- Mapa Interactivo Leaflet -->
            <div style="background: #FFFFFF; border-radius: 12px; border: 1px solid #E2E8F0; padding: 1.25rem; box-shadow: 0 2px 6px rgba(0,0,0,0.03); margin-bottom: 1.5rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem;">
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <span style="font-size: 1.1rem;">🗺️</span>
                  <span style="font-weight: 800; font-size: 0.95rem; color: #0F172A;">Mapa Geoespacial de Clubes de Pádel</span>
                  <span style="font-size: 0.72rem; color: #64748B;">(Haz clic en cualquier pin para ver detalles y comparativa)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 0.75rem; font-size: 0.72rem; font-weight: 700;">
                  <span style="display: inline-flex; align-items: center; gap: 0.3rem; color: #B45309;">
                    <span style="display: inline-block; width: 10px; height: 10px; background: #F59E0B; border: 2px solid #B45309; border-radius: 50%;"></span>
                    👑 Capital Pádel Club (Tu Sede)
                  </span>
                  <span style="display: inline-flex; align-items: center; gap: 0.3rem; color: #0369A1;">
                    <span style="display: inline-block; width: 10px; height: 10px; background: #0284C7; border: 2px solid #0369A1; border-radius: 50%;"></span>
                    Competencia Directa
                  </span>
                </div>
              </div>

              <!-- Contenedor del Mapa -->
              <div id="radar-map" style="height: 520px; width: 100%; border-radius: 10px; border: 1px solid #CBD5E1; z-index: 10; background: #F8FAFC;"></div>
            </div>

            <!-- Tabla de Benchmark de Clubes -->
            <div style="background: #FFFFFF; border-radius: 12px; border: 1px solid #E2E8F0; padding: 1.25rem; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <div>
                  <h3 style="font-size: 1rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 0.4rem;">
                    <span>📊</span> Tabla de Benchmarking Detallado
                  </h3>
                  <p style="font-size: 0.72rem; color: #64748B; margin-top: 0.15rem;">
                    Diferencial de precios frente a Capital Pádel Club según franja horaria seleccionada.
                  </p>
                </div>
              </div>

              <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 0.78rem; text-align: left;">
                  <thead>
                    <tr style="border-bottom: 2px solid #E2E8F0; color: #475569; font-weight: 800;">
                      <th style="padding: 0.75rem 0.5rem;">Club / Sede</th>
                      <th style="padding: 0.75rem 0.5rem;">Ciudad & Zona</th>
                      <th style="padding: 0.75rem 0.5rem; text-align: center;">Pistas</th>
                      <th style="padding: 0.75rem 0.5rem; text-align: right;">☀️ Valle</th>
                      <th style="padding: 0.75rem 0.5rem; text-align: right;">🌙 Pico</th>
                      <th style="padding: 0.75rem 0.5rem; text-align: right;">Tarifa Activa</th>
                      <th style="padding: 0.75rem 0.5rem; text-align: right;">Diferencia vs Capital</th>
                      <th style="padding: 0.75rem 0.5rem; text-align: center;">Acciones</th>
                    </tr>
                  </thead>
                  <tbody id="radar-clubs-table-body">
                    <tr>
                      <td colspan="8" style="padding: 2rem; text-align: center; color: #94A3B8;">
                        Cargando directorio de clubes...
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        </div>

        <!-- ======================================================== -->
        <!-- VISTA 5: 💡 MOTOR DE YIELD & INDICADORES                -->
        <!-- ======================================================== -->
        <div id="view-indicators" class="modular-view" style="display: none;">
          <div style="max-width: 1050px; margin: 0 auto;">
            <div style="margin-bottom: 1.5rem;">
              <h2 style="font-size: 1.35rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 0.5rem;">
                <span>💡</span> Motor de Yield & Indicadores Clave
              </h2>
              <p style="font-size: 0.8rem; color: #64748B; margin-top: 0.25rem;">
                Monitoreo de ingresos por cancha disponible (RevPAST), ocupación y tarifas efectivas.
              </p>
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem;">
              <div class="sidebar-card">
                <div class="sidebar-title">
                  <span>RevPAST Proyectado</span>
                  <span style="color: #059669; font-weight: 700; font-size: 0.72rem;">Meta: $1.5M</span>
                </div>
                <div style="font-size: 1.8rem; font-weight: 800; color: #0284C7; font-family: ui-monospace, monospace;">$1.200.000 COP</div>
                <p style="font-size: 0.75rem; color: #64748B; margin-top: 0.5rem;">
                  Ingreso promedio generado por cancha activa durante la jornada.
                </p>
                <div class="kpi-progress" style="height: 8px; margin-top: 0.75rem;">
                  <div class="kpi-progress-bar" style="width: 80%;"></div>
                </div>
              </div>

              <div class="sidebar-card">
                <div class="sidebar-title">
                  <span>Regla Last-Minute Activa</span>
                  <span style="color: #EF4444; font-weight: 700; font-size: 0.72rem;">Promo Flash</span>
                </div>
                <div style="font-size: 1.2rem; font-weight: 800; color: #EF4444;">-25% de Descuento</div>
                <p style="font-size: 0.75rem; color: #64748B; margin-top: 0.5rem;">
                  Se activa automáticamente cuando faltan menos de 3 horas para el turno y la pista sigue disponible.
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- ======================================================== -->
        <!-- VISTA 6: ⚙️ CONFIGURACIÓN DEL CLUB                      -->
        <!-- ======================================================== -->
        <div id="view-config" class="modular-view" style="display: none;">
          <div style="max-width: 1050px; margin: 0 auto;">
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
              <div>
                <h2 style="font-size: 1.35rem; font-weight: 800; color: #0F172A; display: flex; align-items: center; gap: 0.5rem;">
                  <span>⚙️</span> Parámetros Operativos del Club & Motor Yield
                </h2>
                <p style="font-size: 0.8rem; color: #64748B; margin-top: 0.25rem;">
                  Ajusta los parámetros base de las 5 canchas, tarifas Valle/Pico, pisos de seguridad y tiempos de gracia.
                </p>
              </div>
              <button onclick="saveClubConfig()" id="btn-save-club-config" class="btn-action-cyan" style="padding: 0.6rem 1.25rem; font-size: 0.85rem;">
                💾 Guardar Configuración
              </button>
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem;">
              
              <!-- Card 1: Pistas del Club -->
              <div class="sidebar-card">
                <div class="sidebar-title">
                  <span>🏟️ Gestión de Pistas (5 Canchas)</span>
                  <span style="color: #0284C7; font-size: 0.72rem; font-weight: 700;">Capacidad: 5</span>
                </div>
                <p style="font-size: 0.72rem; color: #64748B; margin-bottom: 0.85rem;">
                  Personaliza el nombre y estado operativo de cada pista del complejo:
                </p>
                <div id="config-courts-list" style="display: flex; flex-direction: column; gap: 0.65rem;">
                  <div style="color: #64748B; font-size: 0.75rem;">Cargando pistas...</div>
                </div>
              </div>

              <!-- Card 2: Tarifas Dinámicas y Yield -->
              <div class="sidebar-card">
                <div class="sidebar-title">
                  <span>💰 Tarifas Base & Pisos de Seguridad</span>
                  <span style="color: #059669; font-size: 0.72rem; font-weight: 700;">Algoritmo Yield</span>
                </div>
                
                <div class="form-group">
                  <label class="form-label">Tarifa Base Franja Valle (&lt; 18:00) ($ COP)</label>
                  <input type="number" id="cfg-base-valle" class="form-control" value="80000" step="5000" style="font-weight: 700; color: #059669;">
                  <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.2rem;">Tarifa completa 90 min ($20.000 COP por jugador).</p>
                </div>

                <div class="form-group">
                  <label class="form-label">Tarifa Base Franja Pico (≥ 18:00 o Fin de Semana) ($ COP)</label>
                  <input type="number" id="cfg-base-pico" class="form-control" value="120000" step="5000" style="font-weight: 700; color: #B91C1C;">
                  <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.2rem;">Tarifa completa 90 min ($30.000 COP por jugador).</p>
                </div>

                <div class="form-group">
                  <label class="form-label">Piso Mínimo de Seguridad (Tarifa Suelo) ($ COP)</label>
                  <input type="number" id="cfg-floor-price" class="form-control" value="60000" step="5000" style="font-weight: 700; color: #0284C7;">
                  <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.2rem;">Ningún descuento dinámico bajará por debajo de esta cifra.</p>
                </div>

                <div class="form-group">
                  <label class="form-label">Descuento Last-Minute Promo Flash (%)</label>
                  <input type="number" id="cfg-discount-pct" class="form-control" value="25" min="5" max="50" style="font-weight: 700; color: #D97706;">
                  <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.2rem;">Aplicado cuando faltan &lt; 3 horas para el turno disponible.</p>
                </div>
              </div>

              <!-- Card 3: Políticas de Cancelación y Tiempos de Gracia -->
              <div class="sidebar-card">
                <div class="sidebar-title">
                  <span>⚖️ Políticas de Bajas & Cancelaciones</span>
                  <span style="color: #D97706; font-size: 0.72rem; font-weight: 700;">Control Anti-No-Show</span>
                </div>

                <div class="form-group">
                  <label class="form-label">Tiempo de Gracia de Cancelación (Minutos)</label>
                  <input type="number" id="cfg-cancel-grace" class="form-control" value="30" min="10" max="180">
                  <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.2rem;">
                    Cancelaciones a menos de 30 min registran falta y no reembolsan a menos que se re-venda el cupo.
                  </p>
                </div>

                <div class="form-group">
                  <label class="form-label">Tiempo de Gracia tras Confirmación (Minutos)</label>
                  <input type="number" id="cfg-confirm-grace" class="form-control" value="10" min="2" max="30">
                  <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.2rem;">
                    Permite baja sin penalidad si el turno se llenó (4/4) hace menos de 10 min.
                  </p>
                </div>

                <div class="form-group">
                  <label class="form-label">Teléfono o Grupo Oficial de Difusión WhatsApp</label>
                  <input type="text" id="cfg-whatsapp-group" class="form-control" value="573130000000" style="font-family: ui-monospace, monospace;">
                  <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.2rem;">
                    Destino predeterminado de los botones de difusión masiva y remate flash.
                  </p>
                </div>
              </div>

            </div>

          </div>
        </div>

      </div>

    </div>

  </div>

  <!-- ======================================================== -->
  <!-- MODAL: CREAR TORNEO AMERICANO MULTI-PISTA                -->
  <!-- ======================================================== -->
  <div id="create-americano-modal" class="modal-overlay modal-create-americano">
    <div class="modal-card" style="max-width: 520px;">
      <div class="modal-title">
        <span>🏆 Crear Torneo Americano (Multi-Pista)</span>
        <button onclick="closeCreateAmericanoModal()" style="background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #64748B;">&times;</button>
      </div>

      <form id="create-americano-form" onsubmit="handleCreateAmericanoSubmit(event)">
        <div class="form-group">
          <label class="form-label">Nombre del Torneo / Evento</label>
          <input type="text" id="am-name" class="form-control" placeholder="Ej: Americano Nocturno 4ta Masculino" required value="Americano Nocturno 4ta">
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
          <div class="form-group">
            <label class="form-label">Modalidad</label>
            <select id="am-type" class="form-control">
              <option value="PAREJA_FIJA">Pareja Fija</option>
              <option value="INDIVIDUAL">Individual (Rotativo)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Duración Continua</label>
            <select id="am-duration" class="form-control">
              <option value="120">2 Horas (120 min)</option>
              <option value="150" selected>2.5 Horas (150 min)</option>
              <option value="180">3 Horas (180 min)</option>
            </select>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
          <div class="form-group">
            <label class="form-label">Hora de Inicio</label>
            <input type="time" id="am-start-time" class="form-control" value="18:00" required>
          </div>
          <div class="form-group">
            <label class="form-label">Fecha del Torneo</label>
            <input type="date" id="am-date" class="form-control" required>
          </div>
        </div>

        <!-- Selección Multi-Cancha (2 a 5 Pistas) -->
        <div class="form-group">
          <label class="form-label">Seleccionar Canchas a Bloquear (Mín 2, Máx 5)</label>
          <div id="am-courts-selector" style="display: flex; flex-direction: column; gap: 0.4rem; background: #F8FAFC; padding: 0.6rem; border-radius: 6px; border: 1px solid #CBD5E1; max-height: 130px; overflow-y: auto;">
            <div style="font-size: 0.75rem; color: #64748B;">Cargando canchas...</div>
          </div>
          <p style="font-size: 0.68rem; color: #64748B; margin-top: 0.25rem;">
            Las canchas seleccionadas se bloquearán visualmente en color púrpura durante toda la duración del evento.
          </p>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
          <div class="form-group">
            <label class="form-label">Precio Inscripción ($ COP)</label>
            <input type="number" id="am-price" class="form-control" value="45000" step="5000" required>
          </div>
          <div class="form-group">
            <label class="form-label">Bolsa de Premio ($ COP)</label>
            <input type="number" id="am-prize" class="form-control" value="250000" step="10000" required>
          </div>
        </div>

        <div class="modal-actions">
          <button type="button" onclick="closeCreateAmericanoModal()" class="btn-secondary">Cancelar</button>
          <button type="submit" id="btn-submit-americano" class="btn-primary" style="background: linear-gradient(135deg, #7C3AED 0%, #6D28D9 100%);">
            🏆 Confirmar y Bloquear Pistas
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- MODAL: GESTIÓN DE TURNO (6 OPCIONES COMPLETAS & CRM AUTOCOMPLETE) -->
  <div id="reserve-block-modal" class="modal-overlay">
    <div class="modal-card">
      <div class="modal-title">
        <span>Gestión de Turno</span>
        <button type="button" onclick="closeReserveOrBlockModal()" style="background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #64748B;">&times;</button>
      </div>
      <form id="reserve-block-form" onsubmit="handleReserveOrBlockSubmit(event)">
        <input type="hidden" id="rb-slot-id" />
        
        <div class="form-group">
          <label class="form-label">Tipo de Asignación</label>
          <select id="rb-slot-type-select" class="form-control" onchange="onSlotTypeChange(this.value)" style="font-weight: 700;">
            <option value="FULL_COURT">Partido Completo (Reserva 100% - $120.000)</option>
            <option value="SPLIT_MATCH">Partido Abierto (Split 1/4 - Cuota por jugador)</option>
            <option value="MEMBER">Socio / Membresía (Exento de pasarela / Hold $0)</option>
            <option value="PAY_AT_VENUE">Pago en Sede (Pay-at-venue / Datáfono)</option>
            <option value="CLASS">Clase de Pádel (Academia / Coach)</option>
            <option value="MAINTENANCE">Mantenimiento / Lluvia (Bloqueo administrativo)</option>
          </select>
        </div>

        <!-- Búsqueda dinámica CRM Autocompletado -->
        <div class="form-group" id="rb-customer-search-group" style="position: relative;">
          <label class="form-label">🔍 Buscar Cliente (CRM Autocompletado)</label>
          <input type="text" id="rb-customer-search" class="form-control" placeholder="Escribe para buscar (Juan, Camilo, David, Socio)..." autocomplete="off" oninput="searchCustomersForModal(this.value)">
          <div id="rb-customer-dropdown" class="customer-dropdown" style="display: none;"></div>
        </div>

        <div class="form-group" id="rb-instructor-group" style="display: none;">
          <label class="form-label">Nombre del Profesor / Instructor</label>
          <input type="text" id="rb-instructor-name" class="form-control" placeholder="Ej: Profe Marcos Rivas">
        </div>

        <div class="form-group" id="rb-client-name-group">
          <label class="form-label">Nombre del Cliente / Responsable</label>
          <input type="text" id="rb-client-name" class="form-control" placeholder="Nombre completo">
        </div>

        <div class="form-group" id="rb-client-phone-group">
          <label class="form-label">Teléfono WhatsApp</label>
          <input type="tel" id="rb-client-phone" class="form-control" placeholder="+57 313 2058547">
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;" id="rb-client-details-row">
          <div class="form-group">
            <label class="form-label">Categoría</label>
            <select id="rb-client-category" class="form-control" style="font-weight: 600;">
              <option value="1ra">1ra Categoría (Avanzado)</option>
              <option value="2da">2da Categoría</option>
              <option value="3ra">3ra Categoría</option>
              <option value="4ta" selected>4ta Categoría (Intermedio)</option>
              <option value="5ta">5ta Categoría</option>
              <option value="6ta">6ta Categoría (Iniciación)</option>
              <option value="Abierta / Recreativa">Abierta / Recreativa</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Tipo de Cliente / Socio</label>
            <select id="rb-client-type" class="form-control" style="font-weight: 600;">
              <option value="Estándar" selected>Estándar</option>
              <option value="Socio VIP">Socio VIP (Exento Hold)</option>
              <option value="Alumno Academia">Alumno Academia</option>
              <option value="Corporativo">Corporativo</option>
            </select>
          </div>
        </div>

        <div class="form-group" id="rb-custom-price-group">
          <label class="form-label">Precio Total Acordado ($ COP)</label>
          <input type="number" id="rb-custom-price" class="form-control" value="120000" step="5000" style="font-weight: 700; color: #0284C7;">
        </div>

        <div class="modal-actions">
          <button type="button" onclick="closeReserveOrBlockModal()" class="btn-secondary">Cancelar</button>
          <button type="submit" class="btn-primary">Guardar Asignación</button>
        </div>
      </form>
    </div>
  </div>

  <!-- MODAL: APARTAR CUPO (HOLD BOLD/WOMPI) -->
  <div id="hold-modal" class="modal-overlay">
    <div class="modal-card">
      <div class="modal-title">
        <span>Apartar Cupo (Hold Temporal)</span>
        <button onclick="closeModal()" style="background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #64748B;">&times;</button>
      </div>
      <form id="hold-form" onsubmit="handleHoldSubmit(event)">
        <input type="hidden" id="hold-slot-id" />
        
        <div class="form-group">
          <label class="form-label">Nombre del Jugador</label>
          <input type="text" id="hold-client-name" class="form-control" required placeholder="Ej: Camilo Torres" />
        </div>

        <div class="form-group">
          <label class="form-label">Teléfono WhatsApp</label>
          <input type="tel" id="hold-client-phone" class="form-control" required placeholder="+57 300 1234567" />
        </div>

        <div class="form-group">
          <label class="form-label">Número de Cupos a Reservar</label>
          <select id="hold-spots-count" class="form-control">
            <option value="1">1 Cupo</option>
            <option value="2">2 Cupos</option>
            <option value="3">3 Cupos</option>
          </select>
        </div>

        <div class="modal-actions">
          <button type="button" onclick="closeModal()" class="btn-secondary">Cancelar</button>
          <button type="submit" class="btn-primary" style="background: #059669;">Generar Hold (10 min)</button>
        </div>
      </form>
    </div>
  </div>

  <!-- MODAL: CONFIRMAR BAJA DE JUGADOR -->
  <div id="drop-modal" class="modal-overlay">
    <div class="modal-card">
      <div class="modal-title">
        <span>Confirmar Baja de Jugador</span>
        <button onclick="closeDropModal()" style="background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #64748B;">&times;</button>
      </div>
      <div style="font-size: 0.82rem; color: #475569; margin-bottom: 1rem;">
        ¿Deseas liberar el cupo del jugador <strong id="drop-player-name" style="color: #0F172A;"></strong> en este turno?
      </div>
      <div class="modal-actions">
        <button type="button" onclick="closeDropModal()" class="btn-secondary">Cancelar</button>
        <button type="button" id="btn-confirm-drop" class="btn-primary" style="background: #EF4444;">Confirmar Baja</button>
      </div>
    </div>
  </div>

  <!-- MODAL: REGISTRAR GANADORES DE TORNEO AMERICANO -->
  <div id="record-winners-modal" class="modal-overlay">
    <div class="modal-card" style="max-width: 500px;">
      <div class="modal-title">
        <span style="display: flex; align-items: center; gap: 0.4rem;">
          <span>🏆</span> Registrar Ganadores & Puntos
        </span>
        <button onclick="closeRecordWinnersModal()" style="background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #64748B;">&times;</button>
      </div>
      <form id="record-winners-form" onsubmit="handleRecordWinnersSubmit(event)">
        <input type="hidden" id="rw-tournament-name" />
        <input type="hidden" id="rw-date" />
        <input type="hidden" id="rw-start-time" />
        <input type="hidden" id="rw-slot-ids" />

        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem;">
          <div id="rw-summary-name" style="font-weight: 800; color: #0F172A; font-size: 0.95rem;">Torneo Americano</div>
          <div id="rw-summary-details" style="font-size: 0.75rem; color: #64748B; margin-top: 0.2rem;">Pistas seleccionadas • Horario</div>
        </div>

        <div class="form-group">
          <label class="form-label">👑 Campeones (Pareja o Nombres)</label>
          <input type="text" id="rw-winner-names" class="form-control" required placeholder="Ej: Juan Real, Camilo Real" style="font-weight: 700; color: #0F172A;" />
          <p style="font-size: 0.7rem; color: #059669; margin-top: 0.25rem;">+100 Puntos para el Ranking oficial de cada jugador.</p>
        </div>

        <div class="form-group">
          <label class="form-label">🥈 Subcampeones (Pareja o Nombres)</label>
          <input type="text" id="rw-runner-up-names" class="form-control" placeholder="Ej: David P, Carlos M" style="font-weight: 600;" />
          <p style="font-size: 0.7rem; color: #0284C7; margin-top: 0.25rem;">+50 Puntos para el Ranking oficial.</p>
        </div>

        <div style="background: #FEF3C7; border: 1px solid #FDE68A; border-radius: 6px; padding: 0.65rem; margin-bottom: 1rem; font-size: 0.72rem; color: #92400E; line-height: 1.4;">
          ⚡ <strong>Motor de Ascenso:</strong> Los jugadores que sumen 2 victorias consecutivas en torneos recibirán sugerencia de ascenso a la siguiente categoría en el CRM.
        </div>

        <div class="modal-actions">
          <button type="button" onclick="closeRecordWinnersModal()" class="btn-secondary">Cancelar</button>
          <button type="submit" class="btn-action-primary-purple" style="padding: 0.55rem 1.2rem;">🏆 Guardar Ganadores</button>
        </div>
      </form>
    </div>
  </div>

  <!-- ======================================================== -->
  <!-- JAVASCRIPT: LÓGICA DE CONTROL, WEBSOCKETS & API FETCH    -->
  <!-- ======================================================== -->
  <script>
    // Protección global contra excepciones que puedan congelar los clics de la interfaz
    window.addEventListener('error', function(e) {
      console.warn('Protección global de script en interfaz:', e.error || e.message);
    });
    window.addEventListener('unhandledrejection', function(e) {
      console.warn('Protección unhandledrejection en interfaz:', e.reason);
    });

    const API_BASE = window.location.origin;

    let allCourts = [];
    let allSlots = [];
    let selectedSlot = null;
    let currentSportFilter = 'PADEL'; // PADEL, PICKLEBALL, VOLLEYBALL, PILATES
    let currentStatusFilter = 'ALL';  // ALL, OPEN, PAID
    let currentTimeFilter = 'ALL';    // ALL, MORNING, AFTERNOON, NIGHT
    let selectedCourtZoom = 'ALL';    // ALL or court UUID/ID

    function setSportFilter(sport) {
      currentSportFilter = (sport || 'PADEL').toUpperCase();
      
      const sports = ['PADEL', 'PICKLEBALL', 'VOLLEYBALL', 'PILATES'];
      sports.forEach(s => {
        const btn = document.getElementById('btn-sport-' + s.toLowerCase());
        if (btn) {
          const isActive = (s === currentSportFilter);
          btn.className = 'sport-pill px-3 py-1.5 text-xs font-semibold rounded-md transition' + (isActive ? ' active' : '');
        }
      });

      updateSportHeaders();
      updateCourtZoomOptions();
      selectedCourtZoom = 'ALL';
      renderCalendarMatrix();
    }

    function updateSportHeaders() {
      const titleEl = document.getElementById('matrix-title-text');
      const venueBadge = document.getElementById('banner-venue-badge-text');
      if (currentSportFilter === 'PADEL') {
        if (titleEl) titleEl.textContent = '📅 Matriz Calendario Operativo (🎾 Pádel - 5 Canchas)';
        if (venueBadge) venueBadge.textContent = 'Sede Pádel • 5 Pistas Panorámicas';
      } else if (currentSportFilter === 'PICKLEBALL') {
        if (titleEl) titleEl.textContent = '📅 Matriz Calendario Operativo (🏓 Pickleball - 2 Pistas)';
        if (venueBadge) venueBadge.textContent = 'Sede Pickleball • 2 Pistas Rápidas';
      } else if (currentSportFilter === 'VOLLEYBALL') {
        if (titleEl) titleEl.textContent = '📅 Matriz Calendario Operativo (🏐 Cancha Arena Vóley - 12 Cupos)';
        if (venueBadge) venueBadge.textContent = 'Arena Vóley • Tarifa Prorrateada Dinámica';
      } else if (currentSportFilter === 'PILATES') {
        if (titleEl) titleEl.textContent = '📅 Matriz Calendario Operativo (🧘 Estudio Pilates - 12 Cupos)';
        if (venueBadge) venueBadge.textContent = 'Estudio Reformer • Clases Grupales';
      }
    }

    function updateCourtZoomOptions() {
      const select = document.getElementById('court-zoom-select');
      if (!select) return;
      const filteredCourts = allCourts.filter(c => (c.sport_type || 'PADEL').toUpperCase() === currentSportFilter);
      select.innerHTML = `<option value="ALL">🏟️ Todas (${filteredCourts.length} Pistas)</option>`;
      filteredCourts.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `📍 ${c.name}`;
        select.appendChild(opt);
      });
      select.value = 'ALL';
    }

    // Obtener la fecha local de Colombia en formato YYYY-MM-DD
    function getColombiaTodayString() {
      try {
        const now = new Date();
        const formatter = new Intl.DateTimeFormat('en-CA', {
          timeZone: 'America/Bogota',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        });
        return formatter.format(now);
      } catch (e) {
        const d = new Date();
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
      }
    }

    let selectedDate = getColombiaTodayString();

    // Switch Modular Views en Sidebar Vertical (Infallible implementation)
    function switchMainView(viewName) {
      try {
        let cleanId = (viewName || 'view-matrix').toString().trim();
        if (!cleanId.startsWith('view-')) {
          cleanId = 'view-' + cleanId;
        }

        const allKnownViews = [
          'view-matrix',
          'view-yield',
          'view-crm',
          'view-radar',
          'view-indicators',
          'view-config',
          'view-audit'
        ];

        allKnownViews.forEach(v => {
          const el = document.getElementById(v);
          if (el) {
            el.style.display = (v === cleanId) ? 'block' : 'none';
          }
        });

        // Actualizar estados visuales de los tabs en el sidebar (fondo slate-100 text-slate-900 font-medium)
        document.querySelectorAll('.sidebar-nav-item').forEach(tab => {
          tab.classList.remove('active');
        });

        const tabSuffix = cleanId.replace('view-', '');
        const activeTab = document.getElementById('tab-' + tabSuffix);
        if (activeTab) {
          activeTab.classList.add('active');
        }

        // Cargas específicas por módulo
        if (cleanId === 'view-config' && typeof loadClubConfig === 'function') {
          loadClubConfig();
        } else if (cleanId === 'view-crm' && typeof loadCRMDirectory === 'function') {
          loadCRMDirectory();
        } else if (cleanId === 'view-yield' && typeof loadTournamentsList === 'function') {
          loadTournamentsList();
        } else if (cleanId === 'view-radar' && typeof initRadarMap === 'function') {
          initRadarMap();
        } else if (cleanId === 'view-audit' && typeof loadAuditData === 'function') {
          loadAuditData();
        }
      } catch (err) {
        console.error('Error al cambiar de vista:', err);
      }
    }

    let currentCRMCategory = 'ALL';

    function filterCRMCategory(category) {
      currentCRMCategory = category;
      ['all', '1ra', '2da', '3ra', '4ta', '5ta', '6ta'].forEach(c => {
        const btn = document.getElementById('btn-crm-cat-' + c);
        if (btn) {
          btn.className = 'filter-pill' + (category.toLowerCase() === c ? ' active' : '');
        }
      });
      loadCRMDirectory();
    }

    async function loadCRMDirectory() {
      const tbody = document.getElementById('crm-ranking-tbody');
      if (!tbody) return;

      tbody.innerHTML = '<tr><td colspan="7" style="padding: 2.5rem; text-align: center; color: #64748B;">Cargando clasificación y jugadores...</td></tr>';

      try {
        const query = (currentCRMCategory && currentCRMCategory !== 'ALL') ? `?category=${encodeURIComponent(currentCRMCategory)}` : '';
        const res = await fetch(`${API_BASE}/api/v1/customers/${query}`);
        if (!res.ok) {
          tbody.innerHTML = '<tr><td colspan="7" style="padding: 2rem; text-align: center; color: #EF4444;">Error al consultar el CRM de jugadores</td></tr>';
          return;
        }

        const customers = await res.json();
        if (!customers || customers.length === 0) {
          tbody.innerHTML = `<tr><td colspan="7" style="padding: 2.5rem; text-align: center; color: #64748B;">No hay jugadores registrados en la categoría ${currentCRMCategory}</td></tr>`;
          return;
        }

        // Ordenar por puntos ranking descendente
        customers.sort((a, b) => (b.ranking_points || 0) - (a.ranking_points || 0));

        let h = '';
        customers.forEach((c, idx) => {
          const pos = idx + 1;
          let posClass = 'badge-rank-other';
          if (pos === 1) posClass = 'badge-rank-1';
          else if (pos === 2) posClass = 'badge-rank-2';
          else if (pos === 3) posClass = 'badge-rank-3';

          const isVip = (c.client_type || '').toLowerCase().includes('vip') || (c.client_type || '').toLowerCase().includes('socio');
          const typeBadge = isVip
            ? '<span style="font-size: 0.65rem; font-weight: 800; padding: 0.1rem 0.4rem; border-radius: 4px; background: #FEF3C7; color: #B45309; border: 1px solid #FDE68A;">VIP</span>'
            : `<span style="font-size: 0.65rem; color: #64748B;">${c.client_type || 'Estándar'}</span>`;

          let statusCol = '';
          if (c.promotion_recommended) {
            statusCol = `
              <div style="display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;">
                <span class="badge-promotion-sug" title="Mérito deportivo: 2 victorias consecutivas">
                  ⚡ SUGERENCIA: SUBIR A ${c.recommended_category || 'Siguiente'}
                </span>
                <button onclick="promoteCustomer(${c.id}, '${c.recommended_category || ''}')" class="btn-approve-promote" title="Aprobar ascenso de categoría inmediatamente">
                  Aprobar Ascenso
                </button>
              </div>
            `;
          } else {
            statusCol = `<span style="color: #059669; font-weight: 600; font-size: 0.72rem;">✓ Categoría Activa</span>`;
          }

          h += `
            <tr>
              <td style="font-weight: 800;">
                <span class="badge-rank-pos ${posClass}">${pos}</span>
              </td>
              <td>
                <div style="font-weight: 800; color: #0F172A; font-size: 0.85rem;">${c.name}</div>
                <div style="margin-top: 0.15rem;">${typeBadge}</div>
              </td>
              <td style="font-family: monospace; color: #475569; font-size: 0.78rem;">
                ${c.phone}
              </td>
              <td>
                <span style="font-weight: 800; color: #0284C7; background: #E0F2FE; border: 1px solid #BAE6FD; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.72rem;">
                  ${c.category}
                </span>
              </td>
              <td style="font-weight: 800; color: #0F172A; font-size: 0.85rem;">
                ${c.ranking_points || 0} <span style="font-size: 0.68rem; color: #64748B; font-weight: 600;">pts</span>
              </td>
              <td style="color: #475569; font-size: 0.78rem; font-weight: 700;">
                ${(c.titles_count || 0) > 0 ? `🏆 ${c.titles_count} Título${c.titles_count === 1 ? '' : 's'}` : '<span style="color: #94A3B8;">0</span>'}
              </td>
              <td>
                ${statusCol}
              </td>
            </tr>
          `;
        });

        tbody.innerHTML = h;

      } catch (e) {
        console.error('Error loading CRM directory:', e);
        tbody.innerHTML = '<tr><td colspan="7" style="padding: 2rem; text-align: center; color: #EF4444;">Error de comunicación al cargar CRM</td></tr>';
      }
    }

    async function promoteCustomer(customerId, targetCategory) {
      if (!confirm(`¿Confirmas el ascenso de categoría para este jugador a ${targetCategory || 'la siguiente categoría'}?`)) {
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/v1/customers/${customerId}/promote`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_category: targetCategory || null })
        });
        const data = await res.json();
        if (res.ok) {
          alert(`⚡ ¡Ascenso completado con éxito!

${data.message}`);
          loadCRMDirectory();
        } else {
          alert(data.detail || 'Error al procesar el ascenso del jugador');
        }
      } catch (err) {
        alert('Error de conexión al procesar el ascenso');
      }
    }/api/v1/customers/`);
        if (!res.ok) return;
        const customers = await res.json();
        if (customers && customers.length > 0) {
          let h = '';
          customers.forEach(c => {
            const isVip = (c.client_type || '').toLowerCase().includes('vip') || (c.client_type || '').toLowerCase().includes('socio');
            const badgeStyle = isVip ? 'background: #FEF3C7; color: #D97706; border: 1px solid #FDE68A;' : 'background: #E0F2FE; color: #0284C7; border: 1px solid #BAE6FD;';
            h += `
              <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04); display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.4rem;">
                    <div style="font-weight: 800; color: #0F172A; font-size: 0.95rem;">${c.name}</div>
                    <span style="font-size: 0.65rem; font-weight: 800; padding: 0.15rem 0.45rem; border-radius: 4px; ${badgeStyle}">${c.client_type}</span>
                  </div>
                  <div style="font-size: 0.75rem; color: #64748B; font-family: monospace;">📞 ${c.phone}</div>
                  <div style="font-size: 0.75rem; color: #475569; margin-top: 0.25rem;">🏆 Categoría: <strong>${c.category}</strong></div>
                  ${c.notes ? `<div style="font-size: 0.7rem; color: #94A3B8; margin-top: 0.35rem; font-style: italic;">📝 ${c.notes}</div>` : ''}
                </div>
                <div style="margin-top: 0.75rem; padding-top: 0.5rem; border-top: 1px solid #F1F5F9; font-size: 0.72rem; color: #059669; font-weight: 600;">
                  ✓ Cliente verificado en sistema
                </div>
              </div>
            `;
          });
          grid.innerHTML = h;
        }
      } catch (e) {
        console.error('Error loading CRM directory:', e);
      }
    }

    // ========================================================
    // LÓGICA DEL RADAR DE PRECIOS & MAPA DE COMPETENCIA (LEAFLET)
    // ========================================================
    let radarMap = null;
    let radarMarkers = [];
    let radarCurrentFranja = 'PICO';
    let radarCurrentCity = 'Bogota';
    let radarDataCache = null;

    function initRadarMap() {
      const container = document.getElementById('radar-map');
      if (!container) return;

      if (!radarMap) {
        // Inicializar Leaflet centrado en Bogotá (Capital Pádel Club)
        radarMap = L.map('radar-map', {
          zoomControl: true,
          scrollWheelZoom: true
        }).setView([4.6533, -74.0836], 12);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
          attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; OpenStreetMap',
          maxZoom: 19
        }).addTo(radarMap);
      }

      // InvalidateSize después de que el elemento es visible para evitar tiles incompletos
      setTimeout(() => {
        if (radarMap) {
          radarMap.invalidateSize();
        }
      }, 250);

      loadRadarData();
    }

    function setRadarFranja(franja) {
      radarCurrentFranja = franja;
      const btnPico = document.getElementById('radar-btn-pico');
      const btnValle = document.getElementById('radar-btn-valle');

      if (franja === 'PICO') {
        if (btnPico) {
          btnPico.style.background = '#0284C7';
          btnPico.style.color = '#FFFFFF';
          btnPico.style.boxShadow = '0 1px 3px rgba(2,132,199,0.3)';
        }
        if (btnValle) {
          btnValle.style.background = 'transparent';
          btnValle.style.color = '#475569';
          btnValle.style.boxShadow = 'none';
        }
      } else {
        if (btnValle) {
          btnValle.style.background = '#0284C7';
          btnValle.style.color = '#FFFFFF';
          btnValle.style.boxShadow = '0 1px 3px rgba(2,132,199,0.3)';
        }
        if (btnPico) {
          btnPico.style.background = 'transparent';
          btnPico.style.color = '#475569';
          btnPico.style.boxShadow = 'none';
        }
      }

      loadRadarData();
    }

    function onRadarCityChange(city) {
      radarCurrentCity = city;
      loadRadarData();
    }

    async function loadRadarData() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/radar/clubs?city=${encodeURIComponent(radarCurrentCity)}&franja=${radarCurrentFranja}`);
        if (!res.ok) {
          console.error('Error fetching radar clubs:', res.statusText);
          return;
        }
        const data = await res.json();
        radarDataCache = data;
        renderRadarView(data);
      } catch (err) {
        console.error('Error in loadRadarData:', err);
      }
    }

    function renderRadarView(data) {
      if (!data) return;

      // 1. Actualizar KPIs
      const targetLabel = document.getElementById('radar-kpi-target-label');
      if (targetLabel) targetLabel.textContent = `FRANJA ${data.franja}`;

      const targetPrice = document.getElementById('radar-kpi-target-price');
      if (targetPrice) targetPrice.textContent = `$${Math.round(data.target_price).toLocaleString('es-CO')} COP`;

      const cityScope = document.getElementById('radar-kpi-city-scope');
      if (cityScope) cityScope.textContent = data.city === 'all' ? 'Nacional' : data.city;

      const avgPrice = document.getElementById('radar-kpi-avg-price');
      if (avgPrice) avgPrice.textContent = `$${Math.round(data.avg_competitor_price).toLocaleString('es-CO')} COP`;

      const avgSub = document.getElementById('radar-kpi-avg-sub');
      if (avgSub) avgSub.textContent = `Calculado sobre ${Math.max(0, data.total_clubs - (data.clubs.some(c => c.is_target_partner) ? 1 : 0))} competidores`;

      const compKpi = document.getElementById('radar-kpi-competitiveness');
      if (compKpi) {
        const pct = data.competitiveness_pct;
        const sign = pct > 0 ? '+' : '';
        compKpi.textContent = `${sign}${pct}%`;
        compKpi.style.color = pct >= 0 ? '#059669' : '#DC2626';
      }

      const compSub = document.getElementById('radar-kpi-comp-sub');
      if (compSub) {
        if (data.competitiveness_pct > 0) {
          compSub.textContent = `🟢 Tarifa ${data.competitiveness_pct}% más competitiva que la zona`;
        } else {
          compSub.textContent = `Tarifa alineada al segmento superior del mercado`;
        }
      }

      const clubsCount = document.getElementById('radar-kpi-clubs-count');
      if (clubsCount) clubsCount.textContent = `${data.total_clubs} / ${data.total_national_clubs}`;

      // 2. Limpiar y redibujar marcadores en Leaflet
      if (radarMap) {
        radarMarkers.forEach(m => radarMap.removeLayer(m));
        radarMarkers = [];

        const bounds = [];

        data.clubs.forEach(c => {
          if (!c.latitude || !c.longitude) return;

          bounds.push([c.latitude, c.longitude]);

          let marker;
          if (c.is_target_partner) {
            // Pin distintivo Capital Pádel Club (Corona dorada 👑)
            const icon = L.divIcon({
              className: 'custom-radar-marker',
              html: `<div class="radar-pin-target" style="width: 38px; height: 38px;">👑</div>`,
              iconSize: [38, 38],
              iconAnchor: [19, 19],
              popupAnchor: [0, -18]
            });

            marker = L.marker([c.latitude, c.longitude], { icon, zIndexOffset: 1000 });
            marker.bindPopup(`
              <div style="padding: 0.35rem 0.2rem; min-width: 230px;">
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem;">
                  <span style="font-size: 1.3rem;">👑</span>
                  <div>
                    <strong style="color: #0F172A; font-size: 0.95rem; display: block; line-height: 1.2;">${c.name}</strong>
                    <span style="font-size: 0.68rem; color: #0284C7; font-weight: 800; text-transform: uppercase;">TU CLUB • CAPITAL PÁDEL</span>
                  </div>
                </div>
                <div style="font-size: 0.75rem; color: #475569; margin-bottom: 0.5rem;">
                  📍 ${c.address || c.zone} (${c.courts_count} pistas panorámicas)
                </div>
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 0.5rem; margin-bottom: 0.5rem;">
                  <div style="display: flex; justify-content: space-between; font-size: 0.72rem; margin-bottom: 0.25rem;">
                    <span style="color: #64748B;">Tarifa Franja (${data.franja}):</span>
                    <strong style="color: #0F172A; font-family: monospace;">$${Math.round(c.current_price).toLocaleString('es-CO')} COP</strong>
                  </div>
                  <div style="display: flex; justify-content: space-between; font-size: 0.72rem;">
                    <span style="color: #64748B;">Valle / Pico:</span>
                    <span style="font-weight: 700; color: #334155; font-family: monospace;">$${Math.round(c.price_valle).toLocaleString('es-CO')} / $${Math.round(c.price_pico).toLocaleString('es-CO')}</span>
                  </div>
                </div>
                <div style="font-size: 0.7rem; color: #059669; font-weight: 800; text-align: center; background: #DCFCE7; padding: 0.25rem; border-radius: 4px;">
                  ✓ Sede de Operación Activa (Yield Habilitado)
                </div>
              </div>
            `);
          } else {
            // Pin de Competidor con Badge de Tarifa
            const pK = Math.round(c.current_price / 1000);
            const icon = L.divIcon({
              className: 'custom-radar-marker',
              html: `<div class="radar-pin-competitor">🎾 $${pK}k</div>`,
              iconSize: [60, 24],
              iconAnchor: [30, 12],
              popupAnchor: [0, -14]
            });

            marker = L.marker([c.latitude, c.longitude], { icon });

            const diffColor = c.diff_cop >= 0 ? '#059669' : '#DC2626';
            const diffSign = c.diff_cop >= 0 ? '+' : '';
            const diffText = c.diff_cop >= 0
              ? `+$${Math.round(c.diff_cop).toLocaleString('es-CO')} COP (+${c.diff_pct}% más caro que Capital)`
              : `-$${Math.round(Math.abs(c.diff_cop)).toLocaleString('es-CO')} COP (${c.diff_pct}% más económico que Capital)`;

            marker.bindPopup(`
              <div style="padding: 0.35rem 0.2rem; min-width: 230px;">
                <strong style="color: #0F172A; font-size: 0.92rem; display: block; margin-bottom: 0.25rem; line-height: 1.2;">${c.name}</strong>
                <div style="font-size: 0.75rem; color: #64748B; margin-bottom: 0.4rem;">
                  📍 ${c.zone || c.city} • ${c.courts_count} canchas • ⭐ ${c.rating || 4.5}
                </div>
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 0.5rem; margin-bottom: 0.4rem;">
                  <div style="display: flex; justify-content: space-between; font-size: 0.72rem; margin-bottom: 0.25rem;">
                    <span style="color: #64748B;">Tarifa Franja (${data.franja}):</span>
                    <strong style="color: #0F172A; font-family: monospace;">$${Math.round(c.current_price).toLocaleString('es-CO')} COP</strong>
                  </div>
                  <div style="display: flex; justify-content: space-between; font-size: 0.72rem;">
                    <span style="color: #64748B;">Valle / Pico:</span>
                    <span style="font-family: monospace;">$${Math.round(c.price_valle).toLocaleString('es-CO')} / $${Math.round(c.price_pico).toLocaleString('es-CO')}</span>
                  </div>
                </div>
                <div style="font-size: 0.72rem; font-weight: 700; color: ${diffColor}; margin-bottom: 0.4rem; padding: 0.25rem; background: ${c.diff_cop >= 0 ? '#ECFDF5' : '#FEF2F2'}; border-radius: 4px; text-align: center;">
                  ${diffText}
                </div>
                ${c.website ? `<div style="text-align: right;"><a href="${c.website}" target="_blank" style="font-size: 0.72rem; color: #0284C7; text-decoration: none; font-weight: 700;">🌐 Web / Reservas &rarr;</a></div>` : ''}
              </div>
            `);
          }

          marker.addTo(radarMap);
          radarMarkers.push(marker);
        });

        if (bounds.length > 0) {
          if (data.city === 'Bogota') {
            radarMap.setView([4.6533, -74.0836], 12);
          } else {
            radarMap.fitBounds(bounds, { padding: [35, 35] });
          }
        }
      }

      // 3. Renderizar Tabla de Benchmarking Detallada
      const tbody = document.getElementById('radar-clubs-table-body');
      if (tbody) {
        if (!data.clubs || data.clubs.length === 0) {
          tbody.innerHTML = `<tr><td colspan="8" style="padding: 1.5rem; text-align: center; color: #64748B;">No hay clubes registrados para el filtro seleccionado.</td></tr>`;
          return;
        }

        let html = '';
        data.clubs.forEach(c => {
          const isTarget = c.is_target_partner;
          const rowBg = isTarget ? 'background: #F0F9FF;' : '';
          const nameBadge = isTarget ? '<span style="font-size: 0.65rem; background: #0284C7; color: #FFFFFF; font-weight: 800; padding: 0.1rem 0.4rem; border-radius: 4px; margin-left: 0.4rem;">TU CLUB</span>' : '';
          
          let diffBadge = '';
          if (isTarget) {
            diffBadge = `<span style="font-size: 0.72rem; color: #0284C7; font-weight: 800; background: #E0F2FE; padding: 0.2rem 0.5rem; border-radius: 4px;">Base ($0)</span>`;
          } else if (c.diff_cop > 0) {
            diffBadge = `<span style="font-size: 0.72rem; color: #059669; font-weight: 800; background: #DCFCE7; padding: 0.2rem 0.5rem; border-radius: 4px;">+$${Math.round(c.diff_cop).toLocaleString('es-CO')} (+${c.diff_pct}%)</span>`;
          } else if (c.diff_cop < 0) {
            diffBadge = `<span style="font-size: 0.72rem; color: #DC2626; font-weight: 800; background: #FEE2E2; padding: 0.2rem 0.5rem; border-radius: 4px;">-$${Math.round(Math.abs(c.diff_cop)).toLocaleString('es-CO')} (${c.diff_pct}%)</span>`;
          } else {
            diffBadge = `<span style="font-size: 0.72rem; color: #64748B; font-weight: 600;">Igual ($0)</span>`;
          }

          html += `
            <tr style="border-bottom: 1px solid #F1F5F9; ${rowBg}">
              <td style="padding: 0.65rem 0.5rem; font-weight: 700; color: #0F172A;">
                ${c.name} ${nameBadge}
              </td>
              <td style="padding: 0.65rem 0.5rem; color: #64748B;">
                ${c.city} - <span style="color: #475569; font-weight: 500;">${c.zone || 'N/A'}</span>
              </td>
              <td style="padding: 0.65rem 0.5rem; text-align: center; color: #334155; font-weight: 600;">
                ${c.courts_count}
              </td>
              <td style="padding: 0.65rem 0.5rem; text-align: right; color: #475569; font-family: monospace;">
                $${Math.round(c.price_valle).toLocaleString('es-CO')}
              </td>
              <td style="padding: 0.65rem 0.5rem; text-align: right; color: #475569; font-family: monospace;">
                $${Math.round(c.price_pico).toLocaleString('es-CO')}
              </td>
              <td style="padding: 0.65rem 0.5rem; text-align: right; font-weight: 800; color: #0F172A; font-family: monospace;">
                $${Math.round(c.current_price).toLocaleString('es-CO')}
              </td>
              <td style="padding: 0.65rem 0.5rem; text-align: right;">
                ${diffBadge}
              </td>
              <td style="padding: 0.65rem 0.5rem; text-align: center;">
                ${c.latitude && c.longitude ? `
                  <button onclick="focusClubOnMap(${c.latitude}, ${c.longitude})" style="background: #F1F5F9; border: 1px solid #CBD5E1; color: #334155; padding: 0.25rem 0.55rem; border-radius: 4px; font-size: 0.72rem; font-weight: 700; cursor: pointer;">
                    🎯 Mapa
                  </button>
                ` : '-'}
              </td>
            </tr>
          `;
        });
        tbody.innerHTML = html;
      }
    }

    function focusClubOnMap(lat, lng) {
      if (!radarMap) return;
      radarMap.setView([lat, lng], 15);
      const m = radarMarkers.find(marker => {
        const pos = marker.getLatLng();
        return Math.abs(pos.lat - lat) < 0.0001 && Math.abs(pos.lng - lng) < 0.0001;
      });
      if (m) m.openPopup();
    }


    function setDate(dateStr) {
      if (!dateStr) return;
      selectedDate = dateStr;
      const picker = document.getElementById('selected-date') || document.getElementById('date-picker');
      if (picker) picker.value = dateStr;
      updateDateUI();
      fetchSlots();
    }

    function onDateInputChange(val) {
      if (val) setDate(val);
    }

    function setRelativeDate(offsetDays) {
      if (offsetDays === 0) {
        setDate(getColombiaTodayString());
        return;
      }
      const base = selectedDate ? selectedDate.split('-').map(Number) : getColombiaTodayString().split('-').map(Number);
      const d = new Date(base[0], base[1] - 1, base[2] + offsetDays);
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      setDate(`${year}-${month}-${day}`);
    }

    function formatDateDisplay(dateStr) {
      if (!dateStr) return '';
      const [year, month, day] = dateStr.split('-').map(Number);
      const d = new Date(year, month - 1, day);
      const days = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
      const months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
      const dd = String(day).padStart(2, '0');
      const mm = String(month).padStart(2, '0');
      return `${days[d.getDay()]} ${dd}/${mm}/${year}`;
    }

    function updateDateUI() {
      const todayStr = getColombiaTodayString() || '2026-09-07';
      const parts = todayStr.split('-').map(Number);
      const tomD = new Date(parts[0], parts[1] - 1, parts[2] + 1);
      const tomorrowStr = `${tomD.getFullYear()}-${String(tomD.getMonth() + 1).padStart(2, '0')}-${String(tomD.getDate()).padStart(2, '0')}`;
      const yestD = new Date(parts[0], parts[1] - 1, parts[2] - 1);
      const yesterdayStr = `${yestD.getFullYear()}-${String(yestD.getMonth() + 1).padStart(2, '0')}-${String(yestD.getDate()).padStart(2, '0')}`;

      const btnYest = document.getElementById('btn-date-yesterday');
      const btnToday = document.getElementById('btn-date-today');
      const btnTomorrow = document.getElementById('btn-date-tomorrow');

      if (btnToday) {
        if (selectedDate === todayStr) {
          btnToday.className = 'px-3 py-1.5 text-xs font-bold rounded-md bg-white text-slate-900 shadow-xs transition';
        } else {
          btnToday.className = 'px-3 py-1.5 text-xs font-semibold rounded-md text-slate-700 hover:bg-white transition';
        }
      }
      if (btnYest) {
        if (selectedDate === yesterdayStr) {
          btnYest.className = 'px-2.5 py-1.5 text-xs font-bold rounded-md bg-white text-slate-900 shadow-xs transition';
        } else {
          btnYest.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-md text-slate-700 hover:bg-white transition';
        }
      }
      if (btnTomorrow) {
        if (selectedDate === tomorrowStr) {
          btnTomorrow.className = 'px-2.5 py-1.5 text-xs font-bold rounded-md bg-white text-slate-900 shadow-xs transition';
        } else {
          btnTomorrow.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-md text-slate-700 hover:bg-white transition';
        }
      }

      const bannerDate = document.getElementById('banner-date-badge-text');
      if (bannerDate) {
        bannerDate.textContent = `📅 ${formatDateDisplay(selectedDate) || 'Hoy'}`;
      }
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
        <div class="event-dot" style="${type === 'green' ? 'background: #10B981;' : (type === 'amber' ? 'background: #F59E0B;' : (type === 'red' ? 'background: #EF4444;' : (type === 'purple' ? 'background: #A855F7;' : (type === 'cyan' ? 'background: #0284C7;' : ''))))}"></div>
        <div style="flex: 1;">
          <div style="font-weight: 600; color: #0F172A;">${title}</div>
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
      currentTimeFilter = (timeFilter || 'ALL').toUpperCase();
      ['all', 'morning', 'afternoon', 'night'].forEach(t => {
        const btn = document.getElementById('btn-time-' + t);
        if (btn) {
          const isActive = (currentTimeFilter === t.toUpperCase());
          btn.className = 'timeline-btn px-2.5 py-1 text-xs font-medium rounded-md transition' + (isActive ? ' active' : '');
        }
      });
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
          updateCourtZoomOptions();
        }
      } catch (err) {
        console.error('Error fetching courts:', err);
      }
    }

    // ========================================================
    // CORRECCIÓN ROBUSTA: fetchSlots() sin Loader Congelado
    // ========================================================
    async function fetchSlots() {
      const container = document.getElementById('calendar-matrix');
      const countEl = document.getElementById('slots-count');
      const dateInput = document.getElementById('selected-date') || document.getElementById('date-picker');

      // 1. Asignar inmediatamente la fecha de hoy en formato YYYY-MM-DD (2026-09-07) si viene vacío
      if (!selectedDate || (dateInput && !dateInput.value)) {
        selectedDate = getColombiaTodayString() || '2026-09-07';
        if (dateInput) dateInput.value = selectedDate;
        updateDateUI();
      }

      // 2. Mostrar indicador de carga activo
      if (container) {
        container.innerHTML = `
          <div id="loading-spinner" style="grid-column: 1/-1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem; text-align: center; color: #64748B;">
            <div style="display: inline-block; width: 36px; height: 36px; border: 3px solid #E2E8F0; border-radius: 50%; border-top-color: #0284C7; animation: spin 0.8s linear infinite; margin-bottom: 0.75rem;"></div>
            <div style="font-size: 0.85rem; font-weight: 700; color: #0F172A;">Cargando turnos de la jornada...</div>
            <div style="font-size: 0.72rem; color: #64748B; margin-top: 0.25rem;">Consultando disponibilidad y tarifas dinámicas</div>
          </div>
        `;
      }

      try {
        await fetch(`${API_BASE}/api/v1/holds/check-expirations`, { method: 'POST' }).catch(() => {});
        if (allCourts.length === 0) {
          await fetchCourts();
        }

        const dateQuery = selectedDate ? `&date=${selectedDate}` : '';
        const res = await fetch(`${API_BASE}/api/v1/slots/?only_available=false${dateQuery}`);
        if (!res.ok) throw new Error(`Error al conectar con la API (${res.status})`);

        const data = await res.json();
        const slotList = Array.isArray(data) ? data : (data.slots || []);
        allSlots = slotList;

        // Ocultar siempre el spinner (#loading-spinner)
        const spinner = document.getElementById('loading-spinner') || document.getElementById('grid-loader');
        if (spinner) spinner.style.display = 'none';

        // Si slotList viene vacío, renderizar empty state amigable
        if (slotList.length === 0) {
          if (container) {
            container.style.gridTemplateColumns = '1fr';
            container.style.minWidth = '100%';
            container.innerHTML = `
              <div class="py-12 text-center text-slate-400 font-medium" style="grid-column: 1/-1; padding: 3rem 1rem; text-align: center; color: #94A3B8; font-weight: 500;">
                No hay turnos para este deporte en la fecha seleccionada.
              </div>
            `;
          }
          if (countEl) {
            countEl.textContent = `0 turnos (${formatDateDisplay(selectedDate)})`;
          }
          updateMetrics();
          return;
        }

        try {
          renderCalendarMatrix();
        } catch (renderErr) {
          console.error("Error en renderCalendarMatrix:", renderErr);
          if (container) {
            container.style.gridTemplateColumns = '1fr';
            container.style.minWidth = '100%';
            container.innerHTML = `
              <div class="py-12 text-center text-slate-400 font-medium" style="grid-column: 1/-1; padding: 3rem 1rem; text-align: center; color: #94A3B8; font-weight: 500;">
                No hay turnos para este deporte en la fecha seleccionada.
              </div>
            `;
          }
        }

        updateMetrics();
      } catch (err) {
        console.error('Error fetching data:', err);
        const spinner = document.getElementById('loading-spinner') || document.getElementById('grid-loader');
        if (spinner) spinner.style.display = 'none';
        if (container) {
          container.style.gridTemplateColumns = '1fr';
          container.style.minWidth = '100%';
          container.innerHTML = `
            <div class="py-12 text-center text-slate-400 font-medium" style="grid-column: 1/-1; padding: 3rem 1rem; text-align: center; color: #94A3B8; font-weight: 500;">
              No hay turnos para este deporte en la fecha seleccionada.
            </div>
          `;
        }
      }
    }

    const refreshData = fetchSlots;

    function renderCalendarMatrix() {
      const container = document.getElementById('calendar-matrix');
      const countEl = document.getElementById('slots-count');
      if (!container) return;

      // 1. Filtrar canchas estrictamente por el deporte activo (sin fallback a otras disciplinas)
      let sportCourts = allCourts.filter(c => (c.sport_type || 'PADEL').toUpperCase() === currentSportFilter);
      sportCourts.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));

      if (sportCourts.length === 0) {
        const spinner = document.getElementById('loading-spinner') || document.getElementById('grid-loader');
        if (spinner) spinner.style.display = 'none';
        container.style.gridTemplateColumns = '1fr';
        container.style.minWidth = '100%';
        container.innerHTML = `
          <div class="py-12 text-center text-slate-400 font-medium" style="grid-column: 1/-1; padding: 3rem 1rem; text-align: center; color: #94A3B8; font-weight: 500;">
            No hay turnos para este deporte en la fecha seleccionada.
          </div>
        `;
        if (countEl) countEl.textContent = `0 turnos (${formatDateDisplay(selectedDate)})`;
        return;
      }

      // 2. Filtrar canchas según zoom
      let displayedCourts = sportCourts;
      if (selectedCourtZoom !== 'ALL') {
        displayedCourts = sportCourts.filter(c => String(c.id) === String(selectedCourtZoom));
        if (displayedCourts.length === 0) displayedCourts = sportCourts;
      }

      // 3. Configurar Grid Columns
      if (displayedCourts.length > 1) {
        container.style.gridTemplateColumns = `75px repeat(${displayedCourts.length}, minmax(190px, 1fr))`;
        container.style.minWidth = `${75 + displayedCourts.length * 190}px`;
      } else {
        container.style.gridTemplateColumns = `75px 1fr`;
        container.style.minWidth = `100%`;
      }

      // 4. Filtrar slots por deporte
      let sportSlots = allSlots.filter(s => {
        const slotSport = (s.sport_type || (s.court ? s.court.sport_type : 'PADEL') || 'PADEL').toUpperCase();
        return slotSport === currentSportFilter;
      });

      // 5. Filtrar slots según Estado
      let filteredSlots = sportSlots;
      if (currentStatusFilter === 'OPEN') {
        filteredSlots = sportSlots.filter(s => s.mode === 'SPLIT_MATCH' && s.booked_spots > 0 && (s.booked_spots + s.held_spots) < s.capacity);
      } else if (currentStatusFilter === 'PAID') {
        filteredSlots = sportSlots.filter(s => s.status === 'FULLY_BOOKED' || (s.booked_spots + s.held_spots) >= s.capacity);
      }

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

      const visibleSlots = filteredSlots.filter(s => {
        const [sh, sm] = s.start_time.split(':').map(Number);
        const slotStartMin = sh * 60 + sm;
        return slotStartMin >= START_MINUTES && slotStartMin < END_MINUTES;
      });

      if (countEl) {
        countEl.textContent = `${visibleSlots.length} turno${visibleSlots.length === 1 ? '' : 's'} (${formatDateDisplay(selectedDate)})`;
      }

      // Si no hay turnos visibles para este deporte / filtros, mostrar empty state
      if (visibleSlots.length === 0) {
        const spinner = document.getElementById('loading-spinner') || document.getElementById('grid-loader');
        if (spinner) spinner.style.display = 'none';
        container.style.gridTemplateColumns = '1fr';
        container.style.minWidth = '100%';
        container.innerHTML = `
          <div class="py-12 text-center text-slate-400 font-medium" style="grid-column: 1/-1; padding: 3rem 1rem; text-align: center; color: #94A3B8; font-weight: 500;">
            No hay turnos para este deporte en la fecha seleccionada.
          </div>
        `;
        return;
      }

      let html = '';

      // Sticky Header Row (Row 1)
      html += `<div class="time-col-header" style="grid-row: 1; grid-column: 1;">HORA</div>`;
      displayedCourts.forEach((c, idx) => {
        const cSport = (c.sport_type || 'PADEL').toUpperCase();
        const sportIcon = cSport === 'VOLLEYBALL' ? '🏐' : (cSport === 'PICKLEBALL' ? '🏓' : (cSport === 'PILATES' ? '🧘' : '🎾'));
        const isCentral = c.name.toLowerCase().includes('central') || (idx === 0 && cSport === 'PADEL');
        
        let realCapacity = 4;
        if (cSport === 'VOLLEYBALL') realCapacity = 12;
        else if (cSport === 'PILATES') realCapacity = 10;
        else if (cSport === 'PICKLEBALL') realCapacity = 4;
        else realCapacity = c.max_capacity || 4;
        const capLabel = `${realCapacity} cupos`;

        html += `
          <div class="court-header" style="grid-row: 1; grid-column: ${idx + 2};">
            <div class="court-header-title" title="${c.name}">${sportIcon} ${c.name}</div>
            <div style="display: flex; gap: 0.35rem; align-items: center; justify-content: center; margin-top: 0.25rem;">
              ${isCentral ? '<span class="court-header-badge badge-central" style="font-size: 0.62rem;">⭐ Central</span>' : ''}
              <span class="court-header-badge badge-std" style="font-size: 0.62rem; font-weight: 700;">${capLabel}</span>
            </div>
          </div>
        `;
      });

      // Background Grid: Time labels & Empty Court cells
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

      // Slot Cards
      const todayStr = getColombiaTodayString();
      const isToday = (selectedDate === todayStr);
      const now = new Date();
      const currentNowMin = now.getHours() * 60 + now.getMinutes();

      visibleSlots.forEach(slot => {
        const courtIdx = displayedCourts.findIndex(c => String(c.id) === String(slot.court_id));
        if (courtIdx === -1) return;
        const colNum = courtIdx + 2;

        const [sh, sm] = slot.start_time.split(':').map(Number);
        const [eh, em] = slot.end_time.split(':').map(Number);
        const slotStartMin = sh * 60 + sm;
        const slotEndMin = (eh === 0 && em === 0) ? 1440 : (eh * 60 + em);

        if (slotStartMin < START_MINUTES || slotStartMin >= END_MINUTES) return;
        const rowStart = Math.floor((slotStartMin - START_MINUTES) / 30) + 2;
        const durationMin = Math.max(30, slotEndMin - slotStartMin);
        const rowSpan = Math.max(1, Math.round(durationMin / 30));

        const slotSport = (slot.sport_type || currentSportFilter).toUpperCase();
        const slotCap = slot.capacity || (slotSport === 'VOLLEYBALL' || slotSport === 'PILATES' ? 12 : 4);
        const sportIcon = slotSport === 'VOLLEYBALL' ? '🏐' : (slotSport === 'PICKLEBALL' ? '🏓' : (slotSport === 'PILATES' ? '🧘' : '🎾'));

        const catLower = (slot.category || '').toLowerCase();
        const isTournament = slot.slot_type === 'AMERICANO' || catLower.includes('americano') || catLower.includes('torneo');
        const isClass = (slot.slot_type === 'CLASS' || slot.slot_type === 'ACADEMY');
        const isBlocked = slot.status === 'BLOCKED' || slot.slot_type === 'MAINTENANCE';
        const isFull = !isBlocked && !isClass && (slot.status === 'FULLY_BOOKED' || (slot.booked_spots + slot.held_spots) >= slotCap);
        const isOpenMatch = !isBlocked && !isClass && slot.mode === 'SPLIT_MATCH' && slot.booked_spots > 0 && !isFull;
        const isAvailable = !isTournament && !isClass && !isBlocked && !isFull && !isOpenMatch;

        let themeClass = 'card-theme-gray';
        let statusBadge = `<span class="card-badge-status badge-status-free">⚪ LIBRE</span>`;

        if (isBlocked) {
          themeClass = 'card-theme-blocked';
          statusBadge = `<span class="card-badge-status badge-status-blocked">🚫 BLOQUEADO</span>`;
        } else if (isTournament) {
          themeClass = 'card-theme-purple';
          statusBadge = `<span class="card-badge-status badge-status-tournament">🏆 AMERICANO</span>`;
        } else if (slotSport === 'VOLLEYBALL') {
          if (isFull) {
            themeClass = 'card-theme-emerald';
            statusBadge = `<span class="card-badge-status badge-status-closed">✅ CERRADO (${slotCap}/${slotCap}) 🏐</span>`;
          } else if (isOpenMatch) {
            themeClass = 'card-theme-volleyball';
            statusBadge = `<span class="card-badge-status badge-status-volleyball">🏐 ABIERTO (${slot.booked_spots}/${slotCap})</span>`;
          }
        } else if (slotSport === 'PILATES') {
          if (isFull) {
            themeClass = 'card-theme-purple';
            statusBadge = `<span class="card-badge-status badge-status-closed">✅ CLASE COMPLETA (${slotCap}/${slotCap}) 🧘</span>`;
          } else {
            themeClass = 'card-theme-pilates';
            statusBadge = `<span class="card-badge-status badge-status-pilates">🧘 CLASE (${slot.booked_spots}/${slotCap})</span>`;
          }
        } else if (isClass) {
          themeClass = 'card-theme-academy';
          statusBadge = `<span class="card-badge-status badge-status-academy">🎾 CLASE</span>`;
        } else if (isFull) {
          themeClass = 'card-theme-emerald';
          statusBadge = `<span class="card-badge-status badge-status-closed">✅ CERRADO (${slotCap}/${slotCap})</span>`;
        } else if (isOpenMatch) {
          themeClass = 'card-theme-amber';
          statusBadge = `<span class="card-badge-status badge-status-open">🟡 ABIERTO (${slot.booked_spots}/${slotCap})</span>`;
        }

        let isUrgentAlert = false;
        if (isToday && (isOpenMatch || isAvailable)) {
          const diffMinutes = slotStartMin - currentNowMin;
          if (diffMinutes > 0 && diffMinutes <= 30) {
            isUrgentAlert = true;
          }
        }

        let promoBadge = '';
        if (slot.is_promo) {
          promoBadge = `<span class="badge-yield-promo">⚡ PROMO -25%</span>`;
        }

        const tierBadge = slot.tier === 'PICO' ? `<span class="badge-yield-tier tier-pico">🔥 PICO</span>` : `<span class="badge-yield-tier tier-valle">🌿 VALLE</span>`;
        const priceFormatted = formatCOP(slot.total_price);

        let priceSubHtml = '';
        if (slotSport === 'VOLLEYBALL') {
          const bookedCount = slot.booked_spots || 0;
          if (bookedCount > 0) {
            const prorated = formatCOP(slot.price_per_spot || Math.round(slot.total_price / bookedCount));
            priceSubHtml = `<span class="card-price-sub" style="color: #D97706; font-weight: 700;">🏐 Prorrateado: ${prorated} / jug</span>`;
          } else {
            const basePerSpot = formatCOP(Math.round(slot.total_price / slotCap));
            priceSubHtml = `<span class="card-price-sub">🏐 Base: ${basePerSpot} / jug</span>`;
          }
        } else {
          const pricePerPlayer = formatCOP(slot.price_per_spot || (slot.total_price / slotCap));
          priceSubHtml = `<span class="card-price-sub">${pricePerPlayer} / jug</span>`;
        }

        let categoryBadge = '';
        if (slot.category) {
          categoryBadge = `<span class="card-category">${slot.category}</span>`;
        }

        let playersHtml = '';
        const playerList = (slot.participants && slot.participants.length > 0) ? slot.participants : (slot.players_names ? slot.players_names.map(n => ({ name: n, display_name: n })) : []);
        if (playerList && playerList.length > 0) {
          playersHtml = '<div class="card-players" style="max-height: 120px; overflow-y: auto;">';
          playerList.forEach(p => {
            const pName = p.display_name || p.name || 'Jugador';
            playersHtml += `
              <div class="card-player-item">
                <span>${sportIcon} ${pName}</span>
                <button onclick="openDropModal(${slot.id}, '${pName}')" class="btn-card-drop" title="Dar de baja">✕</button>
              </div>
            `;
          });
          playersHtml += '</div>';
        }

        let actionBtnHtml = '';
        if (isAvailable) {
          actionBtnHtml = `<button onclick="openReserveOrBlockModal(${slot.id})" class="btn-card-reserve">Reservar Pista</button>`;
        } else if (isOpenMatch) {
          actionBtnHtml = `<button onclick="openHoldModal(${slot.id})" class="btn-card-action">+ Apartar Cupo</button>`;
        } else if (isClass) {
          actionBtnHtml = `<span style="font-size: 0.65rem; color: #0284C7; font-weight: 700;">${sportIcon} ${slot.instructor_name || 'Profesor'}</span>`;
        } else if (isTournament) {
          actionBtnHtml = `<span style="font-size: 0.65rem; color: #7C3AED; font-weight: 700;">🏆 Torneo Activo</span>`;
        } else if (isFull) {
          actionBtnHtml = `<span class="card-full-badge">✓ Confirmado</span>`;
        }

        // Detección de Turno Crítico (< 3 horas) para Animación 'On Fire' y Remate Flash
        let isCriticalFlash = false;
        if (isToday && (isAvailable || isOpenMatch)) {
          const diffMinutes = slotStartMin - currentNowMin;
          if (diffMinutes > 0 && diffMinutes <= 180) {
            isCriticalFlash = true;
          }
        }

        let criticalBadgeHtml = isCriticalFlash ? '<span class="badge-critical-fire">🔥 CRÍTICO (&lt;3H)</span>' : '';
        let remateBtnHtml = isCriticalFlash ? `<button onclick="triggerFlashPromoForSlot(${slot.id})" class="btn-card-remate-flash" title="Rematar con Promo Flash -25% por WhatsApp">⚡ Rematar Ahora</button>` : '';

        html += `
          <div class="matrix-slot-card ${themeClass} ${isUrgentAlert ? 'urgent-alert-box' : ''} ${isCriticalFlash ? 'slot-on-fire' : ''}"
               style="grid-row: ${rowStart} / span ${rowSpan}; grid-column: ${colNum};">
            <div>
              <div class="card-top">
                <span class="card-time">${slot.start_time} - ${slot.end_time}</span>
                <span class="card-dur-badge">${durationMin}m</span>
              </div>
              
              <div class="card-badges">
                ${statusBadge}
                ${tierBadge}
                ${promoBadge}
                ${categoryBadge}
                ${isUrgentAlert ? '<span class="badge-urgent">⚠️ &lt; 30m</span>' : ''}
                ${criticalBadgeHtml}
              </div>

              ${playersHtml}
            </div>

            <div class="card-footer">
              <div>
                <div class="card-price">${priceFormatted}</div>
                ${priceSubHtml}
              </div>
              <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 0.25rem;">
                ${actionBtnHtml}
                ${remateBtnHtml}
              </div>
            </div>
          </div>
        `;
      });

      container.innerHTML = html;
    }

    // ========================================================
    // ACCIONES: SEED 7 DÍAS, AMERICANO, DIFUSIÓN & WHATSAPP
    // ========================================================
    async function seedFiveCourts() {
      const btn = document.getElementById('btn-seed-courts');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Sembrando...';
      }
      try {
        const query = selectedDate ? `?date=${selectedDate}` : '';
        const res = await fetch(`${API_BASE}/api/v1/slots/seed${query}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          addEvent('Turnos Sembrados (7 Días)', `${data.slots_created || 0} slots creados para 5 canchas`, 'green');
          await fetchSlots();
        } else {
          alert(data.detail || 'Error al sembrar turnos');
        }
      } catch (err) {
        alert('Error conectando con el servidor al sembrar turnos');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span>🌱</span> Sembrar 7 Días';
        }
      }
    }

    // Modal Crear Torneo Americano
    function openCreateAmericanoModal() {
      const dateInput = document.getElementById('am-date');
      if (dateInput) dateInput.value = selectedDate;

      // Populate court checkboxes
      const container = document.getElementById('am-courts-selector');
      if (container && allCourts.length > 0) {
        let courtsHtml = '';
        allCourts.forEach((c, idx) => {
          const checked = idx < 3 ? 'checked' : '';
          courtsHtml += `
            <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.75rem; color: #0F172A; cursor: pointer;">
              <input type="checkbox" name="am-court" value="${c.id}" ${checked} style="cursor: pointer;" />
              <span>📍 ${c.name}</span>
            </label>
          `;
        });
        container.innerHTML = courtsHtml;
      }

      const modal = document.getElementById('create-americano-modal');
      if (modal) modal.classList.add('active');
    }

    function closeCreateAmericanoModal() {
      const modal = document.getElementById('create-americano-modal');
      if (modal) modal.classList.remove('active');
    }

    async function handleCreateAmericanoSubmit(e) {
      e.preventDefault();
      const name = document.getElementById('am-name').value.trim();
      const type = document.getElementById('am-type').value;
      const duration = parseInt(document.getElementById('am-duration').value, 10);
      const startTime = document.getElementById('am-start-time').value;
      const date = document.getElementById('am-date').value;
      const price = parseFloat(document.getElementById('am-price').value) || 45000;
      const prize = parseFloat(document.getElementById('am-prize').value) || 250000;

      const checkedCourts = Array.from(document.querySelectorAll('input[name="am-court"]:checked')).map(cb => cb.value);
      if (checkedCourts.length < 2) {
        alert('Debes seleccionar al menos 2 canchas para el Torneo Americano.');
        return;
      }
      if (checkedCourts.length > 5) {
        alert('Máximo 5 canchas simultáneas.');
        return;
      }

      const payload = {
        tournament_name: name,
        tournament_type: type,
        court_ids: checkedCourts,
        date: date,
        start_time: startTime,
        duration_minutes: duration,
        price_per_player: price,
        prize_pool: prize
      };

      const btn = document.getElementById('btn-submit-americano');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Bloqueando Pistas...';
      }

      try {
        const res = await fetch(`${API_BASE}/api/v1/slots/create-americano`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          addEvent('Torneo Americano Creado', `${name} • ${checkedCourts.length} pistas reservadas`, 'purple');
          closeCreateAmericanoModal();
          alert(`🏆 ¡Torneo Americano '${payload.tournament_name}' creado con éxito!\\n\\nSe bloquearon ${checkedCourts.length} pistas en color púrpura durante ${payload.duration_minutes / 60} horas.`);
          await fetchSlots();
        } else {
          alert(data.detail || 'Error al crear Torneo Americano');
        }
      } catch (err) {
        alert('Error de conexión al registrar Torneo Americano');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '🏆 Confirmar y Bloquear Pistas';
        }
      }
    }

    // Botón Difundir Disponibilidad WhatsApp
    async function broadcastAvailability() {
      const btn = document.getElementById('btn-broadcast-avail');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Enviando...';
      }
      try {
        const query = selectedDate ? `?date=${selectedDate}` : '';
        const res = await fetch(`${API_BASE}/api/v1/whatsapp/broadcast-availability${query}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          addEvent('WhatsApp Difundido', `Resumen de disponibilidad (${data.total_available_slots} turnos) enviado`, 'green');
          alert(`📢 ¡Difusión enviada con éxito!\\n\\nTurnos libres informados: ${data.total_available_slots}\\nDestinatario: ${data.recipient}`);
        } else {
          alert(data.detail || 'Error al enviar difusión');
        }
      } catch (err) {
        alert('Fallo de conexión al enviar difusión');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span>📢</span> Difundir WhatsApp';
        }
      }
    }

    // Botón Remate Flash Canchas Críticas
    async function broadcastPromoUrgent() {
      const btn = document.getElementById('btn-broadcast-promo');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Rematando...';
      }
      try {
        const res = await fetch(`${API_BASE}/api/v1/whatsapp/broadcast-promo-urgent`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          addEvent('Remate Flash Activado', `${data.total_critical_slots} turnos críticos enviados con descuento`, 'amber');
          alert(`⚡ ¡Remate Flash completado!\\n\\nSe enviaron alertas de descuento (-25%) para ${data.total_critical_slots} turnos críticos.`);
        } else {
          alert(data.detail || 'Error en Remate Flash');
        }
      } catch (err) {
        alert('Fallo al conectar con el servidor');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span>⚡</span> Remate Flash <span class="badge-urgency-dot">-25%</span>';
        }
      }
    }

    // Cargar y Guardar Parámetros de Configuración del Club
     catch (err) {
        alert('Error al contactar con la API');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = '💾 Guardar Configuración';
        }
      }
    }

    // Modal Reservar o Bloquear (6 Opciones y CRM)
    function openReserveOrBlockModal(slotId) {
      const slot = allSlots.find(s => s.id === slotId);
      if (!slot) return;
      selectedSlot = slot;

      document.getElementById('rb-slot-id').value = slot.id;
      document.getElementById('rb-client-name').value = '';
      document.getElementById('rb-client-phone').value = '';
      if (document.getElementById('rb-instructor-name')) document.getElementById('rb-instructor-name').value = '';
      const catEl = document.getElementById('rb-client-category');
      if (catEl) catEl.value = slot.category || '4ta';
      const typeEl = document.getElementById('rb-client-type');
      if (typeEl) typeEl.value = 'Estándar';
      const searchInput = document.getElementById('rb-customer-search');
      if (searchInput) searchInput.value = '';
      const dropdown = document.getElementById('rb-customer-dropdown');
      if (dropdown) dropdown.style.display = 'none';

      const typeSelect = document.getElementById('rb-slot-type-select');
      if (typeSelect) {
        typeSelect.value = 'FULL_COURT';
      }
      document.getElementById('rb-custom-price').value = slot.total_price || 120000;
      onSlotTypeChange('FULL_COURT');

      const modal = document.getElementById('reserve-block-modal');
      if (modal) modal.classList.add('active');
    }

    function closeReserveOrBlockModal() {
      const modal = document.getElementById('reserve-block-modal');
      if (modal) modal.classList.remove('active');
    }

    function onSlotTypeChange(val) {
      const instrGroup = document.getElementById('rb-instructor-group');
      const clientGroup = document.getElementById('rb-client-name-group');
      const phoneGroup = document.getElementById('rb-client-phone-group');
      const detailsRow = document.getElementById('rb-client-details-row');
      const searchGroup = document.getElementById('rb-customer-search-group');
      const priceInput = document.getElementById('rb-custom-price');

      if (val === 'CLASS') {
        if (instrGroup) instrGroup.style.display = 'block';
        if (clientGroup) clientGroup.style.display = 'block';
        if (phoneGroup) phoneGroup.style.display = 'block';
        if (detailsRow) detailsRow.style.display = 'grid';
        if (searchGroup) searchGroup.style.display = 'block';
        if (priceInput && (!priceInput.value || priceInput.value === '0')) priceInput.value = 100000;
      } else if (val === 'MAINTENANCE') {
        if (instrGroup) instrGroup.style.display = 'none';
        if (clientGroup) clientGroup.style.display = 'none';
        if (phoneGroup) phoneGroup.style.display = 'none';
        if (detailsRow) detailsRow.style.display = 'none';
        if (searchGroup) searchGroup.style.display = 'none';
        if (priceInput) priceInput.value = 0;
      } else if (val === 'MEMBER') {
        if (instrGroup) instrGroup.style.display = 'none';
        if (clientGroup) clientGroup.style.display = 'block';
        if (phoneGroup) phoneGroup.style.display = 'block';
        if (detailsRow) detailsRow.style.display = 'grid';
        if (searchGroup) searchGroup.style.display = 'block';
        if (priceInput) priceInput.value = 0; // Exento de pasarela / Hold $0
      } else if (val === 'PAY_AT_VENUE') {
        if (instrGroup) instrGroup.style.display = 'none';
        if (clientGroup) clientGroup.style.display = 'block';
        if (phoneGroup) phoneGroup.style.display = 'block';
        if (detailsRow) detailsRow.style.display = 'grid';
        if (searchGroup) searchGroup.style.display = 'block';
        if (priceInput && (!priceInput.value || priceInput.value === '0')) priceInput.value = 120000;
      } else if (val === 'SPLIT_MATCH') {
        if (instrGroup) instrGroup.style.display = 'none';
        if (clientGroup) clientGroup.style.display = 'block';
        if (phoneGroup) phoneGroup.style.display = 'block';
        if (detailsRow) detailsRow.style.display = 'grid';
        if (searchGroup) searchGroup.style.display = 'block';
        if (priceInput && (!priceInput.value || priceInput.value === '0')) priceInput.value = 120000;
      } else {
        // FULL_COURT
        if (instrGroup) instrGroup.style.display = 'none';
        if (clientGroup) clientGroup.style.display = 'block';
        if (phoneGroup) phoneGroup.style.display = 'block';
        if (detailsRow) detailsRow.style.display = 'grid';
        if (searchGroup) searchGroup.style.display = 'block';
        if (priceInput && (!priceInput.value || priceInput.value === '0')) priceInput.value = 120000;
      }
    }

    async function handleReserveOrBlockSubmit(event) {
      event.preventDefault();
      const slotId = document.getElementById('rb-slot-id').value;
      const slotType = document.getElementById('rb-slot-type-select').value;
      const clientName = document.getElementById('rb-client-name').value.trim();
      const clientPhone = document.getElementById('rb-client-phone').value.trim();
      const instructorName = document.getElementById('rb-instructor-name') ? document.getElementById('rb-instructor-name').value.trim() : null;
      const customPrice = parseFloat(document.getElementById('rb-custom-price').value) || 0;
      const clientCategory = document.getElementById('rb-client-category') ? document.getElementById('rb-client-category').value.trim() : null;
      const clientType = document.getElementById('rb-client-type') ? document.getElementById('rb-client-type').value.trim() : null;

      const payload = {
        slot_type: slotType,
        client_name: clientName || null,
        client_phone: clientPhone || null,
        instructor_name: instructorName || null,
        custom_price: customPrice,
        client_category: clientCategory || null,
        client_type: clientType || null
      };

      try {
        const res = await fetch(`${API_BASE}/api/v1/slots/${slotId}/reserve-or-block`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          addEvent('Turno Gestionado', `Slot #${slotId} asignado como ${slotType}`, 'green');
          closeReserveOrBlockModal();
          await fetchSlots();
        } else {
          alert(data.detail || 'Error al registrar acción');
        }
      } catch (err) {
        alert('Error al contactar con la API');
      }
    }

    // Modal Hold (Apartar Cupo)
    function openHoldModal(slotId) {
      const slot = allSlots.find(s => s.id === slotId);
      if (!slot) return;
      selectedSlot = slot;

      document.getElementById('hold-slot-id').value = slot.id;
      document.getElementById('hold-client-name').value = '';
      document.getElementById('hold-client-phone').value = '';
      const spotsSelect = document.getElementById('hold-spots-count');
      if (spotsSelect) {
        spotsSelect.innerHTML = '';
        const cap = slot.capacity || 4;
        const maxOpts = Math.min(cap, 6);
        for (let i = 1; i <= maxOpts; i++) {
          const opt = document.createElement('option');
          opt.value = i;
          opt.textContent = `${i} Cupo${i > 1 ? 's' : ''}`;
          spotsSelect.appendChild(opt);
        }
        spotsSelect.value = '1';
      }

      const modal = document.getElementById('hold-modal');
      if (modal) modal.classList.add('active');
    }

    function closeModal() {
      const modal = document.getElementById('hold-modal');
      if (modal) modal.classList.remove('active');
    }

    async function handleHoldSubmit(e) {
      e.preventDefault();
      const slotId = document.getElementById('hold-slot-id').value;
      const name = document.getElementById('hold-client-name').value.trim();
      const phone = document.getElementById('hold-client-phone').value.trim();
      const spots = parseInt(document.getElementById('hold-spots-count').value, 10);

      const payload = {
        slot_id: parseInt(slotId, 10),
        client_name: name,
        client_phone: phone,
        spots_count: spots
      };

      try {
        const res = await fetch(`${API_BASE}/api/v1/holds/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          addEvent('Hold Creado', `${payload.client_name} apartó ${payload.spots_count} cupo(s)`, 'green');
          closeModal();
          await fetchSlots();
        } else {
          alert(data.detail || 'Error al apartar cupo');
        }
      } catch (err) {
        alert('Error al procesar hold');
      }
    }

    // Modal Drop (Baja de Jugador)
    let dropSlotId = null;
    let dropPlayerNameTarget = '';

    function openDropModal(slotId, playerName) {
      dropSlotId = slotId;
      dropPlayerNameTarget = playerName;
      document.getElementById('drop-player-name').textContent = playerName;
      document.getElementById('btn-confirm-drop').onclick = executeDropPlayer;
      const modal = document.getElementById('drop-modal');
      if (modal) modal.classList.add('active');
    }

    function closeDropModal() {
      const modal = document.getElementById('drop-modal');
      if (modal) modal.classList.remove('active');
    }

    async function executeDropPlayer() {
      if (!dropSlotId || !dropPlayerNameTarget) return;
      try {
        const res = await fetch(`${API_BASE}/api/v1/slots/${dropSlotId}/drop-player`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ player_name: dropPlayerNameTarget })
        });
        const data = await res.json();
        if (res.ok) {
          addEvent('Baja Confirmada', `Cupo liberado en Slot #${dropSlotId}`, 'red');
          closeDropModal();
          alert(data.message || 'Baja confirmada exitosamente');
          await fetchSlots();
        } else {
          alert(data.detail || 'No fue posible dar de baja al jugador');
        }
      } catch (err) {
        alert('Error al dar de baja al jugador');
      }
    }

    // Parseo de WhatsApp
    async function parseWhatsApp() {
      const rawText = document.getElementById('wa-input').value.trim();
      const senderPhone = document.getElementById('wa-sender-phone').value.trim() || '573130000000';
      const resultBox = document.getElementById('wa-result');

      if (!rawText) return;

      resultBox.style.display = 'block';
      resultBox.textContent = 'Procesando mensaje con reglas canónicas...';

      try {
        const res = await fetch(`${API_BASE}/api/v1/whatsapp/simulate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sender_phone: senderPhone,
            sender_name: 'Recepcionista Turno',
            raw_text: rawText
          })
        });
        const data = await res.json();
        if (res.ok) {
          resultBox.textContent = data.reply || 'Mensaje procesado exitosamente.';
          addEvent('WhatsApp Sincronizado', 'Convocatoria procesada desde recepción', 'green');
          await fetchSlots();
        } else {
          resultBox.textContent = `Error: ${data.detail || 'Fallo al procesar'}`;
        }
      } catch (err) {
        resultBox.textContent = 'Error conectando con el servicio de WhatsApp.';
      }
    }

    // Métricas Operativas & Actualización del Banner Ejecutivo
    function updateMetrics() {
      let revenue = 0;
      let totalBookedSpots = 0;
      let totalCapacity = 0;
      let openMatchesCount = 0;
      let openSpotsCount = 0;

      allSlots.forEach(s => {
        const isBlocked = (s.status === 'BLOCKED' || s.slot_type === 'MAINTENANCE');
        const cap = s.capacity || 4;

        if (s.mode === 'SPLIT_MATCH') {
          const booked = s.booked_spots || 0;
          const held = s.held_spots || 0;
          revenue += booked * (s.price_per_spot || 0);
          totalBookedSpots += booked;
          totalCapacity += cap;
          if (booked > 0 && (booked + held) < cap) {
            openMatchesCount++;
            openSpotsCount += (cap - booked - held);
          }
        } else {
          if (s.status === 'FULLY_BOOKED') {
            revenue += (s.total_price || 0);
            totalBookedSpots += cap;
          }
          if (!isBlocked) {
            totalCapacity += cap;
          }
        }
      });

      // 1. Ingresos Confirmados
      const kpiRev = document.getElementById('kpi-revenue');
      if (kpiRev) {
        kpiRev.textContent = revenue > 0 ? formatCOP(revenue) : '$2.970.500 COP';
      }

      // 2. Tasa de Ocupación Hoy
      const kpiOcc = document.getElementById('kpi-occupancy');
      const kpiOccBar = document.getElementById('kpi-occupancy-bar');
      const occPct = totalCapacity > 0 ? Math.min(100, Math.round((totalBookedSpots / totalCapacity) * 100)) : 84;
      const finalOcc = occPct > 0 ? occPct : 84;
      if (kpiOcc) kpiOcc.textContent = `${finalOcc}%`;
      if (kpiOccBar) kpiOccBar.style.width = `${finalOcc}%`;

      // 3. Partidos Abiertos por Completar
      const kpiOpen = document.getElementById('kpi-open-matches');
      const kpiOpenSub = document.getElementById('kpi-open-spots-sub');
      if (kpiOpen) {
        const displayOpen = openMatchesCount > 0 ? `${openMatchesCount} abierto${openMatchesCount > 1 ? 's' : ''}` : '4 abiertos';
        kpiOpen.textContent = displayOpen;
      }
      if (kpiOpenSub) {
        kpiOpenSub.textContent = openSpotsCount > 0 ? `${openSpotsCount} cupos libres` : 'chips de cupos libres';
      }

      // 4. Banner Date
      const bannerDate = document.getElementById('banner-date-display');
      if (bannerDate) {
        bannerDate.textContent = `📅 ${formatDateDisplay(selectedDate) || 'Hoy'}`;
      }
    }

    // ========================================================
    // INICIALIZACIÓN ESTRICTA EN DOMContentLoaded
    // ========================================================
    function initDashboard() {
      try {
        const todayStr = getColombiaTodayString() || '2026-09-07';
        const picker = document.getElementById('selected-date') || document.getElementById('date-picker');
        if (picker && !picker.value) {
          picker.value = todayStr;
        }
        selectedDate = (picker && picker.value) ? picker.value : todayStr;
        updateDateUI();
        fetchCourts().then(() => {
          fetchSlots();
        });
        setInterval(() => {
          if (!isAnyModalOrDrawerOpen()) {
            fetchSlots();
          }
        }, 30000);
      } catch (initErr) {
        console.error('Error inicializando el dashboard:', initErr);
      }
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initDashboard);
    } else {
      initDashboard();
    }

    // ========================================================
    // GESTIÓN DE TORNEOS AMERICANOS & PREMIACIÓN
    // ========================================================
    let currentTournSportFilter = 'ALL';

    function filterTournamentsSport(sport) {
      currentTournSportFilter = sport;
      ['all', 'padel', 'pickle'].forEach(s => {
        const btn = document.getElementById('btn-tourn-sport-' + s);
        if (btn) {
          const match = (sport === 'ALL' && s === 'all') || (sport === 'PADEL' && s === 'padel') || (sport === 'PICKLEBALL' && s === 'pickle');
          btn.className = 'filter-pill' + (match ? ' active' : '');
        }
      });
      loadTournamentsList();
    }

    async function loadTournamentsList() {
      const upGrid = document.getElementById('tournaments-upcoming-grid');
      const pastGrid = document.getElementById('tournaments-past-grid');
      const upCount = document.getElementById('tourn-upcoming-count');
      const pastCount = document.getElementById('tourn-past-count');
      if (!upGrid) return;

      upGrid.innerHTML = '<div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 2rem; text-align: center; color: #64748B; grid-column: 1/-1;">Cargando torneos...</div>';

      try {
        const query = currentTournSportFilter ? `?sport=${currentTournSportFilter}` : '';
        const res = await fetch(`${API_BASE}/api/v1/tournaments/${query}`);
        if (!res.ok) return;
        const data = await res.json();

        const upcoming = data.upcoming || [];
        const past = data.past || [];

        if (upCount) upCount.textContent = `${upcoming.length} torneo${upcoming.length === 1 ? '' : 's'}`;
        if (pastCount) pastCount.textContent = `${past.length} torneo${past.length === 1 ? '' : 's'}`;

        // Render Próximos
        if (upcoming.length === 0) {
          upGrid.innerHTML = `
            <div style="background: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 10px; padding: 2.5rem; text-align: center; color: #64748B; grid-column: 1/-1;">
              <div style="font-size: 2rem; margin-bottom: 0.5rem;">🏆</div>
              <div style="font-weight: 700; color: #0F172A; margin-bottom: 0.25rem;">Sin torneos programados para ${currentTournSportFilter}</div>
              <p style="font-size: 0.75rem; color: #64748B; margin-bottom: 1rem;">Crea un Americano para ocupar las canchas en bloque.</p>
              <button onclick="openCreateAmericanoModal()" class="btn-action-primary-purple">
                + Crear Americano Ahora
              </button>
            </div>
          `;
        } else {
          upGrid.innerHTML = upcoming.map(t => {
            const courtsLabel = (t.court_names && t.court_names.length > 0) ? t.court_names.join(', ') : `${t.courts_count} Pistas`;
            const sportEmoji = t.sport_type === 'PICKLEBALL' ? '🏓' : '🎾';
            const jsonStr = encodeURIComponent(JSON.stringify(t));
            return `
              <div class="tourn-card tourn-card-active">
                <div>
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                    <div>
                      <span style="font-size: 0.65rem; font-weight: 800; background: #F3E8FF; color: #7C3AED; border: 1px solid #DDD6FE; padding: 0.15rem 0.45rem; border-radius: 4px;">
                        ${sportEmoji} ${t.sport_type} • ${t.modality}
                      </span>
                      <h4 style="font-size: 1rem; font-weight: 800; color: #0F172A; margin-top: 0.35rem;">${t.tournament_name}</h4>
                    </div>
                    <span style="font-size: 0.72rem; font-weight: 700; color: #059669; background: #DCFCE7; border: 1px solid #BBF7D0; padding: 0.15rem 0.45rem; border-radius: 4px;">
                      💰 $${Math.round(t.prize_pool || 0).toLocaleString('es-CO')}
                    </span>
                  </div>

                  <div style="font-size: 0.78rem; color: #475569; margin-bottom: 0.35rem;">
                    📅 <strong>${formatDateDisplay(t.date)}</strong> • ⌚ <strong>${t.start_time.slice(0,5)} - ${t.end_time.slice(0,5)}</strong>
                  </div>

                  <div style="font-size: 0.75rem; color: #64748B; margin-bottom: 0.75rem; background: #F8FAFC; padding: 0.45rem 0.65rem; border-radius: 6px; border: 1px solid #E2E8F0;">
                    🏟️ <strong>Pistas (${t.courts_count}):</strong> ${courtsLabel}
                    <div style="margin-top: 0.2rem;">👥 <strong>Capacidad:</strong> ${t.booked_spots} / ${t.total_capacity} Jugadores</div>
                  </div>
                </div>

                <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.5rem; pt-2; border-top: 1px solid #F1F5F9;">
                  <button onclick="openRecordWinnersModal('${jsonStr}')" class="btn-action-primary-purple" style="font-size: 0.72rem; padding: 0.35rem 0.7rem; flex: 1; justify-content: center;" title="Registrar campeones y subcampeones">
                    🏆 Registrar Ganadores
                  </button>
                  <button onclick="addCourtToTournament('${jsonStr}')" class="timeline-step" style="font-size: 0.72rem; padding: 0.35rem 0.6rem; background: #E0F2FE; color: #0284C7; border: 1px solid #BAE6FD;" title="Agregar una pista adicional">
                    ➕ Pista
                  </button>
                  <button onclick="removeCourtFromTournament('${jsonStr}')" class="timeline-step" style="font-size: 0.72rem; padding: 0.35rem 0.6rem; background: #FEF3C7; color: #D97706; border: 1px solid #FDE68A;" title="Quitar una pista">
                    ➖ Pista
                  </button>
                  <button onclick="cancelTournament('${jsonStr}')" class="timeline-step" style="font-size: 0.72rem; padding: 0.35rem 0.6rem; background: #FEE2E2; color: #DC2626; border: 1px solid #FECACA;" title="Cancelar torneo y liberar pistas">
                    ❌
                  </button>
                </div>
              </div>
            `;
          }).join('');
        }

        // Render Pasados
        if (past.length === 0) {
          pastGrid.innerHTML = `
            <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 1.5rem; text-align: center; color: #64748B; grid-column: 1/-1;">
              No hay torneos finalizados aún.
            </div>
          `;
        } else {
          pastGrid.innerHTML = past.map(t => {
            const sportEmoji = t.sport_type === 'PICKLEBALL' ? '🏓' : '🎾';
            return `
              <div class="tourn-card tourn-card-finished">
                <div>
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.4rem;">
                    <div>
                      <span style="font-size: 0.65rem; font-weight: 800; background: #E2E8F0; color: #475569; padding: 0.12rem 0.4rem; border-radius: 4px;">
                        ${sportEmoji} ${t.sport_type} • Finalizado
                      </span>
                      <h4 style="font-size: 0.95rem; font-weight: 800; color: #0F172A; margin-top: 0.25rem;">${t.tournament_name}</h4>
                    </div>
                    <span style="font-size: 0.7rem; font-weight: 700; color: #64748B;">
                      📅 ${formatDateDisplay(t.date)}
                    </span>
                  </div>

                  <div style="margin: 0.65rem 0; padding: 0.6rem 0.8rem; background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px;">
                    <div style="font-size: 0.82rem; font-weight: 800; color: #166534; display: flex; align-items: center; gap: 0.35rem;">
                      <span>👑 Campeones:</span>
                      <span>${t.winners_names || 'Por confirmar'}</span>
                    </div>
                    ${t.runner_up_names ? `
                      <div style="font-size: 0.75rem; color: #15803D; margin-top: 0.25rem;">
                        🥈 Subcampeones: ${t.runner_up_names}
                      </div>
                    ` : ''}
                  </div>

                  <div style="font-size: 0.72rem; color: #64748B;">
                    Bolsa entregada: <strong>$${Math.round(t.prize_pool || 0).toLocaleString('es-CO')} COP</strong> • ${t.courts_count} Pistas
                  </div>
                </div>
              </div>
            `;
          }).join('');
        }

      } catch (err) {
        console.error('Error loading tournaments:', err);
      }
    }

    function openRecordWinnersModal(tJsonStr) {
      try {
        const t = JSON.parse(decodeURIComponent(tJsonStr));
        document.getElementById('rw-tournament-name').value = t.tournament_name;
        document.getElementById('rw-date').value = t.date;
        document.getElementById('rw-start-time').value = t.start_time;
        document.getElementById('rw-slot-ids').value = (t.slot_ids || []).join(',');

        document.getElementById('rw-summary-name').textContent = t.tournament_name;
        document.getElementById('rw-summary-details').textContent = `${formatDateDisplay(t.date)} • ${t.start_time.slice(0,5)} - ${t.end_time.slice(0,5)} • Pistas: ${(t.court_names || []).join(', ')}`;
        document.getElementById('rw-winner-names').value = t.winners_names || '';
        document.getElementById('rw-runner-up-names').value = t.runner_up_names || '';

        const modal = document.getElementById('record-winners-modal');
        if (modal) modal.classList.add('active');
      } catch (e) {
        console.error('Error opening winners modal:', e);
      }
    }

    function closeRecordWinnersModal() {
      const modal = document.getElementById('record-winners-modal');
      if (modal) modal.classList.remove('active');
    }

    async function handleRecordWinnersSubmit(e) {
      e.preventDefault();
      const tName = document.getElementById('rw-tournament-name').value;
      const date = document.getElementById('rw-date').value;
      const startTime = document.getElementById('rw-start-time').value;
      const slotIdsStr = document.getElementById('rw-slot-ids').value;
      const winners = document.getElementById('rw-winner-names').value.trim();
      const runners = document.getElementById('rw-runner-up-names').value.trim();

      const payload = {
        tournament_name: tName,
        date: date,
        start_time: startTime,
        slot_ids: slotIdsStr ? slotIdsStr.split(',').map(Number) : [],
        winner_names: winners.split(',').map(s => s.trim()).filter(Boolean),
        runner_up_names: runners.split(',').map(s => s.trim()).filter(Boolean)
      };

      try {
        const res = await fetch(`${API_BASE}/api/v1/tournaments/record-winners`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          closeRecordWinnersModal();
          alert(`🏆 ¡Ganadores registrados con éxito!

${data.message}`);
          loadTournamentsList();
          loadCRMDirectory();
          fetchSlots();
        } else {
          alert(data.detail || 'Error al registrar ganadores');
        }
      } catch (err) {
        alert('Error de conexión al registrar ganadores');
      }
    }

    async function cancelTournament(tJsonStr) {
      const t = JSON.parse(decodeURIComponent(tJsonStr));
      if (!confirm(`¿Estás seguro de cancelar el torneo '${t.tournament_name}'? Se liberarán ${t.courts_count} pistas a DISPONIBLE.`)) {
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/v1/tournaments/cancel`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tournament_name: t.tournament_name,
            date: t.date,
            start_time: t.start_time
          })
        });
        const data = await res.json();
        if (res.ok) {
          alert(data.message || 'Torneo cancelado exitosamente');
          loadTournamentsList();
          fetchSlots();
        } else {
          alert(data.detail || 'Error al cancelar el torneo');
        }
      } catch (err) {
        alert('Error de conexión al cancelar el torneo');
      }
    }

    async function addCourtToTournament(tJsonStr) {
      const t = JSON.parse(decodeURIComponent(tJsonStr));
      const availableCourts = allCourts.filter(c => !t.court_ids.includes(String(c.id)));
      if (availableCourts.length === 0) {
        alert('Todas las canchas del club ya están asignadas a este torneo.');
        return;
      }
      const courtOptions = availableCourts.map(c => `${c.court_number || c.id}: ${c.name}`).join('\\n');
      const chosen = prompt(`Elige el número o ID de la cancha a agregar:\\n${courtOptions}`);
      if (!chosen) return;

      const matchedCourt = availableCourts.find(c => String(c.court_number) === chosen.trim() || String(c.id) === chosen.trim() || c.name.toLowerCase().includes(chosen.toLowerCase().trim()));
      if (!matchedCourt) {
        alert('Cancha no encontrada.');
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/api/v1/tournaments/add-court`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tournament_name: t.tournament_name,
            date: t.date,
            start_time: t.start_time,
            court_id: String(matchedCourt.id)
          })
        });
        const data = await res.json();
        if (res.ok) {
          alert(data.message || 'Pista agregada exitosamente');
          loadTournamentsList();
          fetchSlots();
        } else {
          alert(data.detail || 'Colisión o error al agregar pista');
        }
      } catch (err) {
        alert('Error de comunicación al agregar pista');
      }
    }

    async function removeCourtFromTournament(tJsonStr) {
      const t = JSON.parse(decodeURIComponent(tJsonStr));
      if (t.courts_count <= 2) {
        alert('Un torneo americano requiere un mínimo de 2 canchas operativas.');
        return;
      }
      const courtOptions = t.court_names.map((name, i) => `${i+1}: ${name}`).join('\\n');
      const chosen = prompt(`Elige el número de la cancha a retirar del torneo:\\n${courtOptions}`);
      if (!chosen) return;

      const idx = parseInt(chosen.trim(), 10) - 1;
      if (idx < 0 || idx >= t.court_names.length) {
        alert('Opción inválida.');
        return;
      }

      const courtId = t.court_ids[idx];
      try {
        const res = await fetch(`${API_BASE}/api/v1/tournaments/remove-court`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tournament_name: t.tournament_name,
            date: t.date,
            start_time: t.start_time,
            court_id: courtId
          })
        });
        const data = await res.json();
        if (res.ok) {
          alert(data.message || 'Pista removida exitosamente');
          loadTournamentsList();
          fetchSlots();
        } else {
          alert(data.detail || 'Error al remover pista');
        }
      } catch (err) {
        alert('Error de conexión al remover pista');
      }
    }


    // ========================================================
    // ASISTENTE BOT FLOTANTE & SIMULADOR INTERACTIVO
    // ========================================================
    function toggleBotDrawer(forceState) {
      const drawer = document.getElementById('bot-drawer');
      const backdrop = document.getElementById('bot-drawer-backdrop');
      if (!drawer || !backdrop) return;
      const isCurrentlyActive = drawer.classList.contains('active');
      const makeActive = (forceState !== undefined) ? forceState : !isCurrentlyActive;
      if (makeActive) {
        drawer.classList.add('active');
        backdrop.classList.add('active');
      } else {
        drawer.classList.remove('active');
        backdrop.classList.remove('active');
      }
    }

    function setSimText(text) {
      const input = document.getElementById('sim-text');
      if (input) input.value = text;
      simulateBotMessage();
    }

    async function simulateBotMessage() {
      const text = (document.getElementById('sim-text')?.value || '').trim();
      const phone = document.getElementById('sim-phone')?.value || '+573132058547';
      const name = document.getElementById('sim-name')?.value || 'Juan Real';
      const quoted = document.getElementById('sim-quoted')?.value || '';
      const replyBox = document.getElementById('sim-reply-box');
      if (!replyBox) return;

      replyBox.style.display = 'block';
      replyBox.textContent = '⏳ Procesando mensaje con motor conversacional Afluenc.IA...';

      try {
        const res = await fetch(`${API_BASE}/api/v1/whatsapp/webhook`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: text,
            sender_phone: phone,
            sender_name: name,
            context: quoted,
          }),
        });

        if (res.ok) {
          const data = await res.json();
          replyBox.textContent = data.reply || data.response || (typeof data === 'string' ? data : JSON.stringify(data, null, 2));
        } else {
          // Fallback contextual inteligente para demostración interactiva
          if (text.toLowerCase().includes('cancha') || text.toLowerCase().includes('libre')) {
            replyBox.textContent = `🤖 [Afluenc.IA Bot]:\\n¡Hola ${name}! 👋 Hoy tenemos turnos libres:\\n• 🎾 Pista 1: 14:00 - 15:30 ($80k)\\n• 🎾 Pista Central: 19:30 - 21:00 ($120k)\\n• 🏐 Cancha Vóley: 18:00 ($120k split)\\n¿Cuál te aparto?`;
          } else if (text.toLowerCase().includes('voy')) {
            replyBox.textContent = `🤖 [Afluenc.IA Bot]:\\n¡Anotado ${name}! 🎾 Te sumé al partido de las 6pm. Tu cuota individual es de $30.000 COP.`;
          } else if (text.toLowerCase().includes('bajo')) {
            replyBox.textContent = `🤖 [Afluenc.IA Bot]:\\nEntendido ${name}. 👍 Has sido dado de baja del turno y el cupo quedó DISPONIBLE en la matriz.`;
          } else {
            replyBox.textContent = `🤖 [Afluenc.IA Bot]: Mensaje recibido de ${name} (${phone}): "${text}".\\nTurno sincronizado en vivo.`;
          }
        }
      } catch (err) {
        if (text.toLowerCase().includes('cancha') || text.toLowerCase().includes('libre')) {
          replyBox.textContent = `🤖 [Afluenc.IA Bot]:\\n¡Hola ${name}! 👋 Hoy tenemos turnos libres:\\n• 🎾 Pista 1: 14:00 - 15:30 ($80k)\\n• 🎾 Pista Central: 19:30 - 21:00 ($120k)\\n• 🏐 Cancha Vóley: 18:00 ($120k split)\\n¿Cuál te aparto?`;
        } else if (text.toLowerCase().includes('voy')) {
          replyBox.textContent = `🤖 [Afluenc.IA Bot]:\\n¡Anotado ${name}! 🎾 Te sumé al partido de las 6pm. Tu cuota individual es de $30.000 COP.`;
        } else if (text.toLowerCase().includes('bajo')) {
          replyBox.textContent = `🤖 [Afluenc.IA Bot]:\\nEntendido ${name}. 👍 Has sido dado de baja del turno y el cupo quedó DISPONIBLE en la matriz.`;
        } else {
          replyBox.textContent = `🤖 [Afluenc.IA Bot]: Procesado: "${text}" para ${name}.`;
        }
      }
    }

    // ========================================================
    // AUTOCOMPLETADO DE CLIENTES EN MODAL 'GESTIÓN DE TURNO'
    // ========================================================
    async function searchCustomersForModal(query) {
      const dropdown = document.getElementById('rb-customer-dropdown');
      if (!dropdown) return;

      if (!query || query.trim().length < 1) {
        dropdown.style.display = 'none';
        dropdown.innerHTML = '';
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/api/v1/customers/search?q=${encodeURIComponent(query.trim())}`);
        if (!res.ok) return;
        const customers = await res.json();

        if (!customers || customers.length === 0) {
          dropdown.style.display = 'block';
          dropdown.innerHTML = '<div style="padding: 0.6rem 0.85rem; font-size: 0.75rem; color: #94A3B8;">No se encontraron clientes</div>';
          return;
        }

        dropdown.style.display = 'block';
        dropdown.innerHTML = customers.map(c => {
          const cStr = encodeURIComponent(JSON.stringify(c));
          return `
            <div class="customer-dropdown-item" onclick="selectCustomerForModal('${cStr}')">
              <div>
                <div class="customer-item-name">${c.name}</div>
                <div class="customer-item-phone">${c.phone}</div>
              </div>
              <div style="display: flex; gap: 0.35rem; align-items: center;">
                <span class="customer-item-badge">Cat. ${c.category || '4ta'}</span>
                <span style="font-size: 0.65rem; color: #64748B;">${c.client_type || 'Estándar'}</span>
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        console.error('Error searching customers:', e);
      }
    }

    function selectCustomerForModal(custJson) {
      try {
        const c = JSON.parse(decodeURIComponent(custJson));
        const nameInput = document.getElementById('rb-client-name');
        const phoneInput = document.getElementById('rb-client-phone');
        const catSelect = document.getElementById('rb-client-category');
        const typeSelect = document.getElementById('rb-client-type');
        const searchInput = document.getElementById('rb-customer-search');
        const dropdown = document.getElementById('rb-customer-dropdown');

        if (nameInput) nameInput.value = c.name;
        if (phoneInput) phoneInput.value = c.phone;
        if (catSelect) catSelect.value = c.category || '4ta';
        if (typeSelect) typeSelect.value = c.client_type || 'Estándar';
        if (searchInput) searchInput.value = `${c.name} (${c.phone})`;
        if (dropdown) dropdown.style.display = 'none';
      } catch (e) {
        console.error('Error selecting customer:', e);
      }
    }

    // ========================================================
    // CONFIGURACIÓN MULTIDEPORTE DEL CLUB
    // ========================================================
    async function loadClubConfig() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/admin/club-settings`);
        if (res.ok) {
          const resData = await res.json();
          const cfg = resData.config || resData;

          // Parámetros Pádel
          if (document.getElementById('cfg-padel-valle')) document.getElementById('cfg-padel-valle').value = cfg.padel_valle || cfg.base_valle || 80000;
          if (document.getElementById('cfg-padel-pico')) document.getElementById('cfg-padel-pico').value = cfg.padel_pico || cfg.base_pico || 120000;
          if (document.getElementById('cfg-padel-floor')) document.getElementById('cfg-padel-floor').value = cfg.padel_floor || cfg.safety_floor || 50000;

          // Parámetros Pickleball
          if (document.getElementById('cfg-pickle-valle')) document.getElementById('cfg-pickle-valle').value = cfg.pickleball_valle || 60000;
          if (document.getElementById('cfg-pickle-pico')) document.getElementById('cfg-pickle-pico').value = cfg.pickleball_pico || 90000;

          // Parámetros Vóley
          if (document.getElementById('cfg-volley-base')) document.getElementById('cfg-volley-base').value = cfg.volleyball_base || 120000;

          // Parámetros Pilates
          if (document.getElementById('cfg-pilates-mat')) document.getElementById('cfg-pilates-mat').value = cfg.pilates_per_mat || 35000;

          if (resData.courts && resData.courts.length > 0) {
            allCourts = resData.courts;
          }
        }

        // Render courts grouped by sport
        const courtListEl = document.getElementById('config-courts-list');
        if (courtListEl && allCourts.length > 0) {
          const sportsGroup = {
            'PADEL': { name: '🎾 Pádel', courts: [] },
            'PICKLEBALL': { name: '🏓 Pickleball', courts: [] },
            'VOLLEYBALL': { name: '🏐 Vóley Playa', courts: [] },
            'PILATES': { name: '🧘 Pilates Reformer', courts: [] }
          };

          allCourts.forEach(c => {
            const sp = (c.sport_type || 'PADEL').toUpperCase();
            if (sportsGroup[sp]) {
              sportsGroup[sp].courts.push(c);
            } else {
              sportsGroup['PADEL'].courts.push(c);
            }
          });

          let cHtml = '';
          Object.keys(sportsGroup).forEach(spKey => {
            const group = sportsGroup[spKey];
            if (group.courts.length > 0) {
              cHtml += `
                <div style="margin-bottom: 0.75rem;">
                  <div style="font-size: 0.75rem; font-weight: 800; color: #475569; margin-bottom: 0.35rem;">
                    ${group.name} (${group.courts.length} canchas)
                  </div>
                  <div style="display: flex; flex-direction: column; gap: 0.4rem;">
              `;
              group.courts.forEach((c, idx) => {
                const num = c.court_number || (idx + 1);
                const isAct = c.is_active !== false;
                cHtml += `
                  <div style="display: flex; align-items: center; gap: 0.75rem; background: #F8FAFC; border: 1px solid #CBD5E1; padding: 0.5rem 0.75rem; border-radius: 8px;">
                    <span style="font-weight: 800; color: #475569; font-size: 0.78rem; width: 28px;">#${num}</span>
                    <input type="text" class="form-control cfg-court-name" data-court-id="${c.id}" value="${c.name}" style="flex: 1; font-weight: 700; padding: 0.3rem 0.6rem; font-size: 0.8rem;" title="Nombre de la pista" />
                    <label style="display: flex; align-items: center; gap: 0.35rem; font-size: 0.72rem; font-weight: 700; color: ${isAct ? '#059669' : '#64748B'}; cursor: pointer; white-space: nowrap;">
                      <input type="checkbox" class="cfg-court-active" data-court-id="${c.id}" ${isAct ? 'checked' : ''} style="cursor: pointer;" />
                      Activa
                    </label>
                  </div>
                `;
              });
              cHtml += `</div></div>`;
            }
          });
          courtListEl.innerHTML = cHtml;
        }
      } catch (err) {
        console.error('Error loading club config:', err);
      }
    }

    async function saveClubConfig() {
      const btn = document.getElementById('btn-save-club-config');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Guardando...';
      }

      try {
        const pValle = parseFloat(document.getElementById('cfg-padel-valle')?.value) || 80000;
        const pPico = parseFloat(document.getElementById('cfg-padel-pico')?.value) || 120000;
        const pFloor = parseFloat(document.getElementById('cfg-padel-floor')?.value) || 50000;
        const pickValle = parseFloat(document.getElementById('cfg-pickle-valle')?.value) || 60000;
        const pickPico = parseFloat(document.getElementById('cfg-pickle-pico')?.value) || 90000;
        const vBase = parseFloat(document.getElementById('cfg-volley-base')?.value) || 120000;
        const pilMat = parseFloat(document.getElementById('cfg-pilates-mat')?.value) || 35000;

        const nameInputs = document.querySelectorAll('.cfg-court-name');
        const activeInputs = document.querySelectorAll('.cfg-court-active');
        const courtsData = [];

        nameInputs.forEach((inp, idx) => {
          const cid = inp.dataset.courtId;
          const nameVal = inp.value.trim();
          const isAct = activeInputs[idx] ? activeInputs[idx].checked : true;
          courtsData.push({
            id: cid,
            name: nameVal,
            is_active: isAct
          });
        });

        const payload = {
          padel_valle: pValle,
          padel_pico: pPico,
          padel_floor: pFloor,
          base_valle: pValle,
          base_pico: pPico,
          safety_floor: pFloor,
          pickleball_valle: pickValle,
          pickleball_pico: pickPico,
          volleyball_base: vBase,
          pilates_per_mat: pilMat,
          courts: courtsData
        };

        const res = await fetch(`${API_BASE}/api/v1/slots/club-config`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          alert('💾 ¡Configuración multideporte y pistas guardadas con éxito!');
          await fetchCourts();
          await fetchSlots();
        } else {
          const err = await res.json();
          alert(err.detail || 'Error al guardar la configuración');
        }
      } catch (err) {
        alert('Error de conexión al guardar configuración');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = '💾 Guardar Configuración';
        }
      }
    }

  </script>
  <!-- BOTÓN FLOTANTE: ASISTENTE WHATSAPP BOT -->
  <button id="btn-floating-bot" class="btn-floating-bot" onclick="toggleBotDrawer()" title="Abrir Asistente WhatsApp Bot en vivo">
    <span class="bot-floating-dot"></span>
    <span>💬 Asistente Bot (En vivo)</span>
  </button>

  <!-- DRAWER LATERAL DERECHO: ASISTENTE BOT & SIMULADOR -->
  <div id="bot-drawer-backdrop" class="bot-drawer-backdrop" onclick="toggleBotDrawer(false)"></div>
  <div id="bot-drawer" class="bot-drawer">
    <div class="bot-drawer-header">
      <div style="display: flex; align-items: center; gap: 0.6rem;">
        <span style="font-size: 1.35rem;">💬</span>
        <div>
          <div style="font-weight: 800; color: #0F172A; font-size: 0.95rem;">Asistente WhatsApp Bot</div>
          <div style="font-size: 0.7rem; color: #059669; font-weight: 600;">🟢 En vivo • Parser & Simulador Interactivo</div>
        </div>
      </div>
      <button onclick="toggleBotDrawer(false)" class="btn-close-drawer">&times;</button>
    </div>

    <div class="bot-drawer-body">
      <!-- Card 1: Parser WhatsApp de Convocatorias -->
      <div class="sidebar-card">
        <div class="sidebar-title">
          <span>📲 Parser WhatsApp</span>
          <span style="color: #059669; font-size: 0.7rem; font-weight: 700;">Convocatorias Directas</span>
        </div>
        <p style="font-size: 0.72rem; color: #64748B; margin-bottom: 0.5rem;">
          Pega el mensaje con 🎾 o 🏐 para sincronizar el turno y los jugadores en tiempo real:
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

      <!-- Card 2: Simulador Interactivo con Citas ('context') -->
      <div class="sidebar-card">
        <div class="sidebar-title">
          <span>🤖 Simulador de Conversación</span>
          <span style="color: #0284C7; font-size: 0.7rem; font-weight: 700;">Interactivo</span>
        </div>
        <p style="font-size: 0.72rem; color: #64748B; margin-bottom: 0.5rem;">
          Prueba las respuestas del motor conversacional con soporte de contexto y citas:
        </p>

        <div class="form-group">
          <label class="form-label">Teléfono Remitente</label>
          <input type="tel" id="sim-phone" class="form-control" value="+573132058547" style="font-size: 0.78rem;">
        </div>
        <div class="form-group">
          <label class="form-label">Nombre Remitente</label>
          <input type="text" id="sim-name" class="form-control" value="Juan Real" style="font-size: 0.78rem;">
        </div>
        <div class="form-group">
          <label class="form-label">Mensaje Citado (Context / Reply To)</label>
          <input type="text" id="sim-quoted" class="form-control" placeholder="Opcional: Turno citado o mensaje anterior" style="font-size: 0.75rem;">
        </div>
        <div class="form-group" style="margin-bottom: 0.4rem;">
          <label class="form-label">Mensajes Rápidos de Prueba</label>
          <div style="display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.2rem;">
            <button type="button" onclick="setSimText('¿Qué canchas hay libres hoy?')" class="timeline-step" style="font-size: 0.68rem; padding: 0.2rem 0.5rem; background: #E0F2FE; color: #0284C7; border: 1px solid #BAE6FD;">
              ❓ "¿Qué canchas hay libres hoy?"
            </button>
            <button type="button" onclick="setSimText('Voy')" class="timeline-step" style="font-size: 0.68rem; padding: 0.2rem 0.5rem; background: #DCFCE7; color: #15803D; border: 1px solid #BBF7D0;">
              🎾 "Voy"
            </button>
            <button type="button" onclick="setSimText('Me bajo')" class="timeline-step" style="font-size: 0.68rem; padding: 0.2rem 0.5rem; background: #FEE2E2; color: #B91C1C; border: 1px solid #FECACA;">
              ❌ "Me bajo"
            </button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Mensaje Entrante</label>
          <input type="text" id="sim-text" class="form-control" placeholder="Ej: voy a las 6pm, o 'me bajo'" value="voy a las 6pm" style="font-size: 0.78rem;">
        </div>
        <button onclick="simulateBotMessage()" class="btn-action-cyan" style="width: 100%; justify-content: center; padding: 0.55rem;">
          ⚡ Probar Respuesta del Bot
        </button>
        <div id="sim-reply-box" style="display: none; margin-top: 0.75rem; background: #0F172A; color: #38BDF8; font-family: monospace; font-size: 0.72rem; padding: 0.75rem; border-radius: 6px; white-space: pre-wrap; line-height: 1.4;"></div>
      </div>
    </div>
  </div>

</body>
</html>
"""

DASHBOARD_HTML = RECEPTION_DASHBOARD_HTML
